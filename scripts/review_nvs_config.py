#!/usr/bin/env python3
"""Compare saved, unencrypted ESP-IDF NVS snapshots offline; never access a device."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path


class SnapshotError(ValueError):
    """An invalid or ambiguous snapshot, with a value-free diagnostic."""


def require(condition, message):
    if not condition:
        raise SnapshotError(message)


def load_parser(idf_path):
    source = Path(idf_path) / "components/nvs_flash/nvs_partition_tool/nvs_parser.py"
    spec = importlib.util.spec_from_file_location("cybertrack_nvs_parser", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NVS_Partition, hashlib.sha256(source.read_bytes()).hexdigest()


def logical_values(data, parser):
    require(len(data) >= 4096 and len(data) % 4096 == 0, "NVS size must contain whole pages")
    partition = parser("nvs", bytearray(data))
    entries, page_indices = [], set()
    for page in partition.pages:
        if page.is_empty:
            block = data[page.start_address:page.start_address + 4096]
            require(block == b"\xff" * 4096, "Empty page contains unexpected bytes")
            continue
        header = page.header
        require(header["status"] in ("Active", "Full"), "Unsupported NVS page state")
        require(header["version"] in (1, 2), "Unsupported NVS page version")
        require(header["page_index"] not in page_indices, "Duplicate NVS page sequence")
        page_indices.add(header["page_index"])
        require(header["crc"]["original"] == header["crc"]["computed"], "NVS page CRC mismatch")
        for entry in page.entries:
            require(entry.state != "Invalid", "Invalid NVS entry state")
            if entry.state != "Written":
                continue
            meta = entry.metadata
            require(meta["span"] == len(entry.children) + 1, "Truncated NVS entry")
            require(all(child.state == "Written" for child in entry.children), "Incomplete NVS value")
            require(meta["crc"]["original"] == meta["crc"]["computed"], "NVS entry CRC mismatch")
            require(bool(entry.key) and entry.data is not None, "Unsupported NVS key")
            entries.append(entry)
    namespaces = {}
    for entry in entries:
        if entry.metadata["namespace"] != 0:
            continue
        index = entry.data["value"]
        require(entry.metadata["type"] == "uint8_t" and type(index) is int and 0 < index < 255,
                "Invalid NVS namespace")
        require(index not in namespaces and entry.key not in namespaces.values(), "Ambiguous NVS namespace")
        namespaces[index] = entry.key
    records = {}
    for entry in entries:
        meta = entry.metadata
        if meta["namespace"] == 0:
            continue
        require(meta["namespace"] in namespaces, "Unknown NVS namespace")
        key = (namespaces[meta["namespace"]], entry.key, meta["chunk_index"])
        require(key not in records, "Ambiguous written NVS records")
        kind = meta["type"]
        if kind in ("string", "blob", "blob_data"):
            raw = b"".join(child.raw for child in entry.children)
            require(entry.data["size"] <= len(raw), "Truncated NVS value")
            require(meta["crc"]["data_original"] == meta["crc"]["data_computed"], "NVS data CRC mismatch")
            value = bytes(raw[:entry.data["size"]])
            if kind == "string":
                require(value.endswith(b"\0"), "Unterminated NVS string")
        else:
            require(kind == "blob_index" or kind in {
                "uint8_t", "int8_t", "uint16_t", "int16_t", "uint32_t", "int32_t", "uint64_t", "int64_t"
            }, "Unsupported NVS value type")
            require(meta["span"] == 1, "Unexpected span for fixed-size NVS value")
            value = entry.data["value"]
        records[key] = (kind, value)
    indexed = {key[:2] for key, (kind, _) in records.items() if kind == "blob_index"}
    require(all(key[:2] in indexed for key, (kind, _) in records.items() if kind == "blob_data"),
            "Unindexed NVS blob data")
    values = {}
    for (namespace, key, _), (kind, value) in records.items():
        if kind == "blob_data":
            continue
        if kind == "blob_index":
            size, count, start = value
            require(0 <= start <= 255 and start + count <= 256, "Invalid NVS blob range")
            chunks = [records.get((namespace, key, i)) for i in range(start, start + count)]
            require(all(chunk is not None and chunk[0] == "blob_data" for chunk in chunks), "Missing NVS blob chunk")
            value = b"".join(chunk[1] for chunk in chunks)
            require(len(value) == size, "NVS blob size mismatch")
            kind = "blob"
        require((namespace, key) not in values, "Ambiguous logical NVS value")
        values[(namespace, key)] = (kind, value)
    return values, len(records)


def compare(before, after, parser, offset=0, size=None, allowed=()):
    require(len(before) == len(after), "Snapshot sizes differ")
    size = len(before) - offset if size is None else size
    require(offset >= 0 and size > 0 and offset + size <= len(before), "NVS range exceeds snapshot")
    a, records_a = logical_values(before[offset:offset + size], parser)
    b, records_b = logical_values(after[offset:offset + size], parser)
    changed = sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key))
    # Exceptions permit only changes to existing entries, never additions/deletions.
    permitted = [key for key in changed if "/".join(key) in allowed and key in a and key in b
                 and a[key][0] == b[key][0]]
    unexpected = [key for key in changed if key not in permitted]
    outside_same = before[:offset] == after[:offset] and before[offset + size:] == after[offset + size:]
    return {
        "scope": "Offline logical NVS comparison; no device, firmware identity, RF or physical acceptance",
        "snapshot_bytes": len(before), "nvs_offset": offset, "nvs_bytes": size,
        "records_before": records_a, "records_after": records_b,
        "logical_entries_before": len(a), "logical_entries_after": len(b),
        "all_logical_values_unchanged": not changed, "non_nvs_bytes_unchanged": outside_same,
        "changed_keys": ["/".join(key) for key in changed],
        "permitted_changed_keys": ["/".join(key) for key in permitted],
        "unexpected_changed_keys": ["/".join(key) for key in unexpected],
        "added_keys": ["/".join(key) for key in sorted(b.keys() - a.keys())],
        "removed_keys": ["/".join(key) for key in sorted(a.keys() - b.keys())],
        "requested_runtime_exceptions": sorted(allowed),
        "matches_policy": not unexpected and outside_same,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--before", required=True, type=Path)
    cli.add_argument("--after", required=True, type=Path)
    cli.add_argument("--idf-path", default=os.environ.get("IDF_PATH"), type=Path)
    cli.add_argument("--nvs-offset", default=0, type=lambda x: int(x, 0))
    cli.add_argument("--nvs-size", type=lambda x: int(x, 0))
    cli.add_argument("--allow-runtime-change", action="append", default=[], choices=("websocket/token", "phy/cal_data"))
    args = cli.parse_args()
    try:
        require(args.idf_path is not None, "Set --idf-path or IDF_PATH to an ESP-IDF checkout")
        # Never echo third-party parser exceptions/output: snapshots contain credentials.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            parser, digest = load_parser(args.idf_path)
            result = compare(args.before.read_bytes(), args.after.read_bytes(), parser,
                             args.nvs_offset, args.nvs_size, set(args.allow_runtime_change))
        result["parser_sha256"] = digest
    except SnapshotError as error:
        print(json.dumps({"error": str(error), "matches_policy": False}))
        return 2
    except Exception:
        print(json.dumps({"error": "Cannot parse snapshots or load SDK parser; details withheld", "matches_policy": False}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["matches_policy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
