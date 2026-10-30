#pragma once
#include <string>
#include <map>
#include <functional>
#include <cstring>
#include <cstdint>
#include <algorithm>
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_FAIL=-1;
using esp_event_base_t = const char*;
constexpr auto IP_EVENT="ip";
constexpr int IP_EVENT_STA_GOT_IP=1;
constexpr int IP_EVENT_STA_LOST_IP=2;
constexpr auto WIFI_EVENT="wifi";
constexpr int WIFI_EVENT_STA_DISCONNECTED=3;
inline void TestLog(const char*, const char*, ...) {}
#define ESP_LOGI(...) TestLog(__VA_ARGS__)
#define ESP_LOGE(...) TestLog(__VA_ARGS__)
#define ESP_ERROR_CHECK(expr) do { if ((expr)!=ESP_OK) throw "ESP error"; } while(0)
inline const char* esp_err_to_name(int) { return "test_error"; }
inline int64_t test_time=1000000;
inline int64_t esp_timer_get_time() { return test_time; }
inline uint32_t esp_random() { return 12345678; }
inline void esp_fill_random(void* bytes,size_t n) { static unsigned value=0; memset(bytes,++value,n); }
struct ip_addr { uint32_t addr=0xc0a8017b; };
struct esp_netif_ip_info_t { ip_addr ip; };
struct ip_event_got_ip_t { esp_netif_ip_info_t ip_info; };
#define IPSTR "%u.%u.%u.%u"
#define IP2STR(ip) unsigned((ip)->addr>>24),unsigned(((ip)->addr>>16)&255),unsigned(((ip)->addr>>8)&255),unsigned((ip)->addr&255)
inline void* esp_netif_get_handle_from_ifkey(const char*) { return reinterpret_cast<void*>(1); }
inline int esp_netif_get_ip_info(void*,esp_netif_ip_info_t* info) { info->ip.addr=0xc0a8017b; return ESP_OK; }
inline int esp_event_handler_register(esp_event_base_t,int,void(*)(void*,esp_event_base_t,int32_t,void*),void*) { return ESP_OK; }
struct TestDisplay {
    std::string text,notice,address;
    void SetLocalAddress(const char* value) { address=value; }
    void SetChatMessage(const char*,const char* value) { text=value; }
    void ShowNotification(const std::string& value,int) { notice=value; }
};
class Board { public:
    static Board& GetInstance() { static Board b; return b; }
    TestDisplay* GetDisplay() { static TestDisplay d; return &d; }
};
class Application { public:
    static Application& GetInstance() { static Application a; return a; }
    void Schedule(std::function<void()> action) { action(); }
};
enum httpd_method_t { HTTP_GET, HTTP_POST };
struct httpd_req_t {
    std::map<std::string,std::string> headers,response_headers;
    std::string body,sent,status,type;
    const char* uri="/";
    httpd_method_t method=HTTP_POST;
    size_t content_len=0,read=0;
    int chunk=7;
    bool send_fail=false;
};
using httpd_handle_t=void*;
struct httpd_config_t { unsigned server_port=80,ctrl_port=32768,stack_size=4096,max_open_sockets=7;
    bool lru_purge_enable=false; int recv_wait_timeout=5,send_wait_timeout=5; };
#define HTTPD_DEFAULT_CONFIG() httpd_config_t{}
constexpr int HTTPD_RESP_USE_STRLEN=-1;
struct httpd_uri_t { const char* uri; httpd_method_t method; esp_err_t(*handler)(httpd_req_t*); };
inline size_t httpd_req_get_hdr_value_len(httpd_req_t* r,const char* key) { return r->headers[key].size(); }
inline int httpd_req_get_hdr_value_str(httpd_req_t* r,const char* key,char* dest,size_t size) {
    const auto& value=r->headers[key]; if(value.size()>=size) return ESP_FAIL;
    memcpy(dest,value.c_str(),value.size()+1); return ESP_OK;
}
inline int httpd_req_recv(httpd_req_t* r,char* dest,size_t n) {
    if(r->chunk<=0) return -1;
    size_t count=std::min({n,size_t(r->chunk),r->body.size()-r->read});
    memcpy(dest,r->body.data()+r->read,count); r->read+=count; return count;
}
inline void httpd_resp_set_status(httpd_req_t* r,const char* status) { r->status=status; }
inline void httpd_resp_set_type(httpd_req_t* r,const char* type) { r->type=type; }
inline void httpd_resp_set_hdr(httpd_req_t* r,const char* key,const char* value) { r->response_headers[key]=value; }
inline int httpd_resp_send(httpd_req_t* r,const char* body,int size) {
    r->sent.assign(body,size<0?strlen(body):size); return r->send_fail?ESP_FAIL:ESP_OK;
}
inline int httpd_start(httpd_handle_t* h,const httpd_config_t*) { *h=reinterpret_cast<void*>(1); return ESP_OK; }
inline int httpd_stop(httpd_handle_t) { return ESP_OK; }
inline int httpd_register_uri_handler(httpd_handle_t,const httpd_uri_t*) { return ESP_OK; }
inline constexpr char CyberTrackPage[]="TEST_PAGE";
