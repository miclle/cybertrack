"""Local configuration validation and generated NVS bootstrap behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wifi_config import ROOT, apply_config, load_config, render_header


class WifiConfigTest(unittest.TestCase):
    def load(self, value):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wifi.json"
            path.write_text(json.dumps(value))
            return load_config(path)

    def test_validation(self):
        network = {"ssid": '家里"\\WiFi', "password": 'pa"ss\\word'}
        self.assertEqual(self.load({"networks": [network]}), [network])
        self.load({"networks": [{"ssid": "open", "password": ""}]})
        for value in (
            {"networks": []}, {"networks": [network] * 11},
            {"networks": [network, network]},
            {"networks": [{"ssid": "x", "password": "short"}]},
            {"networks": [{"ssid": "界" * 11, "password": "12345678"}]},
            {"networks": [{"ssid": "x\0y", "password": "12345678"}]},
            {"networks": [{"ssid": "x", "password": "12345678", "username": "u"}]},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(value)

    def test_export(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as directory:
            source = Path(directory)
            board = source / "main/boards/common/wifi_board.cc"
            board.parent.mkdir(parents=True)
            board.write_text("WifiBoard::WifiBoard() {\n}\n")
            component = source / "locked_components/78__esp-wifi-connect"
            (component / "include").mkdir(parents=True)
            (component / "include/wifi_station.h").write_text("struct WifiApRecord {\n};\n")
            (component / "wifi_station.cc").write_text(
                "#define MAX_RECONNECT_COUNT 5\nvoid WifiStation::HandleScanResult() {\n}\n"
                "void WifiStation::StartConnect() {\n    ssid_ = ap_record.ssid;\n}\n")
            (source / "CMakeLists.txt").write_text('set(PROJECT_VER "2.0.3-ct39")\n')
            apply_config(source, [{"ssid": "test", "password": "12345678"}])
            self.assertIn("ApplyCyberTrackWifiConfig();", board.read_text())
            self.assertIn("2.0.3-ct39-wifi-order3", (source / "CMakeLists.txt").read_text())
            self.assertEqual((board.parent / "cybertrack_wifi_config.h").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                apply_config(source, [{"ssid": "test", "password": "12345678"}])

    def test_generated_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.h").write_text(render_header([
                {"ssid": '家里"\\WiFi', "password": 'pa"ss\\word'},
                {"ssid": "backup", "password": "12345678"},
            ]))
            (root / "esp_err.h").write_text('''#pragma once
#include <stdexcept>
using esp_err_t = int;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 1
#define ESP_ERROR_CHECK(call) do { if ((call) != ESP_OK) throw std::runtime_error("NVS error"); } while (0)
''')
            (root / "nvs.h").write_text('''#pragma once
#include "esp_err.h"
#include <map>
#include <string>
#include <cstring>
using nvs_handle_t = int;
#define NVS_READWRITE 1
inline std::map<std::string, std::string> values;
inline int writes = 0, commits = 0;
inline bool fail_commit = false;
inline int nvs_open(const char*, int, int* h) { *h = 1; return 0; }
inline int nvs_get_str(int, const char* k, char* v, size_t* n) {
 auto it = values.find(k); if (it == values.end()) return 1;
 if (*n < it->second.size()+1) return 2;
 strcpy(v, it->second.c_str()); return 0;
}
inline int nvs_set_str(int, const char* k, const char* v) { values[k] = v; ++writes; return 0; }
inline int nvs_erase_key(int, const char* k) { ++writes; return values.erase(k) ? 0 : 1; }
inline int nvs_commit(int) { ++commits; return fail_commit ? 2 : 0; }
inline void nvs_close(int) {}
''')
            (root / "test.cc").write_text(r'''#include "config.h"
#include <cassert>
int main() {
 values = {{"ssid9", "old"}, {"password9", "oldpassword"}, {"max_tx_power", "20"}};
 ApplyCyberTrackWifiConfig();
 assert(values["ssid"] == "家里\"\\WiFi");
 assert(values["password"] == "pa\"ss\\word");
 assert(values["ssid1"] == "backup");
 assert(!values.count("ssid9") && !values.count("password9"));
 assert(values["max_tx_power"] == "20");
 assert(commits == 2);
 int before = writes;
 values["ssid"] = "changed-in-portal";
 ApplyCyberTrackWifiConfig();
 assert(writes == before && commits == 2);
 assert(values["ssid"] == "changed-in-portal");
 values["ct_wifi_seed"] = "older-revision";
 fail_commit = true;
 try { ApplyCyberTrackWifiConfig(); assert(false); } catch (const std::runtime_error&) {}
 assert(values["ct_wifi_seed"] == "older-revision");
 fail_commit = false;
 ApplyCyberTrackWifiConfig();
 assert(values["ssid"] == "家里\"\\WiFi");
}
''')
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(root),
                            str(root / "test.cc"), "-o", str(root / "test")], check=True)
            subprocess.run([str(root / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
