#!/usr/bin/env python3
"""Apply the bounded motor/water adapter to a disposable export of the pinned source.

Never edits the upstream checkout. See README.md for export/build instructions.
"""
from pathlib import Path
import argparse
import shutil
from feedback_overlay import apply as apply_feedback_overlay
from audio_overlay import apply as apply_audio_overlay
from display_overlay import apply as apply_display_overlay

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


BOOT_CALLBACK = '        boot_button_.OnClick([this]() {\n            auto& app = Application::GetInstance();\n            if (app.GetDeviceState() == kDeviceStateStarting && !WifiStation::GetInstance().IsConnected()) {\n                ResetWifiConfiguration();\n            }\n            app.ToggleChatState();\n        });\n'
ACTION_ARGUMENT_CHECK = r'''    if (tool_name == "self.tank.bubbles" || tool_name == "self.tank.ignition" || tool_name == "self.tank.frenzy") {
        const cJSON* duration = cJSON_GetObjectItemCaseSensitive(tool_arguments, "duration_ms");
        const int max_ms = tool_name == "self.tank.ignition" ? 5000 : 30000;
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 1 ||
            !cJSON_IsNumber(duration) || !(duration->valuedouble >= 1 && duration->valuedouble <= max_ms) ||
            duration->valuedouble != duration->valueint) {
            ReplyError(id, "Effect requires exactly integer duration_ms within its limit");
            return;
        }
    }
    if (tool_name == "self.tank.water") {
        const cJSON* duration = cJSON_GetObjectItemCaseSensitive(tool_arguments, "duration_ms");
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 1 ||
            !cJSON_IsNumber(duration) ||
            !(duration->valuedouble >= 1 && duration->valuedouble <= 30000) ||
            duration->valuedouble != duration->valueint) {
            ReplyError(id, "Water requires exactly integer duration_ms in 1..30000");
            return;
        }
    }
    if (tool_name == "self.tank.move") {
        const cJSON* duration = cJSON_GetObjectItemCaseSensitive(tool_arguments, "duration_ms");
        const cJSON* speed = cJSON_GetObjectItemCaseSensitive(tool_arguments, "speed_percent");
        const cJSON* direction = cJSON_GetObjectItemCaseSensitive(tool_arguments, "direction");
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != (speed ? 3 : 2) ||
            (speed && (!cJSON_IsNumber(speed) || !(speed->valuedouble >= 60 && speed->valuedouble <= 100) || speed->valuedouble != speed->valueint)) ||
            !cJSON_IsNumber(duration) || !(duration->valuedouble >= 1 && duration->valuedouble <= 2147483647) ||
            duration->valuedouble != duration->valueint || !cJSON_IsString(direction) ||
            (strcmp(direction->valuestring, "forward") && strcmp(direction->valuestring, "backward") &&
             strcmp(direction->valuestring, "left") && strcmp(direction->valuestring, "right"))) {
            ReplyError(id, "Move requires direction forward/backward/left/right and integer duration_ms in 1..2147483647");
            return;
        }
    }
    if (tool_name == "self.tank.move_and_water") {
        const cJSON* move = cJSON_GetObjectItemCaseSensitive(tool_arguments, "move_duration_ms");
        const cJSON* speed = cJSON_GetObjectItemCaseSensitive(tool_arguments, "speed_percent");
        const cJSON* water = cJSON_GetObjectItemCaseSensitive(tool_arguments, "water_duration_ms");
        const cJSON* direction = cJSON_GetObjectItemCaseSensitive(tool_arguments, "direction");
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != (speed ? 4 : 3) ||
            (speed && (!cJSON_IsNumber(speed) || !(speed->valuedouble >= 60 && speed->valuedouble <= 100) || speed->valuedouble != speed->valueint)) ||
            !cJSON_IsNumber(move) || !(move->valuedouble >= 1 && move->valuedouble <= 2147483647) || move->valuedouble != move->valueint ||
            !cJSON_IsNumber(water) || !(water->valuedouble >= 1 && water->valuedouble <= 30000) || water->valuedouble != water->valueint ||
            !cJSON_IsString(direction) ||
            (strcmp(direction->valuestring, "forward") && strcmp(direction->valuestring, "backward") &&
             strcmp(direction->valuestring, "left") && strcmp(direction->valuestring, "right"))) {
            ReplyError(id, "Combined action requires direction, integer move_duration_ms in 1..2147483647 and water_duration_ms in 1..30000");
            return;
        }
    }
    if (tool_name == "self.tank.set_speed") {
        const cJSON* speed = cJSON_GetObjectItemCaseSensitive(tool_arguments, "speed_percent");
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 1 ||
            !cJSON_IsNumber(speed) || !(speed->valuedouble >= 60 && speed->valuedouble <= 100) ||
            speed->valuedouble != speed->valueint) {
            ReplyError(id, "Set speed requires exactly integer speed_percent in 60..100"); return;
        }
    }
    if (tool_name == "self.tank.adjust_speed") {
        const cJSON* delta = cJSON_GetObjectItemCaseSensitive(tool_arguments, "delta_percent");
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 1 ||
            !cJSON_IsNumber(delta) || (delta->valuedouble != 10 && delta->valuedouble != -10)) {
            ReplyError(id, "Speed adjustment requires delta_percent of exactly 10 or -10"); return;
        }
    }
    if (tool_name == "self.tank.compose") {
        ShowDraft::Command edit;
        if (!ParseShowEdit(tool_arguments, edit)) { ReplyError(id, "Invalid show draft edit"); return; }
    }
    if (tool_name == "self.tank.sequence") {
        const cJSON* steps = cJSON_GetObjectItemCaseSensitive(tool_arguments, "steps_json");
        ActionPlan plan;
        if (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 1 ||
            !cJSON_IsString(steps) || !ParseActionPlan(steps->valuestring, plan)) {
            ReplyError(id, "Sequence requires exactly steps_json with 1..16 valid steps");
            return;
        }
    }
    if (tool_name == "self.tank.stop") CyberTrackActionStop();
    if (cybertrack || tool_name == "self.tank.water" || tool_name == "self.tank.move" || tool_name == "self.tank.move_and_water" || tool_name == "self.tank.bubbles" || tool_name == "self.tank.ignition" || tool_name == "self.tank.frenzy" || tool_name == "self.tank.sequence" || tool_name == "self.tank.adjust_speed" || tool_name == "self.tank.set_speed")
        ESP_LOGI("CT_AUDIO", "RPC id=%d tool=%s", id, tool_name.c_str());'''


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"Unexpected/already modified source: {path.name}")
    path.write_text(text.replace(old, new, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_relative_to(ROOT / "build") or (source / ".git").exists():
        parser.error("source must be a disposable non-Git directory inside this project's build/")
    board = source / "main/boards/bread-compact-wifi"
    replace_once(source / "CMakeLists.txt", 'set(PROJECT_VER "2.0.3")',
                 'set(PROJECT_VER "2.0.3-ct49")')
    replace_once(board / "compact_wifi_board.cc", '#include "lamp_controller.h"',
                 '#include "cybertrack_tools.h"')
    replace_once(board / "compact_wifi_board.cc", 'static LampController lamp(LAMP_GPIO);',
                 'InitializeCyberTrackTools();')
    # Restrict schemas and validation to CyberTrack tools.
    replace_once(source / "main/mcp_server.h",
                 'cJSON_AddItemToObject(input_schema, "properties", properties);',
                 'cJSON_AddItemToObject(input_schema, "properties", properties);\n'
                 '        if (name_ == "self.tank.compose" || name_ == "self.tank.get_status" || name_ == "self.tank.stop" || name_ == "self.tank.water" || name_ == "self.tank.move" || name_ == "self.tank.move_and_water" || name_ == "self.tank.bubbles" || name_ == "self.tank.ignition" || name_ == "self.tank.frenzy" || name_ == "self.tank.sequence" || name_ == "self.tank.adjust_speed" || name_ == "self.tank.set_speed") {\n'
                 '            cJSON_AddBoolToObject(input_schema, "additionalProperties", false);\n'
                 '        }')
    replace_once(source / "main/mcp_server.cc", '    PropertyList arguments = (*tool_iter)->properties();',
                 '    const bool cybertrack = tool_name == "self.tank.get_status" || tool_name == "self.tank.stop";\n'
                 '    if (cybertrack && tool_arguments && (!cJSON_IsObject(tool_arguments) || cJSON_GetArraySize(tool_arguments) != 0)) {\n'
                 '        ReplyError(id, "CyberTrack tools require empty arguments");\n'
                 '        return;\n'
                 '    }\n'
                 '    if (cybertrack) ESP_LOGI("CT_AUDIO", "RPC id=%d tool=%s", id, tool_name.c_str());\n'
                 '    PropertyList arguments = (*tool_iter)->properties();')
    replace_once(source / "main/mcp_server.cc", '#include "mcp_server.h"',
                 '#include "mcp_server.h"\n#include "boards/bread-compact-wifi/cybertrack_tools.h"\n#include "boards/bread-compact-wifi/action_plan_json.h"\n#include "boards/bread-compact-wifi/show_command_json.h"')
    replace_once(source / "main/mcp_server.cc",
                 '    if (cybertrack) ESP_LOGI("CT_AUDIO", "RPC id=%d tool=%s", id, tool_name.c_str());',
                 ACTION_ARGUMENT_CHECK)
    replace_once(source / "main/mcp_server.cc",
                 '    // Use main thread to call the tool',
                 '    if (tool_name == "self.tank.compose" || tool_name == "self.tank.set_speed" || tool_name == "self.tank.adjust_speed" || tool_name == "self.tank.sequence" || tool_name == "self.tank.water" || tool_name == "self.tank.move" || tool_name == "self.tank.move_and_water" || tool_name == "self.tank.bubbles" || tool_name == "self.tank.ignition" || tool_name == "self.tank.frenzy") {\n'
                 '        int ticket = CyberTrackActionClaim(id, tool_name.c_str());\n'
                 '        if (!ticket) { ReplyError(id, "Action request duplicate, channel busy or cooling, offline, queue full, or cancelled by web priority"); return; }\n'
                 '        arguments.AddProperty(Property("_ct_ticket", kPropertyTypeInteger, ticket));\n'
                 '    }\n'
                 '    // Use main thread to call the tool')
    replace_once(board / "compact_wifi_board.cc", '    Button boot_button_;\n', '')
    replace_once(board / "compact_wifi_board.cc", '        boot_button_(BOOT_BUTTON_GPIO),\n', '')
    replace_once(board / "compact_wifi_board.cc", BOOT_CALLBACK, '')
    app = source / "main/application.cc"
    replace_once(app, '#include "application.h"',
                 '#include "application.h"\n#include "boards/bread-compact-wifi/cybertrack_tools.h"')
    replace_once(app, '    protocol_->OnNetworkError([this](const std::string& message) {',
                 '    protocol_->OnNetworkError([this](const std::string& message) {\n        CyberTrackActionLink(false);')
    replace_once(app, '    protocol_->OnAudioChannelOpened([this, codec, &board]() {',
                 '    protocol_->OnAudioChannelOpened([this, codec, &board]() {\n        CyberTrackActionLink(true);')
    replace_once(app, '    protocol_->OnAudioChannelClosed([this, &board]() {',
                 '    protocol_->OnAudioChannelClosed([this, &board]() {\n        CyberTrackActionLink(false);')
    replace_once(app, 'void Application::Reboot() {',
                 'void Application::Reboot() {\n    CyberTrackShutdown();')
    replace_once(app, 'bool Application::UpgradeFirmware(Ota& ota, const std::string& url) {',
                 'bool Application::UpgradeFirmware(Ota& ota, const std::string& url) {\n    CyberTrackShutdown();')
    replace_once(source / "main/protocols/websocket_protocol.cc", '#include "websocket_protocol.h"',
                 '#include "websocket_protocol.h"\n#include "boards/bread-compact-wifi/cybertrack_tools.h"')
    replace_once(source / "main/protocols/websocket_protocol.cc", 'void WebsocketProtocol::CloseAudioChannel() {',
                 'void WebsocketProtocol::CloseAudioChannel() {\n    CyberTrackActionLink(false);')
    for name in ("water_policy.h", "water_policy.c"):
        shutil.copy2(ROOT / "firmware/esp32-linx/main" / name, board / name)
    apply_feedback_overlay(source, replace_once)
    apply_audio_overlay(source, replace_once)
    apply_display_overlay(source, replace_once)
    for name in ("status_facts.h", "voice_feedback.h", "show_draft.h", "show_command_json.h", "recent_command.h", "proximity_guard.h", "proximity_audio.h", "proximity_audio.cc", "distance_reading.h", "ultrasonic.h", "ultrasonic.cc", "cybertrack_state.h", "cybertrack_tools.h", "cybertrack_tools.cc", "water_guard.h", "action_guard.h", "action_plan.h", "action_plan_json.h", "action_outputs.h", "control_sessions.h", "web_request.h", "web_server.h", "web_server.cc"):
        shutil.copy2(HERE / name, board / name)
    sounds = '#pragma once\n'
    for key, filename in (("ProximityBeep", "range-beep.ogg"), ("ProximityStop", "range-stop.ogg")):
        data = (HERE / "sounds" / filename).read_bytes()
        sounds += 'static const unsigned char ' + key + '[] = {' + ','.join(str(b) for b in data) + '};\n'
    (board / "proximity_sounds.h").write_text(sounds)
    page = (HERE / "web/index.html").read_text()
    if ')CTWEB"' in page:
        raise SystemExit("Page contains reserved raw-string delimiter")
    (board / "web_page.h").write_text('#pragma once\nstatic const char CyberTrackPage[] = R"CTWEB(' + page + ')CTWEB";\n')
    (board / "cybertrack").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "firmware/include/cybertrack/control.h", board / "cybertrack/control.h")
    shutil.copy2(ROOT / "firmware/src/control.c", board / "cybertrack_control.c")
    config = source / "sdkconfig"
    replace_once(config, 'CONFIG_FREERTOS_HZ=100\n', 'CONFIG_FREERTOS_HZ=1000\n')
    replace_once(config, '# CONFIG_ESP_TASK_WDT_PANIC is not set', 'CONFIG_ESP_TASK_WDT_PANIC=y')
    replace_once(config, 'CONFIG_ESP_TASK_WDT_TIMEOUT_S=10', 'CONFIG_ESP_TASK_WDT_TIMEOUT_S=2')
    print("Applied bounded motor + water/bubbles/ignition bench; BOOT stops all; audio/display pins unchanged")


if __name__ == "__main__":
    main()
