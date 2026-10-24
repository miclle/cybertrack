#include "linx_wire.h"
#include "cybertrack/protocol.h"
#include "yyjson.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static ct_protocol p;
static ct_controller c;
static char reply[CT_RPC_REPLY_CAP];
static void request(const char *json)
{
    ct_rpc_delivery delivery = {.session = p.session, .received_at_ms = 1};
    assert(ct_protocol_handle(&p, json, strlen(json), delivery, 1, reply, sizeof(reply)) == CT_RPC_RESPONSE);
    assert(!c.output.water && !c.output.bubbles && !c.output.left_level && !c.output.right_level);
}
int main(void)
{
    linx_gateway g;
    const char *unbound = "{\"activation\":{\"code\":\"123456\"}}";
    assert(linx_parse_gateway(unbound, strlen(unbound), &g) && !strcmp(g.code,"123456"));
    const char *bound = "{\"websocket\":{\"url\":\"ws://xrobo-io.qiniuapi.com/v1/ws/\",\"token\":\"test-only\"}}";
    assert(linx_parse_gateway(bound, strlen(bound), &g) && !strncmp(g.url,"wss://",6));
    const char *bad[] = {"{}", "{\"error\":\"bad\"}", "{\"activation\":{\"code\":\"12345\"}}",
        "{\"websocket\":{\"url\":\"wss://other.invalid/\",\"token\":\"x\"}}",
        "{\"websocket\":{\"url\":\"wss://xrobo-io.qiniuapi.com/v1/ws/\",\"token\":\"x\\r\\nX: injected\"}}",
        "{\"websocket\":{\"url\":\"wss://xrobo-io.qiniuapi.com/v1/ws/\"}}"};
    for (size_t i=0;i<sizeof(bad)/sizeof(*bad);++i) assert(!linx_parse_gateway(bad[i],strlen(bad[i]),&g));
    char session[128];
    const char *hello = "{\"type\":\"hello\",\"transport\":\"websocket\",\"audio_params\":{}}";
    assert(linx_parse_hello(hello,strlen(hello),session));
    assert(!linx_parse_hello("{}",2,session));
    for (size_t cut=1;cut<strlen(hello);++cut) {
        linx_text t = {0};
        assert(linx_text_feed(&t,1,true,0,strlen(hello),hello,cut)==0);
        assert(linx_text_feed(&t,1,true,cut,strlen(hello),hello+cut,strlen(hello)-cut)==1);
        assert(!strcmp(t.text,hello));
        t=(linx_text){0};
        assert(linx_text_feed(&t,1,false,0,cut,hello,cut)==0);
        assert(linx_text_feed(&t,9,true,0,1,"p",1)==0);
        assert(linx_text_feed(&t,0,true,0,strlen(hello)-cut,hello+cut,strlen(hello)-cut)==1);
        assert(!strcmp(t.text,hello));
    }
    linx_text t={0};
    assert(linx_text_feed(&t,0,true,0,1,"x",1)==-1);
    assert(linx_text_feed(&t,1,true,0,2049,"x",1)==-1);
    assert(linx_text_feed(&t,1,true,0,3,"a",1)==0);
    assert(linx_text_feed(&t,1,true,2,3,"b",1)==-1);
    ct_init(&c,(ct_limits){0},0); ct_boot_complete(&c); ct_protocol_init(&p,&c,0);
    assert(ct_protocol_open(&p,1));
    request("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1\"}}}}");
    assert(p.initialized);
    request("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}}");
    yyjson_doc *doc=yyjson_read(reply,strlen(reply),0);
    yyjson_val *payload=yyjson_obj_get(yyjson_doc_get_root(doc),"payload");
    yyjson_val *tools=yyjson_obj_get(yyjson_obj_get(payload,"result"),"tools");
    assert(yyjson_arr_size(tools)==2); yyjson_doc_free(doc);
    request("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.water\",\"arguments\":{\"duration_ms\":5000}}}}");
    assert(p.accepted_sequence==0);
    const char *stop="{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.stop\",\"arguments\":{}}}}";
    request(stop); assert(c.fault==CT_STOPPED); request(stop); assert(c.fault==CT_STOPPED);
    request("{\"type\":\"mcp\",\"payload\":{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"self.tank.get_status\",\"arguments\":{}}}}");
    assert(strstr(reply,"stopped"));
    ct_protocol_close(&p,2); assert(ct_protocol_open(&p,3));
    assert(!c.output.water && c.state!=CT_ACTIVE && c.state!=CT_READY);
    puts("PASS: gateway, TLS origin, hello, all fragment splits, only two tools, action rejection, duplicate stop, status, reconnect");
}
