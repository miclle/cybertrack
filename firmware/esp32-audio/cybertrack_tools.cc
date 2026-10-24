#include "cybertrack_tools.h"
#include "cybertrack_state.h"
#include "mcp_server.h"
#include "system_info.h"
#include <esp_timer.h>
#include <esp_random.h>
#include <esp_log.h>

void InitializeCyberTrackTools() {
    static CyberTrackAudioState state(esp_timer_get_time() / 1000);
    static const std::string device_id = SystemInfo::GetMacAddress();
    static const std::string boot_id = [] {
        char id[17];
        std::snprintf(id, sizeof(id), "%08lx%08lx", static_cast<unsigned long>(esp_random()),
                      static_cast<unsigned long>(esp_random()));
        return std::string(id);
    }();
    auto& server = McpServer::GetInstance();
    server.AddTool("self.tank.get_status",
        "查询 CyberTrack 音频板的实时逻辑控制状态。当前没有连接水枪或其他执行器，所有动作能力关闭；"
        "没有电量、液位或实物运动反馈。询问 CyberTrack 状态时使用此工具。",
        PropertyList(), [](const PropertyList&) -> ReturnValue {
            auto result = state.Call(false, esp_timer_get_time() / 1000, device_id, boot_id);
            ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
            return result;
        });
    server.AddTool("self.tank.stop",
        "停止 CyberTrack：锁定本板的逻辑动作控制并清除逻辑输出。当前为无执行器语音联调，"
        "不能声称已停止另一块 ESP32 或实体水枪；不会关闭麦克风、扬声器或屏幕。",
        PropertyList(), [](const PropertyList&) -> ReturnValue {
            auto result = state.Call(true, esp_timer_get_time() / 1000, device_id, boot_id);
            ESP_LOGI("CT_AUDIO", "RESULT %s", result.c_str());
            return result;
        });
    ESP_LOGI("CT_AUDIO", "READY tools=status,stop actuator_backend=not_installed");
}
