"""Bind remote tool requests to recognized input and latch failures on device."""


def apply(source, replace):
    app = source / 'main/application.cc'
    replace(app, 'cybertrack_feedback.Input(text->valuestring);',
            'CyberTrackVoiceInput(text->valuestring);\n                cybertrack_feedback.Input(text->valuestring);')
    path = source / 'main/mcp_server.cc'
    text = path.read_text()
    signature = 'void McpServer::DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments) {'
    body = text[text.index(signature):]
    if body.count(signature) != 1 or not body.rstrip().endswith('}'):
        raise ValueError('unexpected tool dispatch boundary')
    updated = body.replace('ReplyError(id, ', 'reject(')
    updated = updated.replace(signature, signature + '''
    const bool robot_tool = tool_name.compare(0, 10, "self.tank.") == 0;
    const int voice_turn = robot_tool ? CyberTrackVoiceTurn() : -1;
    auto reject = [this, id, voice_turn, robot_tool](const std::string& message) {
        if (robot_tool) CyberTrackVoiceFailure(voice_turn);
        ReplyError(id, message);
    };''', 1)
    updated = updated.replace('CyberTrackActionClaim(id, tool_name.c_str(), &admission_error)',
                              'CyberTrackActionClaim(id, tool_name.c_str(), &admission_error, voice_turn)')
    updated = updated.replace('    // Use main thread to call the tool',
                              '    if (robot_tool) arguments.AddProperty(Property("_ct_turn", kPropertyTypeInteger, voice_turn));\n'
                              '    // Use main thread to call the tool', 1)
    updated = updated.replace('[this, id, feedback_call, tool_iter, arguments =',
                              '[this, id, voice_turn, robot_tool, reject, feedback_call, tool_iter, arguments =', 1)
    updated = updated.replace('(*tool_iter)->Call(arguments, feedback_call ? &receipt : nullptr)',
                              '(*tool_iter)->Call(arguments, (robot_tool || feedback_call) ? &receipt : nullptr)', 1)
    updated = updated.replace('            cybertrack_feedback.Receipt(feedback_call, receipt.c_str());',
                              '            if (robot_tool) CyberTrackVoiceResult(voice_turn, receipt.c_str());\n'
                              '            cybertrack_feedback.Receipt(feedback_call, receipt.c_str());', 1)
    replace(path, body, updated)
