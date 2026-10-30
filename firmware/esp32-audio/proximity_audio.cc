#include "proximity_audio.h"
#include "proximity_sounds.h"
#include "application.h"
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_timer.h>
#include <esp_log.h>

namespace {
struct SoundEvent { ProximityGuard::Alert alert; uint64_t at_ms; };
StaticQueue_t storage;
uint8_t bytes[sizeof(SoundEvent)];
QueueHandle_t queue = xQueueCreateStatic(1, sizeof(SoundEvent), bytes, &storage);
std::atomic<bool> beeping{false};
void ProximitySoundTask(void*) {
    auto& app = Application::GetInstance();
    // Board initialization precedes AudioService initialization.
    while (app.GetDeviceState() == kDeviceStateUnknown || app.GetDeviceState() == kDeviceStateStarting)
        vTaskDelay(pdMS_TO_TICKS(100));
    SoundEvent event{};
    for (;;) if (xQueueReceive(queue, &event, portMAX_DELAY) == pdTRUE) {
        const auto now = static_cast<uint64_t>(esp_timer_get_time() / 1000);
        const bool stop = event.alert == ProximityGuard::Stop;
        if (event.alert == ProximityGuard::None || now < event.at_ms ||
            now - event.at_ms > (stop ? 1000u : 250u) || (!stop && !beeping.load())) continue;
        const auto* data = stop ? ProximityStop : ProximityBeep;
        const auto size = stop ? sizeof(ProximityStop) : sizeof(ProximityBeep);
        ESP_LOGI("CT_RANGE", "PROXIMITY_TONE kind=%s", stop ? "stop" : "beep");
        app.GetAudioService().PlaySound(std::string_view(reinterpret_cast<const char*>(data), size), true);
    }
}
}
void CyberTrackProximityAlert(ProximityGuard::Alert alert, bool enabled) {
    beeping.store(enabled);
    SoundEvent pending{};
    const bool has_pending = xQueuePeek(queue, &pending, 0) == pdTRUE;
    if (!enabled && has_pending && pending.alert == ProximityGuard::Beep) {
        const SoundEvent cancel{ProximityGuard::None, 0};
        xQueueOverwrite(queue, &cancel);
    }
    if (alert == ProximityGuard::None || (has_pending && pending.alert == ProximityGuard::Stop)) return;
    const SoundEvent event{alert, static_cast<uint64_t>(esp_timer_get_time() / 1000)};
    xQueueOverwrite(queue, &event);
}
void InitializeCyberTrackProximityAudio() {
    ESP_ERROR_CHECK(xTaskCreate(ProximitySoundTask, "range_sound", 6144, nullptr, 2, nullptr) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
}
