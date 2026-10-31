"""Reject lossy robot JSON at original message boundaries, before admission."""


def apply(source, replace):
    header = source / 'main/mcp_server.h'
    server = source / 'main/mcp_server.cc'
    replace(header, '    void ParseMessage(const std::string& message);',
            '    void ParseMessage(const std::string& message);\n    void RejectRobotInput(int id);')
    replace(server, '#include "mcp_server.h"',
            '#include "mcp_server.h"\n#include "boards/bread-compact-wifi/mcp_raw_json.h"')
    replace(server, 'void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments) {',
            '''void McpServer::RejectRobotInput(int id) {
    CyberTrackVoiceFailure(CyberTrackVoiceTurn());
    ReplyError(id, "Robot input contains an embedded zero");
}

void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments) {''')
    replace(server, '    ParseMessage(json);', '''    int invalid_robot_id = 0;
    if (RejectZeroInRobotMcp(message, json, invalid_robot_id)) RejectRobotInput(invalid_robot_id);
    else ParseMessage(json);''')
    for filename, include, anchor, raw, indent in (
        ('websocket_protocol.cc', 'websocket_protocol.h',
         '            auto type = cJSON_GetObjectItem(root, "type");', 'std::string_view(data, len)', '            '),
        ('mqtt_protocol.cc', 'mqtt_protocol.h',
         '        cJSON* type = cJSON_GetObjectItem(root, "type");', 'payload', '        '),
    ):
        protocol = source / ('main/protocols/' + filename)
        replace(protocol, '#include "' + include + '"',
                '#include "' + include + '"\n#if CONFIG_ENABLE_MCP\n#include "mcp_server.h"\n#include "boards/bread-compact-wifi/mcp_raw_json.h"\n#endif')
        replace(protocol, anchor, anchor + '\n#if CONFIG_ENABLE_MCP\n' + indent + 'int invalid_robot_id = 0;\n' +
                indent + 'if (RejectZeroInRobotMcp(' + raw + ', root, invalid_robot_id)) {\n' +
                indent + '    McpServer::GetInstance().RejectRobotInput(invalid_robot_id);\n' +
                indent + '    cJSON_Delete(root);\n' + indent + '    return;\n' + indent + '}\n#endif')
