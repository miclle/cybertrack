#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <inttypes.h>
#include "cybertrack/protocol.h"
#include "linx_wire.h"
#include "water_mcp.h"
#include "esp_task_wdt.h"
#include "cJSON.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#define WIFI_UP BIT0
#define GATEWAY "https://xrobo.qiniuapi.com/v1/ota/"
static EventGroupHandle_t wifi_events;
static ct_controller control;
static ct_protocol protocol;
static nvs_handle_t settings;
static char device_id[18], client_id[37];
static QueueHandle_t messages;
static atomic_bool broken;
static atomic_bool safety_online;
static portMUX_TYPE water_lock = portMUX_INITIALIZER_UNLOCKED;
static water_policy water;
static TaskHandle_t safety_task_handle;
static linx_text incoming;
static char reply[CT_RPC_REPLY_CAP];
typedef struct { int kind; size_t size; char text[LINX_TEXT_MAX + 1]; } message;
static uint64_t now_ms(void) { return (uint64_t)esp_timer_get_time() / 1000; }
/* Only this bounded policy and the dedicated safety task can energize GPIO4.
 * Network parsing, TLS, logging and reply sends never hold water_lock. */
static void off(void)
{
    portENTER_CRITICAL(&water_lock);
    water_stop(&water, now_ms());
    (void)gpio_set_level(GPIO_NUM_4, 0);
    portEXIT_CRITICAL(&water_lock);
}
static water_policy water_snapshot(void)
{
    portENTER_CRITICAL(&water_lock);
    water_policy snapshot = water;
    portEXIT_CRITICAL(&water_lock);
    return snapshot;
}
static const char *request_water(const char *token, uint32_t duration)
{
    portENTER_CRITICAL(&water_lock);
    uint64_t now = now_ms();
    water_tick(&water, now, atomic_load(&safety_online) && !atomic_load(&broken), gpio_get_level(GPIO_NUM_0) == 0);
    const char *result = water_request(&water, now, token, duration);
    portEXIT_CRITICAL(&water_lock);
    return result;
}
static bool arm_water(char token[WATER_TOKEN_LEN + 1])
{
    unsigned char random[16]; esp_fill_random(random, sizeof(random));
    for (unsigned i = 0; i < sizeof(random); ++i) snprintf(token + i * 2, 3, "%02x", random[i]);
    portENTER_CRITICAL(&water_lock);
    uint64_t now = now_ms();
    water_tick(&water, now, atomic_load(&safety_online) && !atomic_load(&broken), gpio_get_level(GPIO_NUM_0) == 0);
    bool armed = water_arm(&water, now, token);
    portEXIT_CRITICAL(&water_lock);
    return armed;
}
static void safety_task(void *arg)
{
    (void)arg;
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    bool was_active = false;
    uint64_t started = 0;
    for (;;) {
        bool boot = gpio_get_level(GPIO_NUM_0) == 0;
        bool online = atomic_load(&safety_online) && !atomic_load(&broken);
        portENTER_CRITICAL(&water_lock);
        uint64_t now = now_ms();
        water_tick(&water, now, online, boot);
        bool active = water.active;
        esp_err_t output = gpio_set_level(GPIO_NUM_4, active ? 1 : 0);
        if (output != ESP_OK) { water_stop(&water, now); active = false; (void)gpio_set_level(GPIO_NUM_4, 0); }
        portEXIT_CRITICAL(&water_lock);
        if (active && !was_active) {
            started = now;
            /* No logging while energized: UART congestion must not delay BOOT/deadline. */
        }
        if (!active && was_active)
            printf("LINX WATER_OFF reason=%s software_on_ms=%" PRIu64 " outputs=OFF\n",
                   boot ? "BOOT" : !online ? "link_lost" : now - started < WATER_MS - 10 ? "stop" : "deadline",
                   now - started);
        was_active = active;
        ESP_ERROR_CHECK(esp_task_wdt_reset());
        const TickType_t poll = pdMS_TO_TICKS(5);
        vTaskDelay(poll ? poll : 1);
    }
}

