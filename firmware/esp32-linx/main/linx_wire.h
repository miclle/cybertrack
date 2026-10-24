#ifndef LINX_WIRE_H
#define LINX_WIRE_H
#include <stdbool.h>
#include <stddef.h>
#define LINX_TEXT_MAX 2048
typedef struct {
    char code[7];
    char token[1024];
    char url[128];
} linx_gateway;
bool linx_parse_gateway(const char *json, size_t size, linx_gateway *out);
bool linx_parse_hello(const char *json, size_t size, char session[128]);
typedef struct {
    char text[LINX_TEXT_MAX + 1];
    size_t used, frame_used, frame_size;
    bool active, frame_active;
    int opcode;
} linx_text;
/* 1: complete text, 0: pending or control/binary frame, -1: invalid. */
int linx_text_feed(linx_text *s, int opcode, bool fin, size_t offset,
                   size_t total, const char *data, size_t size);
#endif
