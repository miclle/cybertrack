idf_component_register(SRCS "feedback.c" REQUIRES esp_driver_gpio esp_driver_i2c)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
