#pragma once
#include <cstdint>
#include <string>
#include "web_request.h"
void InitializeCyberTrackWeb();
uint32_t CyberTrackWebAcquire();
std::string CyberTrackWebCall(uint32_t session, const char* operation, const WebCommand* command = nullptr);
