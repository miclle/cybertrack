// Actual MCP dispatch/callbacks with a virtual clock and no board IO.
#include "receipt_host.h"
#include "admission_result.h"
#include "voice_feedback.h"
#include "mcp_tool_types.h"
#include <functional>
#include <iostream>
#include <memory>
#include <climits>

bool initialized = false;
#include "host_admission.inc"
#define ESP_LOGE(...) ((void)0)
class Application {
public:
    static Application& GetInstance() { static Application instance; return instance; }
    void Schedule(std::function<void()> callback) { callback(); }
};

class McpServer {
    std::vector<std::unique_ptr<McpTool>> owned_;
    std::vector<McpTool*> tools_;
public:
    std::string reply;
    void AddTool(const std::string& name, const std::string& description, const PropertyList& properties,
                 std::function<ReturnValue(const PropertyList&)> callback) {
        owned_.emplace_back(new McpTool(name, description, properties, callback));
        tools_.push_back(owned_.back().get());
    }
    void ReplyResult(int, const std::string& result) { reply = "{\"result\":" + result + "}"; }
    void ReplyError(int, const std::string& message) {
        auto* object = cJSON_CreateObject();
        auto* error = cJSON_AddObjectToObject(object,"error");
        cJSON_AddStringToObject(error,"message",message.c_str());
        char* raw = cJSON_PrintUnformatted(object);
        if (!raw) throw std::runtime_error("cannot encode host error");
        reply = raw;
        cJSON_free(raw);
        cJSON_Delete(object);
    }
    void DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments);
};
#include "host_dispatch.inc"

static bool Advance(unsigned elapsed) {
    const uint64_t target = 1000 + elapsed;
    if (target < clock_ms || elapsed > 300000) return false;
    while (clock_ms < target) {
        clock_ms = std::min<uint64_t>(clock_ms+5,target);
        TickLocked(clock_ms);
    }
    return true;
}
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    sessions.WifiLink(clock_ms,true);
    sessions.VoiceLink(clock_ms,true);
    sessions.Tick(clock_ms,false);
    host_distance_mm = 600;
    std::string profile = argv[1];
    if (profile == "corpus_forward70") {
        int ticket=sessions.VoiceClaim(clock_ms,INT_MIN,AudioActionGuard::MoveOnly);
        Reply("move",ticket,30000,"forward",0,0,nullptr,nullptr,70);
        if (!guard.Moving() || guard.Starts()!=1) return 2;
    } else if (profile == "corpus_sequence") {
        ActionPlan plan;
        plan.count=2;
        plan.steps[0]={"forward",30000,0,0,0,70};
        plan.steps[1]={"none",0,0,1000,0};
        int ticket=sessions.VoiceClaim(clock_ms,INT_MIN,AudioActionGuard::PlanMode);
        Reply("sequence",ticket,0,nullptr,0,0,nullptr,&plan);
        if (!sessions.plan_active || !guard.Moving()) return 2;
    } else if (profile != "corpus_idle") return 2;

    McpServer server;
#include "host_registration.inc"
    std::string input;
    if (!std::getline(std::cin,input)) return 2;
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> calls(cJSON_ParseWithOpts(input.c_str(),nullptr,true),cJSON_Delete);
    if (!cJSON_IsArray(calls.get())) return 2;
    int id=1;
    cJSON* call;
    cJSON_ArrayForEach(call,calls.get()) {
        const auto* inspect=cJSON_GetObjectItemCaseSensitive(call,"inspect_ms");
        if (inspect) {
            if (!ShowInteger(inspect,0,300000) || !Advance(inspect->valueint)) return 2;
            continue;
        }
        const auto* elapsed=cJSON_GetObjectItemCaseSensitive(call,"elapsed_ms");
        const auto* name=cJSON_GetObjectItemCaseSensitive(call,"name");
        const auto* args=cJSON_GetObjectItemCaseSensitive(call,"arguments");
        if (!ShowInteger(elapsed,0,300000) || !Advance(elapsed->valueint) || !cJSON_IsString(name)) return 2;
        std::string tool=name->valuestring;
        if (tool.compare(0,10,"self_tank_")==0) tool.replace(0,10,"self.tank.");
        const auto* rpc=cJSON_GetObjectItemCaseSensitive(call,"rpc_id");
        if (rpc && !ShowInteger(rpc,INT_MIN,INT_MAX)) return 2;
        server.reply.clear();
        server.DoToolCall(rpc ? rpc->valueint : ++id,tool,args);
        if (server.reply.empty()) return 3;
        std::cout << server.reply << '\n';
    }
    std::cout << Reply("get_status") << '\n';
}
