idf_component_register(
    SRCS "linx_main.c" "linx_wire.c" "water_policy.c" "water_mcp.c"
         "../../src/control.c" "../../src/protocol.c" "../../src/freshness.c"
         "../../src/replay_store.c" "../../src/replay_log.c"
         "../../third_party/yyjson/yyjson.c"
    INCLUDE_DIRS "../../include" "../../third_party/yyjson"
    REQUIRES esp_wifi esp_netif nvs_flash esp_http_client esp_websocket_client
             mbedtls json esp_timer esp_driver_gpio esp_driver_uart esp_app_format)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    YYJSON_DISABLE_WRITER=1 YYJSON_DISABLE_UTILS=1 YYJSON_DISABLE_NON_STANDARD=1)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
