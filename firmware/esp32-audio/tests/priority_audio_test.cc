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
#define ESP_LOGI(...) ((void)0)
constexpr int AUDIO_POWER_CHECK_INTERVAL_MS=1000;
void esp_timer_stop(int) {}
void esp_timer_start_periodic(int,int) {}
struct AudioStreamPacket { int sample_rate=0,frame_duration=0; std::vector<uint8_t> payload; };
struct Decoder { unsigned resets=0; void ResetState(){++resets;} };
struct Codec { bool output_enabled(){return true;} void EnableOutput(bool){} };
class AudioService {
public:
    bool PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> packet, bool wait=false, bool local_priority=false);
    void PlaySound(const std::string_view& ogg, bool local_priority=false);
    void ResetDecoder();
    std::mutex audio_queue_mutex_;
    std::condition_variable audio_queue_cv_;
    bool local_priority_=false, decode_active_=false, playback_active_=false, service_stopped_=false;
    std::deque<std::unique_ptr<AudioStreamPacket>> audio_decode_queue_;
    std::deque<int> audio_playback_queue_,audio_testing_queue_,timestamp_queue_;
    static constexpr size_t MAX_DECODE_PACKETS_IN_QUEUE=40;
    Decoder decoder; Decoder* opus_decoder_=&decoder;
    Codec codec; Codec* codec_=&codec;
    int audio_power_timer_=0;
};
#include "priority_audio_methods.inc"
int main(int argc,char**argv) {
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
    audio.PlaySound(ogg); // Normal beeps cannot interleave with priority speech.
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
    warning.join(); assert(returned && packets>10 && audio.decoder.resets==1);
    assert(audio.PushPacketToDecodeQueue(std::make_unique<AudioStreamPacket>()));
    audio.ResetDecoder(); assert(audio.decoder.resets==2 && audio.audio_decode_queue_.empty());
    std::cout<<"priority speech: "<<packets<<" packets, cloud exclusion, reset protection, drain/release PASS\n";
}
