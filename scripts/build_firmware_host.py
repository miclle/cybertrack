#!/usr/bin/env python3
"""Compile the prepared MCP dispatcher and board callbacks with host-only IO stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(source, idf, output, sanitize=False):
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    board = source / "main/boards/bread-compact-wifi"
    registration = (board / "cybertrack_tools.cc").read_text()
    # Pin the executable to this checkout's actual callback and control code.
    names = ["cybertrack_tools.cc"] + [p.name for p in (ROOT/"firmware/esp32-audio").glob("*.h") if (board/p.name).exists()]
    for name in names:
        if (board / name).read_bytes() != (ROOT / "firmware/esp32-audio" / name).read_bytes():
            raise ValueError("prepared source differs from checkout: " + name)
    header = (source / "main/mcp_server.h").read_text()
    (output / "mcp_tool_types.h").write_text(header[:header.index("\nclass McpServer {")] + "\n#endif\n")
    server = (source / "main/mcp_server.cc").read_text()
    start = server.find("void McpServer::RejectRobotInput(")
    if start < 0: start = server.index("void McpServer::DoToolCall(")
    (output / "host_dispatch.inc").write_text(server[start:])
    start = registration.index("    server.AddTool(")
    end = registration.index('    ESP_LOGI("CT_AUDIO", "READY', start)
    callbacks = registration[start:end]
    if callbacks.count("server.AddTool(") != 12:
        raise ValueError("expected 12 robot tools")
    (output / "host_registration.inc").write_text(callbacks)
    start = registration.index("int CyberTrackVoiceTurn(")
    end = registration.index("void CyberTrackActionLink(", start)
    (output / "host_admission.inc").write_text(registration[start:end])
    start = registration.index("std::string Reply(")
    end = registration.index("\n}\n}", start) + 2
    (output / "receipt_reply.inc").write_text(registration[start:end])
    cjson = idf / "components/json/cJSON"
    debug_flags=["-g","-fsanitize=address,undefined"] if sanitize else []
    (output / "mbedtls").mkdir(exist_ok=True)
    (output / "mbedtls/base64.h").write_text(
        "#include <stddef.h>\nint mbedtls_base64_encode(unsigned char*,size_t,size_t*,const unsigned char*,size_t);\n")
    subprocess.run(["cc", *debug_flags, "-I", str(cjson), "-c", str(cjson/"cJSON.c"), "-o", str(output/"cJSON.o")], check=True)
    subprocess.run(["cc", *debug_flags, "-I", str(ROOT/"firmware/esp32-linx/main"), "-c",
                    str(ROOT/"firmware/esp32-linx/main/water_policy.c"), "-o", str(output/"water_policy.o")], check=True)
    executable = output / "firmware_host"
    subprocess.run(["c++", "-std=c++17", *debug_flags, "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
                    "-I", str(output), "-I", str(cjson), "-I", str(board),
                    "-I", str(ROOT/"firmware/esp32-audio/tests"), "-I", str(ROOT/"firmware/esp32-linx/main"),
                    str(ROOT/"firmware/esp32-audio/tests/firmware_host.cc"),
                    str(output/"cJSON.o"), str(output/"water_policy.o"), "-o", str(executable)], check=True)
    paths = [board/name for name in names] + [ROOT/"firmware/esp32-audio/tests/receipt_host.h", source/"main/mcp_server.cc", source/"main/mcp_server.h", board/"cybertrack_tools.cc",
             ROOT/"firmware/esp32-audio/tests/firmware_host.cc", Path(__file__).resolve()]
    catalog = json.loads(subprocess.check_output([str(executable),"--catalog"],text=True))
    formats = []
    for name in ("self.tank.sequence","self.tank.compose"):
        properties = next(t for t in catalog if t["name"]==name)["inputSchema"]["properties"]
        formats.append("native_array" if properties.get("steps",{}).get("type")=="array" else
                       "legacy_string" if properties.get("steps_json",{}).get("type")=="string" else "unknown")
    if formats[0]!=formats[1] or formats[0]=="unknown": raise ValueError("unknown/inconsistent step contract")
    catalog_file=output/"tool-catalog.json"
    catalog_file.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n")
    manifest = dict(scope="Full MCP dispatcher and actual callbacks; immediate or explicitly deferred host schedule; simulated input/time/distance; zero board IO",
                    step_argument_format=formats[0],tool_catalog_sha256=hashlib.sha256(catalog_file.read_bytes()).hexdigest(),
                    sanitizers=sanitize,
                    executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(executable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--idf", type=Path, default=Path.home()/"esp/esp-idf")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sanitize", action="store_true", help="instrument the entire host and C dependencies with ASan/UBSan")
    args = parser.parse_args()
    build(args.source, args.idf, args.output,args.sanitize)
