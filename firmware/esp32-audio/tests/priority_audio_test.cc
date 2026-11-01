// Executes the exported firmware's actual priority playback/queue/reset methods.
#include <cassert>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <deque>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <vector>
#include <iostream>
#include <functional>
#include "../range_notification.h"
#define ESP_LOGI(...) ((void)0)
constexpr int AUDIO_POWER_CHECK_INTERVAL_MS=1000;
void esp_timer_stop(int) {}
void esp_timer_start_periodic(int,int) {}
struct AudioStreamPacket { int sample_rate=0,frame_duration=0; std::vector<uint8_t> payload; };
struct Decoder { unsigned resets=0; void ResetState(){++resets;} };
struct Codec { bool output_enabled(){return true;} void EnableOutput(bool){} int output_sample_rate(){return 16000;} };
enum AudioTaskType { kAudioTaskTypeDecodeToPlaybackQueue, kAudioTaskTypeRangeNotification };
struct AudioTask { AudioTaskType type=kAudioTaskTypeDecodeToPlaybackQueue; std::vector<int16_t> pcm; uint32_t timestamp=0; };
class AudioService {
public:
    bool PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> packet, bool wait=false, bool local_priority=false);
    void PlaySound(const std::string_view& ogg, bool local_priority=false);
    void ResetDecoder();
    void SetRangeNotificationSuppressed(bool);
    bool PlayRangeBeepIfIdle();
    void CancelRangeNotificationsLocked();
    std::mutex audio_queue_mutex_;
    std::condition_variable audio_queue_cv_;
    bool local_priority_=false, decode_active_=false, playback_active_=false, service_stopped_=false;
    std::deque<std::unique_ptr<AudioStreamPacket>> audio_decode_queue_;
    bool range_notification_suppressed_=true;
    std::deque<std::unique_ptr<AudioTask>> audio_playback_queue_;
    std::deque<int> audio_testing_queue_,timestamp_queue_;
    static constexpr size_t MAX_DECODE_PACKETS_IN_QUEUE=40;
    Decoder decoder; Decoder* opus_decoder_=&decoder;
    Codec codec; Codec* codec_=&codec;
    int audio_power_timer_=0;
};
static std::function<void()> after_pcm_prepared;
static std::vector<int16_t> PrepareNotificationPcm(int rate) {
    auto pcm=RangeNotificationPcm(rate);
    if(after_pcm_prepared) after_pcm_prepared();
    return pcm;
}
// Schedule events during the actual method's out-of-lock preparation window.
#define RangeNotificationPcm PrepareNotificationPcm
#include "priority_audio_methods.inc"
#undef RangeNotificationPcm
static void RangeNotificationTests() {
    for (int rate : {8000,16000,24000,48000,96000}) {
        auto pcm=RangeNotificationPcm(rate);
        assert(pcm.size()==static_cast<size_t>(rate*80/1000));
        assert(pcm.front()==0 && pcm.back()==0);
        unsigned positive_crossings=0;
        for(size_t i=1;i<pcm.size();++i) {
            assert(pcm[i]>=-5899 && pcm[i]<=5899);
            if(pcm[i-1]<=0 && pcm[i]>0) ++positive_crossings;
        }
        assert(positive_crossings>=111 && positive_crossings<=113); // 1400Hz x 80ms.
    }
    assert(RangeNotificationPcm(0).empty());
    AudioService a;
    assert(!a.PlayRangeBeepIfIdle()); // Non-idle/startup is suppressed by default.
    a.SetRangeNotificationSuppressed(false);
    assert(a.PlayRangeBeepIfIdle());
    assert(a.audio_playback_queue_.size()==4);
    for (auto& task:a.audio_playback_queue_) {
        assert(task->type==kAudioTaskTypeRangeNotification && task->pcm.size()==320 && task->timestamp==0);
    }
    assert(a.decoder.resets==0 && !a.local_priority_);
    auto cloud=std::make_unique<AudioStreamPacket>(); cloud->payload={4,5,6};
    assert(a.PushPacketToDecodeQueue(std::move(cloud)));
    assert(a.audio_playback_queue_.empty() && a.audio_decode_queue_.size()==1);
    assert(a.audio_decode_queue_.front()->payload==std::vector<uint8_t>({4,5,6}));
    assert(a.decoder.resets==0); // Speech accepted intact, not reset/rejected by ordinary tone.
    assert(!a.PlayRangeBeepIfIdle()); // Queued cloud audio blocks notifications.
    a.audio_decode_queue_.clear();
    auto speech=std::make_unique<AudioTask>(); speech->pcm={1,2,3}; speech->timestamp=123;
    a.audio_playback_queue_.push_back(std::move(speech));
    auto beep=std::make_unique<AudioTask>(); beep->type=kAudioTaskTypeRangeNotification;
    a.audio_playback_queue_.push_back(std::move(beep));
    a.SetRangeNotificationSuppressed(true);
    assert(a.audio_playback_queue_.size()==1 && a.audio_playback_queue_.front()->timestamp==123);
    a.audio_playback_queue_.clear(); a.SetRangeNotificationSuppressed(false);
    for (bool* flag : {&a.decode_active_,&a.playback_active_,&a.local_priority_,&a.service_stopped_}) {
        *flag=true; assert(!a.PlayRangeBeepIfIdle()); *flag=false;
    }
    after_pcm_prepared=[&]{a.SetRangeNotificationSuppressed(true);};
    assert(!a.PlayRangeBeepIfIdle() && a.audio_playback_queue_.empty());
    a.SetRangeNotificationSuppressed(false);
    after_pcm_prepared=[&]{assert(a.PushPacketToDecodeQueue(std::make_unique<AudioStreamPacket>()));};
    assert(!a.PlayRangeBeepIfIdle() && a.audio_playback_queue_.empty());
    assert(a.audio_decode_queue_.size()==1 && a.decoder.resets==0);
    a.audio_decode_queue_.clear(); after_pcm_prepared={};
    a.SetRangeNotificationSuppressed(false);
    assert(a.PlayRangeBeepIfIdle()); a.SetRangeNotificationSuppressed(true);
    assert(a.audio_playback_queue_.empty());
    std::cout<<"ordinary range PCM: waveform, idle admission, dialogue cancellation, intact cloud packets and active-frame gates PASS\n";
}
int main(int argc,char**argv) {
    RangeNotificationTests();
    assert(argc==2);
    std::ifstream f(argv[1],std::ios::binary);
    std::string ogg((std::istreambuf_iterator<char>(f)),{});
    assert(!ogg.empty()); AudioService audio;
    // Simulate an in-flight cloud decoder; local playback must not reset it mid-frame.
    audio.decode_active_=true;
    audio.audio_decode_queue_.push_back(std::make_unique<AudioStreamPacket>());
    std::atomic<bool> returned=false;
    std::thread warning([&]{audio.PlaySound(ogg,true); returned=true;});
    for (;;) { std::lock_guard<std::mutex> l(audio.audio_queue_mutex_); if(audio.local_priority_) break; }
    audio.ResetDecoder(); assert(audio.decoder.resets==0);
    assert(!audio.PushPacketToDecodeQueue(std::make_unique<AudioStreamPacket>()));
    audio.PlaySound(ogg); // Normal beeps cannot interleave with priority tone.
    {
        std::lock_guard<std::mutex> l(audio.audio_queue_mutex_);
        assert(audio.audio_decode_queue_.empty()); audio.decode_active_=false; audio.audio_queue_cv_.notify_all();
    }
    unsigned packets=0;
    for (;;) {
        std::unique_lock<std::mutex> l(audio.audio_queue_mutex_);
        audio.audio_queue_cv_.wait(l,[&]{return !audio.audio_decode_queue_.empty() || !audio.local_priority_;});
        if(!audio.local_priority_) break;
        auto packet=std::move(audio.audio_decode_queue_.front()); audio.audio_decode_queue_.pop_front();
        assert(packet->sample_rate==16000 && packet->frame_duration==60 && !packet->payload.empty());
        audio.playback_active_=true; audio.audio_queue_cv_.notify_all(); l.unlock();
        audio.ResetDecoder(); // Cloud tts state transitions cannot truncate warning.
        assert(!audio.PushPacketToDecodeQueue(std::make_unique<AudioStreamPacket>()));
        l.lock(); assert(!returned); ++packets;
        audio.playback_active_=false; audio.audio_queue_cv_.notify_all();
    }
    warning.join(); assert(returned && packets>0 && packets<=8 && audio.decoder.resets==1);
    assert(audio.PushPacketToDecodeQueue(std::make_unique<AudioStreamPacket>()));
    audio.ResetDecoder(); assert(audio.decoder.resets==2 && audio.audio_decode_queue_.empty());
    std::cout<<"priority tone: "<<packets<<" packets, cloud exclusion, reset protection, drain/release PASS\n";
}
