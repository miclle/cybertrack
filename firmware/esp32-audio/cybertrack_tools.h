#pragma once
void InitializeCyberTrackTools();
void CyberTrackActionLink(bool online);
void CyberTrackActionStop();
void CyberTrackWifiLink(bool online);
void CyberTrackShutdown();
int CyberTrackActionClaim(int rpc_id, const char* operation, const char** error = nullptr);
