#pragma once
#include <cstdint>
#include <string>
#include "web_request.h"
void InitializeCyberTrackWeb();
uint32_t CyberTrackWebAcquire();
struct WebReply {
    std::string body;
    bool session_expired = false;
};
WebReply CyberTrackWebCall(uint32_t session, const char* operation, const WebCommand* command = nullptr);
