#include "mcp_raw_json.h"
#include <cassert>
#include <iostream>
#include <string>

#define ESP_LOGE(...) ((void)0)
class McpServer {
public:
    int rejected=0, forwarded=0;
    void RejectRobotInput(int id) { rejected=id; }
    void ParseMessage(const cJSON*) { ++forwarded; }
    void ParseMessage(const std::string& message);
};
// The actual prepared SDK raw-string entry, with only its downstream sink stubbed.
#include "mcp_raw_parse.inc"

int main() {
    // cJSON turns this invalid direction into the valid enum prefix "left".
    const std::string bad=R"({"direction":"left\u0000unexpected","duration_ms":880})";
    auto* parsed=cJSON_Parse(bad.c_str());
    assert(!std::strcmp(cJSON_GetObjectItemCaseSensitive(parsed,"direction")->valuestring,"left"));
    cJSON_Delete(parsed);
    const std::string params="{\"name\":\"self.tank.move\",\"arguments\":"+bad+"}";
    const std::string payload="{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"id\":7,\"params\":"+params+"}";
    McpServer entry;
    entry.ParseMessage(payload);
    assert(entry.rejected==7 && entry.forwarded==0);
    for (const std::string rpc : {"1.5", "2147483648", "-2147483649"}) {
        std::string wire=payload;
        wire.replace(wire.find("\"id\":7"), 6, "\"id\":"+rpc);
        entry.ParseMessage(wire);
        assert(entry.forwarded==0);
    }
    entry.ParseMessage(payload+std::string("\0tail",5));
    assert(entry.forwarded==0);
    entry.ParseMessage(std::string(R"({"jsonrpc":"2.0","method":"tools/call","id":8,"params":{"name":"self.tank.stop","arguments":{}}})"));
    assert(entry.forwarded==1);
    for (const auto& wire : {payload,"{\"type\":\"mcp\",\"payload\":"+payload+"}"}) {
        auto* root=cJSON_Parse(wire.c_str());int id=0;
        assert(RejectZeroInRobotMcp(wire,root,id) && id==7);
        cJSON_Delete(root);
    }
    assert(McpJsonContainsZero(std::string("a\0b",3)));
    for (size_t slashes=1;slashes<=8;++slashes) {
        const std::string raw="\""+std::string(slashes,'\\')+"u0000\"";
        assert(McpJsonContainsZero(raw)==(slashes%2==1));
    }
    for (const std::string wire : {
            R"({"type":"mcp","payload":{"method":"tools/call","id":8,"params":{"name":"self.tank.stop","arguments":{}}}})",
            R"({"type":"tts","text":"\u0000"})",
            R"({"method":"tools/call","id":9,"params":{"name":"self.audio.test","arguments":{"text":"\u0000"}}})",
            R"({"method":"notifications/test","id":9,"params":{"name":"self.tank.move","text":"\u0000"}})",
            R"({"method":"tools/call","id":9,"params":{"name":"self.tank.move","arguments":{"note":"\\u0000"}}})"}) {
        auto* root=cJSON_Parse(wire.c_str());int id=0;
        assert(!RejectZeroInRobotMcp(wire,root,id));cJSON_Delete(root);
    }
    std::cout << "PASS: lossy enum prefix, raw/bare envelope and slash parity; valid stop, nonrobot and literal escapes preserved\n";
}
