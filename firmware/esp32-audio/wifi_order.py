"""Apply ordered ordinary Wi-Fi selection to the pinned component export."""
from pathlib import Path


SCAN_RESULT = '''void WifiStation::HandleScanResult() {
    uint16_t ap_num = 0;
    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_num(&ap_num));
    std::vector<wifi_ap_record_t> ap_records(ap_num);
    if (ap_num) {
        ESP_ERROR_CHECK(esp_wifi_scan_get_ap_records(&ap_num, ap_records.data()));
        ap_records.resize(ap_num);
    }
    const auto& ssid_list = SsidManager::GetInstance().GetSsidList();
    connect_queue_.clear();
    // Saved order comes from the JSON list. RSSI only selects a radio for one SSID.
    for (size_t index = 0; index < ssid_list.size(); ++index) {
        const auto& item = ssid_list[index];
        const wifi_ap_record_t* best = nullptr;
        for (const auto& ap : ap_records) {
            if (strcmp((const char*)ap.ssid, item.ssid.c_str()) == 0 &&
                (!best || ap.rssi > best->rssi)) {
                best = &ap;
            }
        }
        WifiApRecord record = {};
        record.ssid = item.ssid;
        record.password = item.password;
        record.config_index = int(index + 1);
        if (best) {
            record.channel = best->primary;
            record.authmode = best->authmode;
            memcpy(record.bssid, best->bssid, sizeof(record.bssid));
            ESP_LOGI("CT_WIFI", "Candidate network index=%u rssi=%d", unsigned(index + 1), best->rssi);
        } else {
            // A hidden SSID may not appear in the broadcast scan. Let the driver
            // perform a directed connection before falling back to the next entry.
            ESP_LOGI("CT_WIFI", "Candidate network index=%u directed=true", unsigned(index + 1));
        }
        connect_queue_.push_back(record);
    }
    if (connect_queue_.empty()) {
        esp_timer_start_once(timer_handle_, 10 * 1000000);
        return;
    }
    StartConnect();
}

'''


def ordered_source(text: str) -> str:
    old = "#define MAX_RECONNECT_COUNT 5"
    if text.count(old) != 1 or "config_index" in text:
        raise ValueError("Unexpected or already patched Wi-Fi station source")
    begin = text.index("void WifiStation::HandleScanResult() {")
    end = text.index("void WifiStation::StartConnect() {", begin)
    text = text[:begin] + SCAN_RESULT + text[end:]
    text = text.replace(old, "// A failed candidate yields to the next saved network.\n#define MAX_RECONNECT_COUNT 0", 1)
    text = text.replace("    ssid_ = ap_record.ssid;", '    config_index_ = ap_record.config_index;\n    ESP_LOGI("CT_WIFI", "Attempt network index=%d", config_index_);\n    ssid_ = ap_record.ssid;', 1)
    text = text.replace("if (remember_bssid_) {", "if (remember_bssid_ && ap_record.channel != 0) {", 1)
    text = text.replace("        xEventGroupClearBits(this_->event_group_, WIFI_EVENT_CONNECTED);", '''        if (event_data) {
            const auto* failure = static_cast<wifi_event_sta_disconnected_t*>(event_data);
            ESP_LOGW("CT_WIFI", "Failure network index=%d reason=%u", this_->config_index_, unsigned(failure->reason));
        }
        xEventGroupClearBits(this_->event_group_, WIFI_EVENT_CONNECTED);''', 1)
    # esp_timer takes microseconds; the upstream literal waits only 10 ms.
    text = text.replace("10 * 1000);", "10 * 1000000);")
    return text


def apply_order(source: Path) -> None:
    component = source / "locked_components/78__esp-wifi-connect"
    station = component / "wifi_station.cc"
    header = component / "include/wifi_station.h"
    updated = ordered_source(station.read_text())
    declaration = header.read_text()
    marker = "struct WifiApRecord {\n"
    if declaration.count(marker) != 1 or "config_index" in declaration:
        raise ValueError("Unexpected Wi-Fi record declaration")
    declaration = declaration.replace(marker, marker + "    int config_index;\n", 1)
    declaration = declaration.replace("    int reconnect_count_ = 0;", "    int config_index_ = 0;\n    int reconnect_count_ = 0;", 1)
    header.write_text(declaration)
    station.write_text(updated)
