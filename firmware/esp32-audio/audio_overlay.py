"""Pinned-source patch: critical warnings preempt; idle range tones yield to speech."""
from pathlib import Path
import shutil

def apply(source, replace):
    header = source / 'main/audio/audio_service.h'
    code = source / 'main/audio/audio_service.cc'
    shutil.copy2(Path(__file__).with_name('range_notification.h'), source / 'main/audio/range_notification.h')
    replace(header, '    kAudioTaskTypeDecodeToPlaybackQueue,',
            '    kAudioTaskTypeDecodeToPlaybackQueue,\n    kAudioTaskTypeRangeNotification,')
    replace(header, '    void ResetDecoder();',
            '    void ResetDecoder();\n    void SetRangeNotificationSuppressed(bool suppressed);\n    bool PlayRangeBeepIfIdle();')
    replace(header, '    bool wake_word_initialized_ = false;',
            '    bool range_notification_suppressed_ = true; // audio_queue_mutex_\n'
            '    void CancelRangeNotificationsLocked();\n\n    bool wake_word_initialized_ = false;')
    replace(header, 'bool wait = false);', 'bool wait = false, bool local_priority = false);')
    replace(header, 'void PlaySound(const std::string_view& sound);',
            'void PlaySound(const std::string_view& sound, bool local_priority = false);')
    replace(header, '    std::deque<std::unique_ptr<AudioTask>> audio_playback_queue_;',
            '    bool local_priority_ = false, decode_active_ = false, playback_active_ = false; // audio_queue_mutex_\n'
            '    std::deque<std::unique_ptr<AudioTask>> audio_playback_queue_;')
    replace(code, '        audio_playback_queue_.pop_front();',
            '        audio_playback_queue_.pop_front();\n        playback_active_ = true;')
    replace(code, '        codec_->OutputData(task->pcm);',
            '''        codec_->OutputData(task->pcm);
        {
            std::lock_guard<std::mutex> finished(audio_queue_mutex_);
            playback_active_ = false;
            audio_queue_cv_.notify_all();
        }''')
    replace(code, '            audio_decode_queue_.pop_front();',
            '            audio_decode_queue_.pop_front();\n            decode_active_ = true;')
    replace(code, '            debug_statistics_.decode_count++;',
            '            decode_active_ = false;\n            audio_queue_cv_.notify_all();\n            debug_statistics_.decode_count++;')
    replace(code, 'bool AudioService::PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> packet, bool wait) {\n    std::unique_lock<std::mutex> lock(audio_queue_mutex_);',
            '''bool AudioService::PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> packet, bool wait, bool local_priority) {
    std::unique_lock<std::mutex> lock(audio_queue_mutex_);
    if (local_priority_ && !local_priority) return false;''')
    replace(code, '    audio_decode_queue_.push_back(std::move(packet));',
            '    if (local_priority_ && !local_priority) return false;\n'
            '    if (!local_priority) CancelRangeNotificationsLocked();\n'
            '    audio_decode_queue_.push_back(std::move(packet));')
    replace(code, 'void AudioService::PlaySound(const std::string_view& ogg) {',
            '''void AudioService::PlaySound(const std::string_view& ogg, bool local_priority) {
    {
        std::unique_lock<std::mutex> lock(audio_queue_mutex_);
        if (local_priority_ || service_stopped_) return;
        if (local_priority) {
            local_priority_ = true;
            // Drop queued speech, then wait only for the current decode frame.
            audio_decode_queue_.clear();
            audio_playback_queue_.clear();
            audio_queue_cv_.wait(lock, [this]() { return !decode_active_ || service_stopped_; });
            audio_playback_queue_.clear();
            opus_decoder_->ResetState();
        }
    }''')
    replace(code, '            PushPacketToDecodeQueue(std::move(packet), true);',
            '            PushPacketToDecodeQueue(std::move(packet), true, local_priority);')
    replace(code, '        offset = body_off + body_size;\n    }\n}',
            '''        offset = body_off + body_size;
    }
    if (local_priority) {
        std::unique_lock<std::mutex> lock(audio_queue_mutex_);
        audio_queue_cv_.wait(lock, [this]() {
            return service_stopped_ || (audio_decode_queue_.empty() && audio_playback_queue_.empty() &&
                                       !decode_active_ && !playback_active_);
        });
        local_priority_ = false;
        audio_queue_cv_.notify_all();
    }
}''')
    replace(code, 'void AudioService::ResetDecoder() {\n    std::lock_guard<std::mutex> lock(audio_queue_mutex_);',
            'void AudioService::ResetDecoder() {\n    std::lock_guard<std::mutex> lock(audio_queue_mutex_);\n    if (local_priority_) return; // Cloud state changes must not erase the local warning.')
    replace(code, 'void AudioService::ResetDecoder() {', '''#include "range_notification.h"

void AudioService::CancelRangeNotificationsLocked() {
    audio_playback_queue_.erase(std::remove_if(audio_playback_queue_.begin(), audio_playback_queue_.end(),
        [](const auto& task) { return task->type == kAudioTaskTypeRangeNotification; }), audio_playback_queue_.end());
}

void AudioService::SetRangeNotificationSuppressed(bool suppressed) {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    range_notification_suppressed_ = suppressed;
    if (suppressed) CancelRangeNotificationsLocked();
    audio_queue_cv_.notify_all();
}

bool AudioService::PlayRangeBeepIfIdle() {
    auto idle = [this]() {
        return !range_notification_suppressed_ && !service_stopped_ && !local_priority_ &&
               !decode_active_ && !playback_active_ && audio_decode_queue_.empty() &&
               audio_playback_queue_.empty();
    };
    {
        std::lock_guard<std::mutex> lock(audio_queue_mutex_);
        if (!idle()) return false;
    }
    const int rate = codec_->output_sample_rate();
    auto pcm = RangeNotificationPcm(rate);
    if (pcm.empty()) return false;
    std::vector<std::unique_ptr<AudioTask>> tasks;
    // Small PCM chunks let us cancel pending notification work without touching
    // speech. Chunk size is not a measured codec/DMA interruption bound.
    const size_t chunk = static_cast<size_t>(rate) * 20 / 1000;
    for (size_t at = 0; at < pcm.size(); at += chunk) {
        auto task = std::make_unique<AudioTask>();
        task->type = kAudioTaskTypeRangeNotification;
        task->timestamp = 0;
        task->pcm.assign(pcm.begin() + at, pcm.begin() + std::min(at + chunk, pcm.size()));
        tasks.push_back(std::move(task));
    }
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    // Speech may have arrived while the PCM was prepared outside the mutex.
    if (!idle()) return false;
    for (auto& task : tasks) audio_playback_queue_.push_back(std::move(task));
    audio_queue_cv_.notify_all();
    return true;
}

void AudioService::ResetDecoder() {''')
    replace(source / 'main/application.cc', '    device_state_ = state;',
            '    device_state_ = state;\n'
            '    audio_service_.SetRangeNotificationSuppressed(state != kDeviceStateIdle);')
