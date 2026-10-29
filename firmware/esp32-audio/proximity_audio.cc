#include "proximity_audio.h"
#include "proximity_sounds.h"
#include "application.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_log.h>

namespace {
StaticQueue_t storage;
uint8_t bytes[sizeof(ProximityGuard::Alert)];
QueueHandle_t queue = xQueueCreateStatic(1, sizeof(ProximityGuard::Alert), bytes, &storage);
void ProximityVoiceTask(void*) {
    auto& app = Application::GetInstance();
    // Board initialization precedes AudioService initialization.
    while (app.GetDeviceState() == kDeviceStateUnknown || app.GetDeviceState() == kDeviceStateStarting)
        vTaskDelay(pdMS_TO_TICKS(100));
    ProximityGuard::Alert alert;
    for (;;) if (xQueueReceive(queue, &alert, portMAX_DELAY) == pdTRUE) {
        ESP_LOGI("CT_RANGE", "PROXIMITY_VOICE level=%s", alert == ProximityGuard::Stop ? "stop" : "caution");
        const auto* data = alert == ProximityGuard::Stop ? ProximityStop : ProximityCaution;
        const auto size = alert == ProximityGuard::Stop ? sizeof(ProximityStop) : sizeof(ProximityCaution);
        app.GetAudioService().PlaySound(std::string_view(reinterpret_cast<const char*>(data), size), true);
    }
}
}
void CyberTrackProximityAlert(ProximityGuard::Alert alert) {
    if (alert == ProximityGuard::None) return;
    ProximityGuard::Alert pending;
    if (xQueuePeek(queue, &pending, 0) == pdTRUE && pending > alert) return;
    xQueueOverwrite(queue, &alert);
}
void InitializeCyberTrackProximityAudio() {
    ESP_ERROR_CHECK(xTaskCreate(ProximityVoiceTask, "range_voice", 6144, nullptr, 2, nullptr) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
}