static void require_ok(esp_err_t err)
{
    if (err == ESP_OK) return;
    off();
    printf("LINX FATAL %s outputs=OFF\n", esp_err_to_name(err));
    for (;;) vTaskDelay(pdMS_TO_TICKS(100));
}

static bool read_line(char *buf, size_t cap)
{
    static char line[512];
    static size_t used;
    static bool discard;
    unsigned char ch;
    while (uart_read_bytes(UART_NUM_0, &ch, 1, 0) == 1) {
        if (ch == '\n') {
            bool valid = !discard && used && used < cap;
            if (valid) { memcpy(buf, line, used); buf[used] = 0; }
            memset(line, 0, sizeof(line)); used = 0; discard = false;
            if (valid) return true;
        } else if (ch != '\r') {
            if (used == sizeof(line) - 1 || ch == 0) discard = true;
            if (!discard) line[used++] = (char)ch;
        }
    }
    return false;
}

static bool provision(const char *line, wifi_config_t *cfg)
{
    cJSON *root = cJSON_Parse(line);
    const char *ssid = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(root, "ssid"));
    const char *pass = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(root, "password"));
    bool valid = ssid && pass && strlen(ssid) > 0 && strlen(ssid) <= 32 && strlen(pass) <= 63;
    if (valid) {
        memset(cfg, 0, sizeof(*cfg));
        memcpy(cfg->sta.ssid, ssid, strlen(ssid));
        memcpy(cfg->sta.password, pass, strlen(pass));
        require_ok(nvs_set_str(settings, "ssid", ssid));
        require_ok(nvs_set_str(settings, "password", pass));
        require_ok(nvs_commit(settings));
    }
    if (pass) memset((char *)pass, 0, strlen(pass));
    cJSON_Delete(root);
    return valid;
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_events, WIFI_UP);
        atomic_store(&broken, true);
        off();
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(wifi_events, WIFI_UP);
}

