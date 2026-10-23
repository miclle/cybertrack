idf_component_register(SRCS "board_check.c" "../../src/control.c"
    INCLUDE_DIRS "../../include"
    REQUIRES esp_psram esp_timer heap esp_app_format esp_hw_support)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
