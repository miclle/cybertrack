#include "linx_wire.h"
#include "yyjson.h"
#include <string.h>

static bool copy_string(yyjson_val *v, char *out, size_t cap)
{
    if (!yyjson_is_str(v)) return false;
    size_t n = yyjson_get_len(v);
    const char *p = yyjson_get_str(v);
    if (!n || n >= cap || memchr(p, 0, n) || memchr(p, '\r', n) || memchr(p, '\n', n)) return false;
    memcpy(out, p, n + 1);
    return true;
}

bool linx_parse_gateway(const char *json, size_t size, linx_gateway *out)
{
    memset(out, 0, sizeof(*out));
    yyjson_doc *doc = yyjson_read(json, size, 0);
    yyjson_val *root = yyjson_doc_get_root(doc);
    bool ok = false;
    if (!yyjson_is_obj(root) || yyjson_obj_get(root, "error")) goto done;
    yyjson_val *activation = yyjson_obj_get(root, "activation");
    if (activation) {
        if (!copy_string(yyjson_obj_get(activation, "code"), out->code, sizeof(out->code)) ||
            strlen(out->code) != 6) goto done;
        for (size_t i = 0; i < 6; ++i) if (out->code[i] < '0' || out->code[i] > '9') goto done;
        ok = true;
        goto done;
    }
    yyjson_val *ws = yyjson_obj_get(root, "websocket");
    char url[128];
    if (!copy_string(yyjson_obj_get(ws, "url"), url, sizeof(url)) ||
        !copy_string(yyjson_obj_get(ws, "token"), out->token, sizeof(out->token))) goto done;
    /* The official gateway still documents WS. Upgrade only this exact official
     * endpoint to its documented WSS counterpart; never send tokens in plaintext. */
    if (strcmp(url, "ws://xrobo-io.qiniuapi.com/v1/ws/") != 0 &&
        strcmp(url, "wss://xrobo-io.qiniuapi.com/v1/ws/") != 0) goto done;
    strcpy(out->url, "wss://xrobo-io.qiniuapi.com/v1/ws/");
    ok = true;
done:
    yyjson_doc_free(doc);
    if (!ok) memset(out, 0, sizeof(*out));
    return ok;
}

bool linx_parse_hello(const char *json, size_t size, char session[128])
{
    session[0] = 0;
    yyjson_doc *doc = yyjson_read(json, size, 0);
    yyjson_val *root = yyjson_doc_get_root(doc);
    const char *type = yyjson_get_str(yyjson_obj_get(root, "type"));
    const char *transport = yyjson_get_str(yyjson_obj_get(root, "transport"));
    yyjson_val *audio = yyjson_obj_get(root, "audio_params");
    yyjson_val *id = yyjson_obj_get(root, "session_id");
    bool ok = type && !strcmp(type, "hello") && transport && !strcmp(transport, "websocket") &&
              (!audio || yyjson_is_obj(audio)) && (!id || copy_string(id, session, 128));
    yyjson_doc_free(doc);
    return ok;
}

int linx_text_feed(linx_text *s, int opcode, bool fin, size_t offset,
                   size_t total, const char *data, size_t size)
{
    if (opcode >= 8 || opcode == 2) return 0;
    if ((opcode != 0 && opcode != 1) || size > total || offset > total - size ||
        total > LINX_TEXT_MAX || (!data && size)) return -1;
    if (offset == 0) {
        if (s->frame_active || (opcode == 1 && s->active) || (opcode == 0 && !s->active)) return -1;
        if (opcode == 1) { s->used = 0; s->active = true; }
        s->frame_size = total;
        s->frame_used = 0;
        s->opcode = opcode;
        s->frame_active = true;
    }
    if (!s->frame_active || s->opcode != opcode || total != s->frame_size ||
        offset != s->frame_used || size > LINX_TEXT_MAX - s->used) return -1;
    if (size) memcpy(s->text + s->used, data, size);
    s->used += size;
    s->frame_used += size;
    if (s->frame_used != total) return 0;
    s->frame_active = false;
    if (!fin) return 0;
    s->active = false;
    s->text[s->used] = 0;
    return 1;
}
