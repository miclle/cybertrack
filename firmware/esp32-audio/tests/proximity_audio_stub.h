#pragma once
#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>
#include <string_view>
#include <vector>
constexpr int pdTRUE=1, pdPASS=1, ESP_OK=0, ESP_ERR_NO_MEM=0x101;
constexpr unsigned portMAX_DELAY=~0u;
constexpr int kDeviceStateUnknown=0, kDeviceStateStarting=1, kDeviceStateIdle=2;
#define ESP_LOGI(...) ((void)0)
#define ESP_ERROR_CHECK(value) assert((value)==ESP_OK)
struct StaticQueue_t {};
using QueueHandle_t = void*;
namespace sound_mock {
struct Done {};
inline uint64_t now=0, ready_at=0;
inline size_t size=0;
inline bool queued=false;
inline uint8_t pending[64]{};
inline std::vector<std::string> played;
inline std::function<void()> before_play;
inline void (*task)(void*)=nullptr;
}
inline QueueHandle_t xQueueCreateStatic(int n,size_t size,uint8_t*,StaticQueue_t*) {
    assert(n==1 && size<=64); sound_mock::size=size; return sound_mock::pending;
}
inline int xQueuePeek(QueueHandle_t,void* out,unsigned wait) {
    assert(!wait); if(!sound_mock::queued) return 0;
    std::memcpy(out,sound_mock::pending,sound_mock::size); return pdTRUE;
}
inline int xQueueOverwrite(QueueHandle_t,const void* value) {
    std::memcpy(sound_mock::pending,value,sound_mock::size); sound_mock::queued=true; return pdTRUE;
}
inline int xQueueReceive(QueueHandle_t,void* out,unsigned wait) {
    assert(wait==portMAX_DELAY); if(!sound_mock::queued) throw sound_mock::Done{};
    std::memcpy(out,sound_mock::pending,sound_mock::size); sound_mock::queued=false; return pdTRUE;
}
inline int xTaskCreate(void(*task)(void*),const char*,unsigned stack,void*,int priority,void*) {
    assert(stack>=6144 && priority==2); sound_mock::task=task; return pdPASS;
}
inline unsigned pdMS_TO_TICKS(unsigned ms) {return ms;}
inline void vTaskDelay(unsigned ms) {sound_mock::now+=ms;}
inline int64_t esp_timer_get_time() {return sound_mock::now*1000;}
struct FakeAudio {
    void PlaySound(std::string_view data,bool priority) {
        assert(priority); sound_mock::played.emplace_back(data);
        if(sound_mock::before_play) sound_mock::before_play();
    }
};
struct Application {
    static Application& GetInstance() {static Application a; return a;}
    int GetDeviceState() {return sound_mock::now<sound_mock::ready_at ? kDeviceStateStarting : kDeviceStateIdle;}
    FakeAudio& GetAudioService() {static FakeAudio a; return a;}
};
inline constexpr unsigned char ProximityBeep[]={'b'};
inline constexpr unsigned char ProximityStop[]={'s'};
