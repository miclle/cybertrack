#pragma once
#include "proximity_guard.h"
void InitializeCyberTrackProximityAudio();
// Nonblocking, allocation-free; called from the control tick under its mutex.
void CyberTrackProximityAlert(ProximityGuard::Alert alert, bool beeping);
