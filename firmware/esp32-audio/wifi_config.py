#!/usr/bin/env python3
"""Validate local Wi-Fi credentials and seed a disposable firmware export."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from wifi_order import apply_order

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path) -> list[dict[str, str]]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ValueError("Cannot read Wi-Fi JSON; check file encoding and JSON syntax") from None
    if not isinstance(config, dict) or set(config) != {"networks"}:
        raise ValueError("Expected an object with only a networks array")
    networks = config["networks"]
    if not isinstance(networks, list) or not 1 <= len(networks) <= 10:
        raise ValueError("networks must contain 1 to 10 entries")
    seen = set()
    for index, network in enumerate(networks, 1):
        prefix = f"Network {index}: "
        if not isinstance(network, dict) or set(network) != {"ssid", "password"}:
            raise ValueError(prefix + "expected only ssid and password")
        ssid, password = network["ssid"], network["password"]
        if not isinstance(ssid, str) or not isinstance(password, str):
            raise ValueError(prefix + "ssid and password must be strings")
        try:
            ssid_bytes = ssid.encode("utf-8")
        except UnicodeError:
            raise ValueError(prefix + "invalid SSID encoding") from None
        # The pinned component uses strcpy into a 32-byte SSID buffer.
        if not 1 <= len(ssid_bytes) <= 31 or "\0" in ssid:
            raise ValueError(prefix + "SSID must be 1 to 31 UTF-8 bytes, without NUL")
        if ssid in seen:
            raise ValueError(prefix + "duplicate SSID")
        seen.add(ssid)
        if password and (not 8 <= len(password) <= 63 or
                         any(ord(c) < 32 or ord(c) > 126 for c in password)):
            raise ValueError(prefix + "password must be 8 to 63 printable ASCII characters, or empty for an open network")
    return networks


def cpp_string(value: str) -> str:
    # Fixed-width octal escapes avoid C++ quoting and UTF-8 source ambiguity.
    return '"' + ''.join(f"\\{byte:03o}" for byte in value.encode("utf-8")) + '"'


def render_header(networks: list[dict[str, str]]) -> str:
    digest = hashlib.sha256(json.dumps(networks, ensure_ascii=True, sort_keys=True).encode()).hexdigest()
    entries = ",\n".join("    {" + cpp_string(n["ssid"]) + ", " + cpp_string(n["password"]) + "}" for n in networks)
    return '''// Generated local credentials: keep this file and firmware private.
#pragma once
#include <cstring>
#include <cstdio>
#include <initializer_list>
#include <nvs.h>
#include <esp_err.h>

inline void ApplyCyberTrackWifiConfig() {
    const char* credentials[][2] = {
''' + entries + '''
    };
    const char* revision = "''' + digest + '''";
    nvs_handle_t handle;
    ESP_ERROR_CHECK(nvs_open("wifi", NVS_READWRITE, &handle));
    char previous[65] = {};
    size_t length = sizeof(previous);
    if (nvs_get_str(handle, "ct_wifi_seed", previous, &length) == ESP_OK &&
        strcmp(previous, revision) == 0) {
        nvs_close(handle);
        return;
    }
    for (int i = 0; i < 10; ++i) {
        char ssid_key[16] = "ssid", password_key[16] = "password";
        if (i > 0) {
            snprintf(ssid_key, sizeof(ssid_key), "ssid%d", i);
            snprintf(password_key, sizeof(password_key), "password%d", i);
        }
        if (i < static_cast<int>(sizeof(credentials) / sizeof(credentials[0]))) {
            ESP_ERROR_CHECK(nvs_set_str(handle, ssid_key, credentials[i][0]));
            ESP_ERROR_CHECK(nvs_set_str(handle, password_key, credentials[i][1]));
        } else {
            for (const char* key : {ssid_key, password_key}) {
                esp_err_t error = nvs_erase_key(handle, key);
                if (error != ESP_ERR_NVS_NOT_FOUND) ESP_ERROR_CHECK(error);
            }
        }
    }
    ESP_ERROR_CHECK(nvs_commit(handle));
    // Mark only after the complete list has been committed; retry after interruption.
    ESP_ERROR_CHECK(nvs_set_str(handle, "ct_wifi_seed", revision));
    ESP_ERROR_CHECK(nvs_commit(handle));
    nvs_close(handle);
}
'''


def apply_config(source: Path, networks: list[dict[str, str]]) -> None:
    source = source.resolve()
    if not source.is_relative_to(ROOT / "build") or (source / ".git").exists():
        raise ValueError("Wi-Fi export must be a disposable directory inside build/")
    board = source / "main/boards/common/wifi_board.cc"
    text = board.read_text()
    marker = "WifiBoard::WifiBoard() {"
    if text.count(marker) != 1 or "ApplyCyberTrackWifiConfig" in text:
        raise ValueError("Unexpected or already configured Wi-Fi board source")
    cmake = source / "CMakeLists.txt"
    cmake_text = cmake.read_text()
    pattern = r'set\(PROJECT_VER "(2\.0\.3-ct[0-9]+)"\)'
    if len(re.findall(pattern, cmake_text)) != 1:
        raise ValueError("Expected a versioned CyberTrack export")
    apply_order(source)
    header = board.parent / "cybertrack_wifi_config.h"
    header.write_text(render_header(networks))
    header.chmod(0o600)
    board.write_text('#include "cybertrack_wifi_config.h"\n' + text.replace(
        marker, marker + "\n    ApplyCyberTrackWifiConfig();", 1))
    cmake.write_text(re.sub(pattern, r'set(PROJECT_VER "\1-wifi-order3")', cmake_text))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    try:
        networks = load_config(args.config)
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    print(f"Valid: {len(networks)} Wi-Fi networks; credentials not displayed; device unchanged")


if __name__ == "__main__":
    main()
