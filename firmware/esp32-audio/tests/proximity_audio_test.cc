#include "../proximity_audio.cc"
#include <iostream>
using A = ProximityGuard;
static void reset() {
    sound_mock::now=sound_mock::ready_at=0;
    sound_mock::queued=false; sound_mock::played.clear(); sound_mock::before_play={}; beeping=false;
    sound_mock::range_allowed=true;
}
static void run() {try {sound_mock::task(nullptr);} catch(const sound_mock::Done&) {}}
int main() {
    InitializeCyberTrackProximityAudio();
    reset(); CyberTrackProximityAlert(A::Beep,true); run();
    assert(sound_mock::played==std::vector<std::string>{"b"});
    reset(); sound_mock::range_allowed=false;
    CyberTrackProximityAlert(A::Beep,true); run();
    assert(sound_mock::played.empty()); // Dialogue drops the ordinary event, never queues catch-up.
    sound_mock::range_allowed=true; run(); assert(sound_mock::played.empty());
    sound_mock::now=400; CyberTrackProximityAlert(A::Beep,true); run();
    assert(sound_mock::played==std::vector<std::string>{"b"}); // A fresh ordinary event resumes.
    reset(); sound_mock::range_allowed=false;
    CyberTrackProximityAlert(A::Stop,false); run();
    assert(sound_mock::played==std::vector<std::string>{"s"}); // Dialogue cannot suppress a stop warning.
    reset(); CyberTrackProximityAlert(A::Beep,true); CyberTrackProximityAlert(A::None,false); run();
    assert(sound_mock::played.empty()); // Invalid/far data cancels a queued ordinary beep.
    reset(); CyberTrackProximityAlert(A::Beep,true); sound_mock::now=251; run();
    assert(sound_mock::played.empty());
    reset(); CyberTrackProximityAlert(A::Beep,true); CyberTrackProximityAlert(A::Stop,false);
    CyberTrackProximityAlert(A::Beep,true); CyberTrackProximityAlert(A::None,false); run();
    assert(sound_mock::played==std::vector<std::string>{"s"}); // Critical event survives, and overrides normal.
    reset(); CyberTrackProximityAlert(A::Stop,false); sound_mock::now=1001; run();
    assert(sound_mock::played.empty());
    reset(); CyberTrackProximityAlert(A::Stop,false); sound_mock::ready_at=2000; run();
    assert(sound_mock::played.empty()); // Do not replay old events after audio startup.
    reset(); CyberTrackProximityAlert(A::Beep,true);
    sound_mock::before_play=[] {
        if(sound_mock::played.size()==1) {
            sound_mock::now+=180;
            CyberTrackProximityAlert(A::Stop,false);
            CyberTrackProximityAlert(A::None,false);
        }
    };
    run(); assert(sound_mock::played==(std::vector<std::string>{"b","s"}));
    reset(); CyberTrackProximityAlert(A::Stop,false);
    sound_mock::before_play=[] {
        if(sound_mock::played.size()==1) {
            sound_mock::now+=400;
            CyberTrackProximityAlert(A::Beep,true);
        }
    };
    run(); assert(sound_mock::played==(std::vector<std::string>{"s","b"}));
    std::cout<<"actual tone worker: cancellation, expiry, critical priority, startup silence and one-shot stop PASS\n";
}
