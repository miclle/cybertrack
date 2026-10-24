#!/usr/bin/env python3
"""Apply the no-actuator adapter to a disposable export of the pinned source.

Never edits the upstream checkout. See README.md for export/build instructions.
"""
from pathlib import Path
import argparse
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


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
                 'set(PROJECT_VER "2.0.3-ct2")')
    replace_once(board / "compact_wifi_board.cc", '#include "lamp_controller.h"',
                 '#include "cybertrack_tools.h"')
    replace_once(board / "compact_wifi_board.cc", 'static LampController lamp(LAMP_GPIO);',
                 'InitializeCyberTrackTools();')
    # Limit validation changes to the two new empty-argument tools.
    replace_once(source / "main/mcp_server.h",
                 'cJSON_AddItemToObject(input_schema, "properties", properties);',
                 'cJSON_AddItemToObject(input_schema, "properties", properties);\n'
                 '        if (name_ == "self.tank.get_status" || name_ == "self.tank.stop") {\n'
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
    for name in ("cybertrack_state.h", "cybertrack_tools.h", "cybertrack_tools.cc"):
        shutil.copy2(HERE / name, board / name)
    (board / "cybertrack").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "firmware/include/cybertrack/control.h", board / "cybertrack/control.h")
    shutil.copy2(ROOT / "firmware/src/control.c", board / "cybertrack_control.c")
    print("Applied status/stop adapter; audio/display GPIO configuration unchanged")


if __name__ == "__main__":
    main()
