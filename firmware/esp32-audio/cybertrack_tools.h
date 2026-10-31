#pragma once
void InitializeCyberTrackTools();
void CyberTrackActionLink(bool online);
void CyberTrackActionStop();
void CyberTrackWifiLink(bool online);
void CyberTrackShutdown();
int CyberTrackVoiceTurn();
void CyberTrackVoiceInput(const char* text);
void CyberTrackVoiceFailure(int turn);
void CyberTrackVoiceResult(int turn, const char* receipt);
int CyberTrackActionClaim(int rpc_id, const char* operation, const char** error = nullptr, int turn = -1);
