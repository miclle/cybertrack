#include "web_server.h"
#include "cybertrack_tools.h"
#include "web_page.h"
#include "application.h"
#include "board.h"
#include "display/display.h"
#include <esp_http_server.h>
#include <esp_event.h>
#include <esp_netif.h>
#include <esp_timer.h>
#include <esp_random.h>
#include <esp_log.h>
#include <cstdio>
#include <cstring>

namespace {
constexpr unsigned Port = 8080;
httpd_handle_t server = nullptr;
char bearer[33] = {};
uint32_t session = 0;
int64_t next_pair_attempt = 0;

bool Header(httpd_req_t* req, const char* key, const char* expected) {
    char value[96];
    return httpd_req_get_hdr_value_len(req, key) == strlen(expected) &&
           httpd_req_get_hdr_value_str(req, key, value, sizeof(value)) == ESP_OK && !strcmp(value, expected);
}
bool TrustedRequest(httpd_req_t* req) {
    esp_netif_ip_info_t info{};
    auto netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (!netif || esp_netif_get_ip_info(netif, &info) != ESP_OK || !info.ip.addr) return false;
    char host[32], origin[48];
    snprintf(host, sizeof(host), IPSTR ":%u", IP2STR(&info.ip), Port);
    snprintf(origin, sizeof(origin), "http://%s", host);
    if (!Header(req, "Host", host)) return false;
    // No CORS. The custom header also forces a preflight for cross-origin scripts.
    if (req->method != HTTP_GET && !Header(req, "X-CyberTrack-Client", "1")) return false;
    return !httpd_req_get_hdr_value_len(req, "Origin") || Header(req, "Origin", origin);
}
esp_err_t Send(httpd_req_t* req, const char* status, const char* body) {
    httpd_resp_set_status(req, status);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
    return httpd_resp_send(req, body, HTTPD_RESP_USE_STRLEN);
}
esp_err_t Error(httpd_req_t* req, const char* status, const char* reason) {
    char body[96]; snprintf(body, sizeof(body), "{\"result\":\"%s\"}", reason);
    // Close unread/rejected bodies instead of treating them as another request.
    httpd_resp_set_hdr(req, "Connection", "close");
    Send(req, status, body);
    return ESP_FAIL;
}
cJSON* Body(httpd_req_t* req) {
    if (!Header(req, "Content-Type", "application/json") || req->content_len == 0 || req->content_len > 384) return nullptr;
    char body[385]; size_t used = 0;
    while (used < req->content_len) {
        int n = httpd_req_recv(req, body + used, req->content_len - used);
        if (n <= 0) return nullptr;
        used += n;
    }
    body[used] = 0;
    if (memchr(body, 0, used)) return nullptr;
    return cJSON_ParseWithLengthOpts(body, used + 1, nullptr, true);
}
esp_err_t Page(httpd_req_t* req) {
    if (!TrustedRequest(req)) return Error(req, "403 Forbidden", "origin_rejected");
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'");
    httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
    httpd_resp_set_hdr(req, "Referrer-Policy", "no-referrer");
    return httpd_resp_send(req, CyberTrackPage, sizeof(CyberTrackPage) - 1);
}
esp_err_t Pair(httpd_req_t* req) {
    if (!TrustedRequest(req)) return Error(req, "403 Forbidden", "origin_rejected");
    const auto now = esp_timer_get_time();
    if (now < next_pair_attempt) return Error(req, "429 Too Many Requests", "pair_rate_limited");
    next_pair_attempt = now + 1000000;
    cJSON* body = Body(req);
    const bool valid = cJSON_IsObject(body) && cJSON_GetArraySize(body) == 0;
    cJSON_Delete(body);
    if (!valid) return Error(req, "400 Bad Request", "invalid_request");
    auto acquired = CyberTrackWebAcquire();
    if (!acquired) return Error(req, "409 Conflict", "control_busy");
    session = acquired;
    unsigned char bytes[16]; esp_fill_random(bytes, sizeof(bytes));
    for (unsigned i = 0; i < sizeof(bytes); ++i) snprintf(bearer + 2*i, 3, "%02x", bytes[i]);
    char reply[80]; snprintf(reply, sizeof(reply), "{\"result\":\"ok\",\"token\":\"%s\"}", bearer);
    const auto result = Send(req, "200 OK", reply);
    if (result != ESP_OK) CyberTrackWebCall(session, "release");
    return result;
}
esp_err_t Api(httpd_req_t* req) {
    if (!TrustedRequest(req)) return Error(req, "403 Forbidden", "origin_rejected");
    if (!session || !bearer[0] || !Header(req, "X-CyberTrack-Token", bearer))
        return Error(req, "401 Unauthorized", "session_expired");
    cJSON* body = Body(req);
    if (!cJSON_IsObject(body)) { cJSON_Delete(body); return Error(req, "400 Bad Request", "invalid_request"); }
    const bool action = !strcmp(req->uri, "/api/action");
    WebCommand command;
    if ((action && !ParseWebCommand(body, command)) || (!action && cJSON_GetArraySize(body))) {
        cJSON_Delete(body); return Error(req, "400 Bad Request", "invalid_request");
    }
    const char* operation = action ? command.operation : !strcmp(req->uri, "/api/state") ? "get_status" :
                            !strcmp(req->uri, "/api/stop") ? "stop" : "release";
    auto reply = CyberTrackWebCall(session, operation, action ? &command : nullptr);
    cJSON_Delete(body);
    bool expired = reply.find("\"result\":\"session_expired\"") != std::string::npos;
    if (expired || !strcmp(operation, "release")) { bearer[0] = 0; session = 0; }
    const auto result = Send(req, expired ? "401 Unauthorized" : "200 OK", reply.c_str());
    if (result != ESP_OK && session) CyberTrackWebCall(session, "release");
    return result;
}
void GotIp(void*, esp_event_base_t, int32_t, void* data) {
    const auto* event = static_cast<ip_event_got_ip_t*>(data);
    CyberTrackWifiLink(true);
    if (!server) {
        httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
        cfg.server_port = Port;
        cfg.ctrl_port = 32769; // Keep the upstream Wi-Fi provisioning server independent.
        cfg.stack_size = 8192;
        cfg.max_open_sockets = 2;
        cfg.lru_purge_enable = true;
        cfg.recv_wait_timeout = 1;
        cfg.send_wait_timeout = 1;
        auto error = httpd_start(&server, &cfg);
        if (error != ESP_OK) { ESP_LOGE("CT_WEB", "HTTP start failed: %s", esp_err_to_name(error)); return; }
        const struct { const char* uri; httpd_method_t method; esp_err_t (*handler)(httpd_req_t*); } routes[] = {
            {"/", HTTP_GET, Page}, {"/api/pair", HTTP_POST, Pair}, {"/api/state", HTTP_POST, Api},
            {"/api/action", HTTP_POST, Api}, {"/api/stop", HTTP_POST, Api}, {"/api/release", HTTP_POST, Api}
        };
        for (const auto& route : routes) {
            httpd_uri_t uri{}; uri.uri = route.uri; uri.method = route.method; uri.handler = route.handler;
            if (httpd_register_uri_handler(server, &uri) != ESP_OK) {
                httpd_stop(server); server = nullptr;
                ESP_LOGE("CT_WEB", "HTTP route registration failed"); return;
            }
        }
    }
    char address[48]; snprintf(address, sizeof(address), IPSTR ":%u", IP2STR(&event->ip_info.ip), Port);
    ESP_LOGI("CT_WEB", "Open http://%s", address);
    std::string url = std::string("http://") + address;
    Application::GetInstance().Schedule([url]() {
        auto display = Board::GetInstance().GetDisplay();
        display->SetChatMessage("system", url.c_str());
    });
}
}
void InitializeCyberTrackWeb() {
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, GotIp, nullptr));
}
