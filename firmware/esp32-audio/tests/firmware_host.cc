// Actual MCP dispatch/callbacks with a virtual clock and no board IO.
#include "receipt_host.h"
#include "admission_result.h"
#include "voice_feedback.h"
#include "draft_duration_intent.h"
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
    bool defer = false;
    std::vector<std::function<void()>> pending;
    static Application& GetInstance() { static Application instance; return instance; }
    void Schedule(std::function<void()> callback) {
        if (defer) pending.push_back(std::move(callback));
        else callback();
    }
    void Flush() {
        auto callbacks = std::move(pending);
        pending.clear();
        for (auto& callback : callbacks) callback();
    }
};

class McpServer {
    std::vector<std::unique_ptr<McpTool>> owned_;
    std::vector<McpTool*> tools_;
public:
    std::string reply;
    std::vector<std::string> responses;
    void AddTool(const std::string& name, const std::string& description, const PropertyList& properties,
                 std::function<ReturnValue(const PropertyList&)> callback) {
        owned_.emplace_back(new McpTool(name, description, properties, callback));
        tools_.push_back(owned_.back().get());
    }
    void ReplyResult(int, const std::string& result) {
        reply = "{\"result\":" + result + "}";
        responses.push_back(reply);
    }
    void ReplyError(int, const std::string& message) {
        auto* object = cJSON_CreateObject();
        auto* error = cJSON_AddObjectToObject(object,"error");
        cJSON_AddStringToObject(error,"message",message.c_str());
        char* raw = cJSON_PrintUnformatted(object);
        if (!raw) throw std::runtime_error("cannot encode host error");
        reply = raw;
        responses.push_back(reply);
        cJSON_free(raw);
        cJSON_Delete(object);
    }
    void DoToolCall(int id, const std::string& tool_name, const cJSON* tool_arguments);
};
#include "host_dispatch.inc"

uint32_t host_web_owner = 0;
uint64_t last_web_heartbeat = 1000;

static bool Advance(unsigned elapsed) {
    const uint64_t target = 1000 + elapsed;
    if (target < clock_ms || elapsed > 300000) return false;
    while (clock_ms < target) {
        clock_ms = std::min<uint64_t>(clock_ms+5,target);
        TickLocked(clock_ms);
        if (host_web_owner && clock_ms-last_web_heartbeat>=200) {
            if (!sessions.Heartbeat(clock_ms,host_web_owner)) return false;
            last_web_heartbeat=clock_ms;
        }
    }
    return true;
}
int main(int argc, char** argv) {
    if (argc != 2 && (argc != 3 || std::string(argv[2]) != "--await-stt")) return 2;
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
    } else if (profile == "corpus_draft7" || profile == "corpus_draft7_conflict") {
        ShowDraft::Command edit;
        edit.plan.count=2;
        edit.plan.steps[0]={"left",880,0,0,0,100};
        edit.plan.steps[1]={"none",0,0,1000,0,100};
        for (int revision=0;revision<7;++revision) {
            Reply("get_status");
            edit.revision=revision;
            int ticket=sessions.VoiceClaim(clock_ms,INT_MIN+revision,AudioActionGuard::PlanMode);
            if (!ticket) return 2;
            Reply("show_edit",ticket,0,nullptr,0,0,nullptr,nullptr,100,&edit);
            if (sessions.draft.CurrentRevision()!=static_cast<unsigned>(revision+1)) return 2;
        }
    } else if (profile != "corpus_idle") return 2;

    // Bootstrap requests belong to setup, not the captured platform RPC epoch.
    guard.NewVoiceSession();
    if (argc == 2) CyberTrackVoiceInput("captured host input");
    McpServer server;
#include "host_registration.inc"
    std::string input;
    if (!std::getline(std::cin,input)) return 2;
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> calls(cJSON_ParseWithOpts(input.c_str(),nullptr,true),cJSON_Delete);
    if (!cJSON_IsArray(calls.get())) return 2;
    int id=1;
    bool conflict_applied=false;
    cJSON* call;
    cJSON_ArrayForEach(call,calls.get()) {
        const auto* inspect=cJSON_GetObjectItemCaseSensitive(call,"inspect_ms");
        if (inspect) {
            if (!ShowInteger(inspect,0,300000) || !Advance(inspect->valueint)) return 2;
            continue;
        }
        const auto* elapsed=cJSON_GetObjectItemCaseSensitive(call,"elapsed_ms");
        if (!ShowInteger(elapsed,0,300000) || !Advance(elapsed->valueint)) return 2;
        if (const auto* text=cJSON_GetObjectItemCaseSensitive(call,"input_text")) {
            if (!cJSON_IsString(text)) return 2;
            CyberTrackVoiceInput(text->valuestring);
            continue;
        }
        if (const auto* flush=cJSON_GetObjectItemCaseSensitive(call,"flush")) {
            if (!cJSON_IsTrue(flush)) return 2;
            Application::GetInstance().Flush();
            continue;
        }
        if (const auto* online=cJSON_GetObjectItemCaseSensitive(call,"voice_online")) {
            if (!cJSON_IsBool(online)) return 2;
            sessions.VoiceLink(clock_ms,cJSON_IsTrue(online));
            continue;
        }
        const auto* name=cJSON_GetObjectItemCaseSensitive(call,"name");
        const auto* args=cJSON_GetObjectItemCaseSensitive(call,"arguments");
        if (!cJSON_IsString(name)) return 2;
        std::string tool=name->valuestring;
        if (tool.compare(0,10,"self_tank_")==0) tool.replace(0,10,"self.tank.");
        if (profile=="corpus_draft7_conflict" && !conflict_applied && tool=="self.tank.compose") {
            host_web_owner=sessions.Acquire(clock_ms);
            if (!host_web_owner || !sessions.Heartbeat(clock_ms,host_web_owner)) return 2;
            last_web_heartbeat=clock_ms;
            ShowDraft::Command edit;
            edit.edit=ShowDraft::ReplaceStep;
            edit.revision=sessions.draft.CurrentRevision();
            edit.step=2;
            edit.plan.count=1;
            edit.plan.steps[0]={"none",0,0,3000,0,100};
            if (std::strcmp(sessions.WebDraft(clock_ms,host_web_owner,1,sessions.window,edit),"draft_saved")) return 2;
            conflict_applied=true;
        }
        const auto* rpc=cJSON_GetObjectItemCaseSensitive(call,"rpc_id");
        if (rpc && !ShowInteger(rpc,INT_MIN,INT_MAX)) return 2;
        server.reply.clear();
        const auto* defer=cJSON_GetObjectItemCaseSensitive(call,"defer");
        if (defer && !cJSON_IsBool(defer)) return 2;
        Application::GetInstance().defer=cJSON_IsTrue(defer);
        server.DoToolCall(rpc ? rpc->valueint : ++id,tool,args);
        Application::GetInstance().defer=false;
        if (server.reply.empty() && !cJSON_IsTrue(defer)) return 3;
    }
    Application::GetInstance().Flush();
    for (const auto& response : server.responses) std::cout << response << '\n';
    std::cout << Reply("get_status") << '\n';
}