static void start_wifi(void)
{
    /* Never erase a pre-existing NVS partition to recover an initialization error. */
    require_ok(nvs_flash_init());
    require_ok(nvs_open("linx", NVS_READWRITE, &settings));
    size_t n = sizeof(client_id);
    if (nvs_get_str(settings, "client_id", client_id, &n) != ESP_OK) {
        unsigned char b[16]; esp_fill_random(b, sizeof(b));
        b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
        snprintf(client_id, sizeof(client_id),
                 "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
                 b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15]);
        require_ok(nvs_set_str(settings, "client_id", client_id));
        require_ok(nvs_commit(settings));
    }
    uint8_t mac[6]; require_ok(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    snprintf(device_id, sizeof(device_id), "%02X:%02X:%02X:%02X:%02X:%02X", MAC2STR(mac));
    wifi_config_t cfg = {0};
    char ssid[33] = {0}, pass[64] = {0};
    n = sizeof(ssid);
    esp_err_t ssid_err = nvs_get_str(settings, "ssid", ssid, &n);
    n = sizeof(pass);
    esp_err_t pass_err = nvs_get_str(settings, "password", pass, &n);
    if (ssid_err == ESP_OK && pass_err == ESP_OK && ssid[0]) {
        memcpy(cfg.sta.ssid, ssid, strlen(ssid));
        memcpy(cfg.sta.password, pass, strlen(pass));
    } else {
        printf("LINX WIFI_CONFIG_REQUIRED outputs=OFF\n");
        char line[512];
        uint64_t prompt_at = now_ms();
        for (;;) {
            if (now_ms() - prompt_at >= 5000) {
                printf("LINX WIFI_CONFIG_REQUIRED outputs=OFF\n"); prompt_at = now_ms();
            }
            if (read_line(line, sizeof(line))) {
                bool ok = provision(line, &cfg);
                memset(line, 0, sizeof(line));
                if (ok) break;
                printf("LINX WIFI_CONFIG_INVALID\n");
            }
            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }
    memset(pass, 0, sizeof(pass));
    wifi_events = xEventGroupCreate();
    if (!wifi_events) require_ok(ESP_ERR_NO_MEM);
    require_ok(esp_netif_init());
    require_ok(esp_event_loop_create_default());
    if (!esp_netif_create_default_wifi_sta()) require_ok(ESP_ERR_NO_MEM);
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    require_ok(esp_wifi_init(&init));
    require_ok(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    require_ok(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    require_ok(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    require_ok(esp_wifi_set_mode(WIFI_MODE_STA));
    require_ok(esp_wifi_set_config(WIFI_IF_STA, &cfg));
    memset(&cfg, 0, sizeof(cfg));
    require_ok(esp_wifi_start());
}

typedef struct { char text[8192]; size_t used; bool overflow; } http_body;
static esp_err_t http_event(esp_http_client_event_t *event)
{
    http_body *body = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && event->data_len > 0) {
        size_t n = (size_t)event->data_len;
        if (n >= sizeof(body->text) - body->used) { body->overflow = true; return ESP_FAIL; }
        memcpy(body->text + body->used, event->data, n); body->used += n;
        body->text[body->used] = 0;
    }
    return ESP_OK;
}

static bool synchronize_time(void)
{
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_err_t err = esp_netif_sntp_init(&config);
    if (err != ESP_OK) return false;
    err = esp_netif_sntp_sync_wait(pdMS_TO_TICKS(30000));
    esp_netif_sntp_deinit();
    printf("LINX TIME_SYNC %s\n", err == ESP_OK ? "OK" : "FAILED");
    return err == ESP_OK;
}

static bool gateway(linx_gateway *out)
{
    http_body *body = calloc(1, sizeof(*body));
    if (!body) return false;
    wifi_ap_record_t ap = {0}; esp_wifi_sta_get_ap_info(&ap);
    char ssid[33] = {0}; memcpy(ssid, ap.ssid, 32);
    char hash[65]; esp_app_get_elf_sha256(hash, sizeof(hash));
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "mac_address", device_id);
    cJSON_AddStringToObject(root, "uuid", client_id);
    cJSON_AddStringToObject(root, "chip_model_name", "esp32s3");
    cJSON *app = cJSON_AddObjectToObject(root, "application");
    cJSON_AddStringToObject(app, "version", esp_app_get_description()->version);
    cJSON_AddStringToObject(app, "elf_sha256", hash);
    cJSON *board = cJSON_AddObjectToObject(root, "board");
    cJSON_AddStringToObject(board, "type", "cybertrack-s3-water-bench");
    cJSON_AddStringToObject(board, "ssid", ssid);
    cJSON_AddNumberToObject(board, "rssi", ap.rssi);
    char *request = cJSON_PrintUnformatted(root); cJSON_Delete(root);
    if (!request) { free(body); return false; }
    esp_http_client_config_t cfg = {
        .url = GATEWAY, .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 15000, .event_handler = http_event, .user_data = body,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t http = esp_http_client_init(&cfg);
    bool ok = false;
    if (http) {
        esp_http_client_set_method(http, HTTP_METHOD_POST);
        esp_http_client_set_header(http, "Content-Type", "application/json");
        esp_http_client_set_header(http, "Activation-Version", "1");
        esp_http_client_set_header(http, "Device-Id", device_id);
        esp_http_client_set_header(http, "Client-Id", client_id);
        esp_http_client_set_header(http, "User-Agent", "cybertrack-s3/0.2.0");
        esp_http_client_set_post_field(http, request, strlen(request));
        esp_err_t err = esp_http_client_perform(http);
        int status = esp_http_client_get_status_code(http);
        ok = err == ESP_OK && status == 200 && !body->overflow &&
             linx_parse_gateway(body->text, body->used, out);
        if (!ok) printf("LINX GATEWAY_FAILED http=%d transport=%s\n", status, esp_err_to_name(err));
        esp_http_client_cleanup(http);
    }
    memset(body, 0, sizeof(*body)); free(body); free(request);
    return ok;
}

static void ws_event(void *arg, esp_event_base_t base, int32_t id, void *event_data)
{
    (void)arg; (void)base;
    esp_websocket_event_data_t *data = event_data;
    if (id == WEBSOCKET_EVENT_DISCONNECTED || id == WEBSOCKET_EVENT_ERROR || id == WEBSOCKET_EVENT_CLOSED) {
        atomic_store(&broken, true); off();
        printf("LINX WS_CLOSED event=%ld code=%d error=%d tls=%d\n", (long)id, data->close_status_code, data->error_handle.error_type, data->error_handle.esp_tls_cert_verify_flags);
        atomic_store(&broken, true); off(); return;
    }
    message msg = {0};
    if (id == WEBSOCKET_EVENT_CONNECTED) msg.kind = 1;
    else if (id == WEBSOCKET_EVENT_DATA) {
        if (data->data_len < 0 || data->payload_offset < 0 || data->payload_len < 0) {
            atomic_store(&broken, true); return;
        }
        int result = linx_text_feed(&incoming, data->op_code, data->fin,
                                   (size_t)data->payload_offset, (size_t)data->payload_len,
                                   data->data_ptr, (size_t)data->data_len);
        if (result < 0) {
            atomic_store(&broken, true); off();
            printf("LINX RX_REJECT opcode=%d fin=%d offset=%d total=%d size=%d\n", data->op_code, data->fin, data->payload_offset, data->payload_len, data->data_len);
            atomic_store(&broken, true); return;
        }
        if (!result) return;
        msg.kind = 2; msg.size = incoming.used;
        memcpy(msg.text, incoming.text, msg.size + 1);
    } else return;
    if (xQueueSend(messages, &msg, 0) != pdTRUE) { atomic_store(&broken, true); off(); printf("LINX RX_OVERFLOW\n"); }
}

static bool send_text(esp_websocket_client_handle_t ws, const char *text)
{
    int size = (int)strlen(text);
    return esp_websocket_client_send_text(ws, text, size, pdMS_TO_TICKS(1000)) == size;
}

static void run_session(linx_gateway *gateway_result)
{
    char headers[1400];
    snprintf(headers, sizeof(headers),
             "Authorization: Bearer %s\r\nDevice-Id: %s\r\nClient-Id: %s\r\nProtocol-Version: 1\r\n",
             gateway_result->token, device_id, client_id);
    esp_websocket_client_config_t cfg = {
        .uri = gateway_result->url, .headers = headers,
        .crt_bundle_attach = esp_crt_bundle_attach, .disable_auto_reconnect = true,
        .network_timeout_ms = 10000, .task_stack = 8192, .buffer_size = 1024,
    };
    memset(&incoming, 0, sizeof(incoming)); xQueueReset(messages);
    atomic_store(&broken, false);
    esp_websocket_client_handle_t ws = esp_websocket_client_init(&cfg);
    if (!ws) return;
    require_ok(esp_websocket_register_events(ws, WEBSOCKET_EVENT_ANY, ws_event, NULL));
    if (esp_websocket_client_start(ws) != ESP_OK) atomic_store(&broken, true);
    uint64_t deadline = now_ms() + 20000;
    bool ready = false;
    char session[128] = {0};
    message msg;
    while (!atomic_load(&broken) && (xEventGroupGetBits(wifi_events) & WIFI_UP)) {
        ct_set_stop(&control, gpio_get_level(GPIO_NUM_0) == 0);
        ct_tick(&control, now_ms());
        if (!ready && now_ms() >= deadline) { printf("LINX HELLO_TIMEOUT\n"); break; }
        if (xQueueReceive(messages, &msg, pdMS_TO_TICKS(10)) == pdTRUE) {
            if (msg.kind == 1) {
                printf("LINX WSS_CONNECTED outputs=OFF\n");
                if (!send_text(ws, "{\"type\":\"hello\",\"version\":1,\"features\":{\"mcp\":true},\"transport\":\"websocket\",\"audio_params\":{}}")) break;
                deadline = now_ms() + 10000;
            } else if (!ready) {
                if (!linx_parse_hello(msg.text, msg.size, session)) { printf("LINX HELLO_INVALID\n"); break; }
                if (!ct_protocol_open(&protocol, now_ms())) break;
                ready = true;
                atomic_store(&safety_online, true);
                printf("LINX HELLO_OK tools=status,stop,water water=local-single-use-only\n");
            } else {
                cJSON *root = cJSON_ParseWithLength(msg.text, msg.size);
                const char *type = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(root, "type"));
                bool mcp = type && !strcmp(type, "mcp");
                if (type && (!strcmp(type, "tts") || !strcmp(type, "stt") || !strcmp(type, "error") || !strcmp(type, "goodbye")))
                    printf("LINX EVENT %s\n", type);
                if (mcp) {
                    ct_rpc_delivery delivery = {.session = protocol.session, .received_at_ms = now_ms(),
                                                .enable_generation = control.enable_generation};
                    water_callbacks cb = {.snapshot = water_snapshot, .stop = off, .request = request_water};
                    ct_rpc_result result = water_mcp_handle(&protocol, msg.text, msg.size, delivery,
                                                             now_ms(), reply, sizeof(reply), cb);
                    if (result == CT_RPC_BAD_ARGUMENT) { off(); atomic_store(&broken, true); }
                    cJSON *payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
                    const char *method = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(payload, "method"));
                    const char *label = "other";
                    if (method && !strcmp(method, "initialize")) label = "initialize";
                    if (method && !strcmp(method, "tools/list")) label = "tools/list";
                    if (method && !strcmp(method, "tools/call")) {
                        cJSON *params = cJSON_GetObjectItemCaseSensitive(payload, "params");
                        const char *name = cJSON_GetStringValue(cJSON_GetObjectItemCaseSensitive(params, "name"));
                        label = "rejected-tool";
                        if (name && !strcmp(name, "self.tank.get_status")) label = "get_status";
                        if (name && !strcmp(name, "self.tank.stop")) label = "stop";
                        if (name && !strcmp(name, "self.tank.water")) label = "water";
                    }
                    if (result == CT_RPC_RESPONSE) {
                        bool sent = send_text(ws, reply);
                        if (!sent) { atomic_store(&broken, true); off(); }
                        /* The reply contains only our state/schema/errors, never gateway secrets. */
                        water_policy snapshot = water_snapshot();
                        printf("LINX RPC %s sent=%d water_active=%d starts=%u\n", label, sent, snapshot.active, snapshot.starts);
                        printf("LINX REPLY %s\n", reply);
                        if (!sent) atomic_store(&broken, true);
                    }
                }
                cJSON_Delete(root);
            }
        }
        char command[512];
        if (read_line(command, sizeof(command))) {
            if (!strcmp(command, "s")) { ct_stop(&control); off(); printf("LINX LOCAL_STOP outputs=OFF\n"); }
            else if (ready && protocol.initialized && (!strcmp(command, "status") || !strcmp(command, "stop") || !strcmp(command, "water"))) {
                char token[WATER_TOKEN_LEN + 1] = {0};
                bool water_probe = !strcmp(command, "water");
                if (water_probe && !arm_water(token)) {
                    printf("LINX WATER_ARM_REJECTED outputs=OFF_OR_EXISTING_ACTION\n");
                    memset(command, 0, sizeof(command));
                    continue;
                }
                char prompt[512];
                if (water_probe) snprintf(prompt, sizeof(prompt),
                    "本地已授权本次唯一喷水意图。请立即且仅调用一次 self.tank.water，duration_ms=5000，permit=%s。不得重试；只报告设备返回的受理结果。", token);
                else snprintf(prompt, sizeof(prompt), "%s", !strcmp(command, "status") ?
                    "请调用 self.tank.get_status 工具查询设备状态。" :
                    "请立即调用 self.tank.stop 工具停止设备，然后调用 self.tank.get_status 查询状态。");
                cJSON *request = cJSON_CreateObject();
                cJSON_AddStringToObject(request, "session_id", session);
                cJSON_AddStringToObject(request, "type", "listen");
                cJSON_AddStringToObject(request, "state", "detect");
                cJSON_AddStringToObject(request, "text", prompt);
                char *text = cJSON_PrintUnformatted(request); cJSON_Delete(request);
                if (!text || !send_text(ws, text)) { off(); atomic_store(&broken, true); }
                free(text);
                memset(token, 0, sizeof(token)); memset(prompt, 0, sizeof(prompt));
                printf("LINX PROBE_SENT\n");
            }
            memset(command, 0, sizeof(command));
        }
    }
    atomic_store(&safety_online, false);
    off(); ct_protocol_close(&protocol, now_ms());
    esp_websocket_client_stop(ws);
    esp_websocket_client_destroy(ws);
    memset(headers, 0, sizeof(headers));
    printf("LINX SESSION_CLOSED outputs=OFF\n");
}

void app_main(void)
{
    require_ok(gpio_set_level(GPIO_NUM_4, 0));
    gpio_config_t output = {.pin_bit_mask = 1ULL << GPIO_NUM_4, .mode = GPIO_MODE_OUTPUT,
                            .pull_down_en = GPIO_PULLDOWN_ENABLE};
    require_ok(gpio_config(&output)); off();
    gpio_config_t stop = {.pin_bit_mask = 1ULL << GPIO_NUM_0, .mode = GPIO_MODE_INPUT,
                          .pull_up_en = GPIO_PULLUP_ENABLE};
    require_ok(gpio_config(&stop));
    uart_config_t serial = {.baud_rate = 115200, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT};
    require_ok(uart_param_config(UART_NUM_0, &serial));
    require_ok(uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0));
    /* SDK transport errors can include URLs/headers; use our redacted diagnostics. */
    esp_log_level_set("*", ESP_LOG_NONE);
    ct_init(&control, (ct_limits){0}, now_ms());
    ct_boot_complete(&control);
    ct_protocol_init(&protocol, &control, 0);
    messages = xQueueCreate(8, sizeof(message));
    if (!messages) require_ok(ESP_ERR_NO_MEM);
    if (xTaskCreate(safety_task, "water_safety", 4096, NULL, 10, &safety_task_handle) != pdPASS) require_ok(ESP_ERR_NO_MEM);
    printf("LINX READY 0.2.0 GPIO4=LOW water=local-single-use-only max_ms=5000 audio=disabled\n");
    start_wifi();
    bool time_ready = false;
    for (;;) {
        off();
        if (!(xEventGroupWaitBits(wifi_events, WIFI_UP, pdFALSE, pdTRUE, pdMS_TO_TICKS(15000)) & WIFI_UP)) {
            printf("LINX WIFI_WAIT outputs=OFF\n"); continue;
        }
        printf("LINX WIFI_CONNECTED\n");
        if (!time_ready) {
            time_ready = synchronize_time();
            if (!time_ready) { vTaskDelay(pdMS_TO_TICKS(10000)); continue; }
        }
        linx_gateway result;
        if (gateway(&result)) {
            if (result.code[0]) {
                /* Serial display only: the host helper must redact this from logs. */
                printf("LINX ACTIVATION_CODE %s\n", result.code);
            } else {
                printf("LINX BOUND\n"); run_session(&result);
            }
        }
        memset(&result, 0, sizeof(result));
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
