#!/usr/bin/env python3
"""Execute actual exported Wi-Fi selection and event methods against driver stubs."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def method(source, name):
    start = source.index("void WifiStation::" + name + "(")
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
source = (args.source / "locked_components/78__esp-wifi-connect/wifi_station.cc").read_text()
retry = re.search(r"#define MAX_RECONNECT_COUNT (\d+)", source)[0]
methods = '\n'.join(method(source, name) for name in (
    "HandleScanResult", "StartConnect", "WifiEventHandler", "IpEventHandler"))
stub = r'''
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>
#include <vector>
#define ESP_OK 0
#define ESP_ERROR_CHECK(x) assert((x) == 0)
#define ESP_LOGI(...) ((void)0)
template<class... Args> void log_warning(Args...) {}
#define ESP_LOGW(...) log_warning(__VA_ARGS__)
#define WIFI_IF_STA 0
#define WIFI_EVENT_CONNECTED 1
enum { WIFI_EVENT_STA_START, WIFI_EVENT_SCAN_DONE, WIFI_EVENT_STA_DISCONNECTED, WIFI_EVENT_STA_CONNECTED };
using esp_event_base_t = int;
struct wifi_ap_record_t { uint8_t ssid[33] = {}; uint8_t bssid[6] = {}; int8_t rssi = 0; int primary = 0, authmode = 0; };
struct wifi_config_t { struct { char ssid[32], password[64]; int channel; uint8_t bssid[6]; bool bssid_set; } sta; };
struct ip_event_got_ip_t { struct { int ip; } ip_info; };
struct wifi_event_sta_disconnected_t { uint8_t reason; };
struct SsidItem { std::string ssid, password; };
struct SsidManager {
 std::vector<SsidItem> entries;
 static SsidManager& GetInstance() { static SsidManager manager; return manager; }
 const std::vector<SsidItem>& GetSsidList() { return entries; }
};
struct WifiApRecord { int config_index; std::string ssid, password; int channel, authmode; uint8_t bssid[6]; };
std::vector<wifi_ap_record_t> radios;
std::vector<std::string> attempts;
wifi_config_t config{};
int connects = 0, scans = 0, bits = 0;
int64_t scheduled_us = 0;
int esp_wifi_scan_get_ap_num(uint16_t* n) { *n = radios.size(); return 0; }
int esp_wifi_scan_get_ap_records(uint16_t* n, wifi_ap_record_t* p) { std::copy_n(radios.begin(), *n, p); return 0; }
int esp_wifi_set_config(int, wifi_config_t* p) { config = *p; return 0; }
int esp_wifi_connect() { ++connects; attempts.push_back(config.sta.ssid); return 0; }
void esp_wifi_scan_start(void*, bool) { ++scans; }
void esp_timer_start_once(int, int64_t us) { scheduled_us = us; }
void xEventGroupClearBits(int, int b) { bits &= ~b; }
void xEventGroupSetBits(int, int b) { bits |= b; }
void esp_ip4addr_ntoa(int*, char* dest, size_t) { strcpy(dest, "127.0.0.1"); }
class WifiStation {
public:
 std::vector<WifiApRecord> connect_queue_;
 std::string ssid_, password_, ip_address_;
 int event_group_ = 0, timer_handle_ = 0, reconnect_count_ = 0, config_index_ = 0;
 bool remember_bssid_ = true;
 std::function<void()> on_scan_begin_;
 std::function<void(const std::string&)> on_connect_, on_connected_;
 void HandleScanResult(); void StartConnect();
 static void WifiEventHandler(void*, esp_event_base_t, int32_t, void*);
 static void IpEventHandler(void*, esp_event_base_t, int32_t, void*);
};
'''
tests = r'''
wifi_ap_record_t ap(const char* ssid, int rssi, int radio) {
 wifi_ap_record_t result{}; strcpy((char*)result.ssid, ssid);
 result.rssi = rssi; result.bssid[5] = radio; result.primary = 6; return result;
}
void failed(WifiStation& station) {
 wifi_event_sta_disconnected_t event{201};
 WifiStation::WifiEventHandler(&station, 0, WIFI_EVENT_STA_DISCONNECTED, &event);
}
int main() {
 SsidManager::GetInstance().entries = {{"first", "password1"}, {"second", "password2"}};
 // Second network is much stronger; duplicate first-network radios must not
 // create extra candidates or delay fallback to the second network.
 radios = {ap("second", -20, 1), ap("first", -80, 2), ap("first", -60, 3), ap("unknown", -10, 4)};
 WifiStation station;
 station.HandleScanResult();
 assert(attempts == std::vector<std::string>{"first"});
 assert(config.sta.bssid[5] == 3);
 assert(station.connect_queue_.size() == 1);
 failed(station);
 assert((attempts == std::vector<std::string>{"first", "second"}));
 assert(!strcmp(config.sta.password, "password2"));
 failed(station);
 assert(scheduled_us == 10000000 && connects == 2);
 // A new scan starts at the first configured candidate again.
 station.HandleScanResult(); assert(attempts.back() == "first");
 ip_event_got_ip_t event{};
 WifiStation::IpEventHandler(&station, 0, 0, &event);
 assert(bits == WIFI_EVENT_CONNECTED && station.connect_queue_.empty());
 const auto count = attempts.size();
 failed(station);
 assert(bits == 0 && attempts.size() == count && scheduled_us == 10000000);
 // Invisible/hidden first network gets a directed attempt before fallback.
 radios = {ap("second", -20, 1)};
 station.HandleScanResult(); assert(attempts.back() == "first");
 assert(!config.sta.bssid_set && config.sta.channel == 0);
 failed(station); assert(attempts.back() == "second");
 // Unknown radios and empty scans still try configured SSIDs directly.
 radios = {ap("unknown", -10, 4)};
 station.HandleScanResult(); assert(attempts.back() == "first");
 failed(station); assert(attempts.back() == "second"); failed(station);
 radios.clear(); station.HandleScanResult(); assert(attempts.back() == "first");
 failed(station); assert(attempts.back() == "second"); failed(station);
 assert(scheduled_us == 10000000);
 // Stored order changes must take effect, independent of RSSI.
 SsidManager::GetInstance().entries = {{"second", "password2"}, {"first", "password1"}};
 radios = {ap("first", -20, 2), ap("second", -80, 1)};
 station.HandleScanResult(); assert(attempts.back() == "second");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / "test.cc").write_text(stub + retry + '\n' + methods + tests)
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    str(path / "test.cc"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
print("PASS: exported Wi-Fi priority, duplicate AP, failure fallback, reconnect, absent/empty scan and reordered list")
