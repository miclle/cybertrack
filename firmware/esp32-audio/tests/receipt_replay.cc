// Replay the evaluation's status, speed, stop and compose RPCs with a controlled host clock.
// Unimplemented RPCs fail the replay; the executable links no board IO.
#include "receipt_host.h"
#include <iostream>
#include <memory>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string profile = argv[1];
    sessions.WifiLink(clock_ms,true);
    sessions.VoiceLink(clock_ms,true);
    sessions.Tick(clock_ms,false);
    uint32_t draft_web_owner = 0;
    uint64_t last_heartbeat = clock_ms;
    if (profile == "forward70" || profile == "short_forward70" || profile == "thirty_second_forward70") {
        int ticket = sessions.VoiceClaim(clock_ms,1,AudioActionGuard::MoveOnly);
        const int duration = profile == "thirty_second_forward70" ? 30000 : (profile == "forward70" ? 4000 : 400);
        Reply("move",ticket,duration,"forward",0,0,nullptr,nullptr,70);
        if (!guard.Moving() || guard.Starts() != 1) return 2;
    } else if (profile == "sequence_forward_bubbles") {
        ActionPlan plan;
        plan.count = 2;
        plan.steps[0] = {"forward", 4000, 0, 0, 0, 70};
        plan.steps[1] = {"none", 0, 0, 1000, 0};
        int ticket = sessions.VoiceClaim(clock_ms, 1, AudioActionGuard::PlanMode);
        Reply("sequence", ticket, 0, nullptr, 0, 0, nullptr, &plan);
        if (!sessions.plan_active || !guard.Moving() || guard.Starts() != 1) return 2;
    } else if (profile == "two_step_web_draft") {
        // C002 starts with a saved web draft and no prior voice status read.
        draft_web_owner = sessions.Acquire(clock_ms);
        if (!draft_web_owner) return 2;
        ShowDraft::Command edit;
        edit.plan.count = 2;
        edit.plan.steps[0] = {"left", 880, 0, 0, 0, 100};
        edit.plan.steps[1] = {"none", 0, 0, 1000, 0, 100};
        for (unsigned rev = 0; rev < 7; ++rev) {
            edit.revision = rev;
            if (!sessions.Heartbeat(clock_ms, draft_web_owner)) return 2;
            if (std::strcmp(sessions.WebDraft(clock_ms, draft_web_owner, rev + 1, sessions.window, edit),
                            "draft_saved")) return 2;
        }
    } else if (profile == "web_forward_hold") {
        const auto web = sessions.Acquire(clock_ms);
        if (!web || !sessions.Heartbeat(clock_ms, web)) return 2;
        WebCommand command;
        command.sequence = 1;
        command.window = sessions.window;
        Reply("drive_start", 0, 0, "forward", 0, web, &command);
        if (!guard.Moving() || guard.Starts() != 1) return 2;
    } else if (profile != "idle") return 2;

    std::string line;
    if (!std::getline(std::cin,line)) return 2;
    std::unique_ptr<cJSON, decltype(&cJSON_Delete)> calls(cJSON_ParseWithOpts(line.c_str(),nullptr,true), cJSON_Delete);
    if (!cJSON_IsArray(calls.get())) return 2;
    int id = 1;
    constexpr unsigned start_ms = 1000;
    cJSON* call;
    cJSON_ArrayForEach(call,calls.get()) {
        ++id;
        const auto* elapsed = cJSON_GetObjectItemCaseSensitive(call,"elapsed_ms");
        if (elapsed) {
            if (!ShowInteger(elapsed,0,300000)) return 2;
            const auto target = start_ms + static_cast<unsigned>(elapsed->valueint);
            if (target < clock_ms) return 2;
            while (clock_ms < target) {
                clock_ms = std::min<uint64_t>(clock_ms+5,target);
                TickLocked(clock_ms);
                if (draft_web_owner && clock_ms - last_heartbeat >= 200) {
                    if (!sessions.Heartbeat(clock_ms, draft_web_owner)) return 2;
                    last_heartbeat = clock_ms;
                }
            }
        }
        const auto* name = cJSON_GetObjectItemCaseSensitive(call,"name");
        const auto* args = cJSON_GetObjectItemCaseSensitive(call,"arguments");
        if (!cJSON_IsString(name) || !cJSON_IsObject(args)) return 2;
        std::string tool = name->valuestring;
        if (tool.compare(0,10,"self_tank_")==0) tool.replace(0,10,"self.tank.");
        if (tool == "self.tank.compose") {
            ShowDraft::Command edit;
            if (!ParseShowEdit(args,edit)) return 3;
            int ticket = sessions.VoiceClaim(clock_ms,id,AudioActionGuard::PlanMode);
            if (!ticket) return 3;
            std::cout << Reply("show_edit",ticket,0,nullptr,0,0,nullptr,nullptr,100,&edit) << '\n';
        } else if (tool == "self.tank.set_speed") {
            auto* speed = cJSON_GetObjectItemCaseSensitive(args, "speed_percent");
            if (cJSON_GetArraySize(args) != 1 || !ShowInteger(speed,60,100)) return 3;
            int ticket = sessions.VoiceClaim(clock_ms,id,AudioActionGuard::SpeedMode);
            if (!ticket) {
                std::cout << R"({"rpc_error":"Action request duplicate, channel busy or cooling, offline, queue full, or cancelled by web priority"})" << '\n';
                continue;
            }
            std::cout << Reply("set_speed",ticket,speed->valueint) << '\n';
        } else if ((tool == "self.tank.get_status" || tool == "self.tank.stop") && cJSON_GetArraySize(args)==0) {
            if (tool == "self.tank.stop") sessions.Stop(clock_ms); // Same immediate cancellation as MCP dispatch.
            std::cout << Reply(tool.c_str()+10) << '\n';
        } else {
            std::cerr << "RPC outside the replay contract\n";
            return 3;
        }
    }
    // Snapshot after all calls, even when the model sent no RPC. A final
    // read cannot affect the already-completed edit sequence.
    std::cout << Reply("get_status") << '\n';
}
