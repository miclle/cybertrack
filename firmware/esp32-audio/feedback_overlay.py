"""Scope remote playback to one recognized utterance and its actual MCP receipt."""

def apply(source, replace):
    board_header = '#include "boards/bread-compact-wifi/voice_feedback.h"'
    app = source / 'main/application.cc'
    server = source / 'main/mcp_server.cc'
    header = source / 'main/mcp_server.h'
    for path, anchor in ((app, '#include "application.h"'), (server, '#include "mcp_server.h"')):
        replace(path, anchor, anchor + '\n' + board_header)
    for anchor in ('CyberTrackActionLink(true);',):
        replace(app, anchor, 'cybertrack_feedback.Input("");\n        ' + anchor)
    for anchor in ('protocol_->OnNetworkError([this](const std::string& message) {',
                   'protocol_->OnAudioChannelClosed([this, &board]() {'):
        replace(app, anchor, anchor + '\n        cybertrack_feedback.Input("");')
    replace(app, 'ESP_LOGI(TAG, ">> %s", text->valuestring);',
            'cybertrack_feedback.Input(text->valuestring);\n                ESP_LOGI(TAG, ">> %s", text->valuestring);')
    for state, action in (('start', 'StartSpeech()'), ('stop', 'Input("")')):
        anchor = f'if (strcmp(state->valuestring, "{state}") == 0) {{'
        replace(app, anchor, anchor + '\n                cybertrack_feedback.' + action + ';')
    replace(app, 'audio_service_.PushPacketToDecodeQueue(std::move(packet));',
            'if (!cybertrack_feedback.Muted()) audio_service_.PushPacketToDecodeQueue(std::move(packet));')
    anchor = 'void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments) {'
    replace(server, anchor, anchor + '\n    auto feedback_call = cybertrack_feedback.BeginCall(tool_name, tool_arguments);')
    replace(server, '[this, id, tool_iter, arguments =', '[this, id, feedback_call, tool_iter, arguments =')
    replace(server, 'ReplyResult(id, (*tool_iter)->Call(arguments));',
            'std::string receipt;\n            auto result = (*tool_iter)->Call(arguments, feedback_call ? &receipt : nullptr);\n'
            '            cybertrack_feedback.Receipt(feedback_call, receipt.c_str());\n            ReplyResult(id, result);')
    replace(header, 'std::string Call(const PropertyList& properties)', 'std::string Call(const PropertyList& properties, std::string* receipt = nullptr)')
    anchor = 'cJSON_AddStringToObject(text, "text", std::get<std::string>(return_value).c_str());'
    replace(header, anchor, 'if (receipt) *receipt = std::get<std::string>(return_value);\n                ' + anchor)
