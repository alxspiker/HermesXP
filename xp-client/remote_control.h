#ifndef HERMESXP_REMOTE_CONTROL_H
#define HERMESXP_REMOTE_CONTROL_H

static int remote_hex(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

static int remote_token_is_valid(const char *token) {
    int i = 0;
    if (!token) return 0;
    while (i < 64 && token[i]) {
        if (!remote_hex((unsigned char)token[i])) return 0;
        ++i;
    }
    return i == 64 && token[i] == 0;
}

static int remote_ct_equal(const char *a, const char *b, int n) {
    unsigned int diff = 0;
    int i;
    for (i = 0; i < n; ++i) diff |= (unsigned char)a[i] ^ (unsigned char)b[i];
    return diff == 0;
}

static int remote_line_prefix(const char *line, const char *prefix) {
    int i = 0;
    while (prefix[i]) {
        unsigned char a = (unsigned char)line[i], b = (unsigned char)prefix[i];
        if (a >= 'a' && a <= 'z') a = (unsigned char)(a - 'a' + 'A');
        if (b >= 'a' && b <= 'z') b = (unsigned char)(b - 'a' + 'A');
        if (a != b) return 0;
        ++i;
    }
    return 1;
}

static int hermesxp_remote_authorized(const char *request, const char *token) {
    const char *p, *line_end;
    int found = 0;
    if (!request || !remote_token_is_valid(token)) return 0;
    line_end = request;
    while (*line_end && !(line_end[0] == '\r' && line_end[1] == '\n')) ++line_end;
    if (!*line_end || !(remote_line_prefix(request, "GET /ui/") ||
        remote_line_prefix(request, "POST /ui/") || remote_line_prefix(request, "GET /screenshot.bmp") ||
        remote_line_prefix(request, "POST /update/exe ") || remote_line_prefix(request, "GET /update/status ") ||
        remote_line_prefix(request, "POST /update/helper ") || remote_line_prefix(request, "GET /update/helper-status ") ||
        remote_line_prefix(request, "POST /system/service ") ||
        remote_line_prefix(request, "GET /network/status "))) return 0;
    p = line_end + 2;
    while (*p) {
        const char *end = p;
        while (*end && !(end[0] == '\r' && end[1] == '\n')) ++end;
        if (end == p) break;
        if (remote_line_prefix(p, "X-Hermes-Token: ")) {
            static const char token_header[] = "X-Hermes-Token: ";
            int i;
            if (found || !remote_line_prefix(p, token_header)) return 0;
            p += sizeof(token_header) - 1;
            if (end - p != 64 || !remote_ct_equal(p, token, 64)) return 0;
            for (i = 0; i < 64; ++i) if (!remote_hex((unsigned char)p[i])) return 0;
            found = 1;
        }
        if (!*end) break;
        p = end + 2;
    }
    return found;
}

static int hermesxp_remote_parse_uint(const char *text, unsigned int min_value,
        unsigned int max_value, unsigned int *out) {
    unsigned int value = 0;
    int i = 0;
    if (!text || !out || !text[0]) return 0;
    while (text[i]) {
        unsigned int digit;
        if (text[i] < '0' || text[i] > '9') return 0;
        digit = (unsigned int)(text[i] - '0');
        if (digit > max_value || value > (max_value - digit) / 10) return 0;
        value = value * 10 + digit;
        ++i;
    }
    if (value < min_value || value > max_value) return 0;
    *out = value;
    return 1;
}

static int remote_literal_equal(const char *a, const char *b, int length) {
    int i;
    for (i = 0; i < length; ++i) if (a[i] != b[i]) return 0;
    return 1;
}

static int hermesxp_remote_header_end(const char *request, int length) {
    int i;
    if (!request || length < 4) return 0;
    for (i = 0; i <= length - 4; ++i)
        if (request[i] == '\r' && request[i + 1] == '\n' && request[i + 2] == '\r' && request[i + 3] == '\n') return i + 4;
    return 0;
}

static int hermesxp_remote_content_length(const char *request, int *length, int *present) {
    const char *p, *end;
    int header_end, found = 0, request_len = 0;
    unsigned int value = 0;
    if (!request || !length || !present) return 0;
    while (request[request_len]) ++request_len;
    header_end = hermesxp_remote_header_end(request, request_len);
    if (!header_end) return 0;
    *present = 0; *length = 0;
    p = request;
    while (*p && !(p[0] == '\r' && p[1] == '\n')) ++p;
    if (!*p) return 0;
    p += 2;
    while (*p && !(p[0] == '\r' && p[1] == '\n')) {
        char number[8];
        int n = 0;
        end = p;
        while (*end && !(end[0] == '\r' && end[1] == '\n')) ++end;
        if (remote_line_prefix(p, "Content-Length: ")) {
            if (found) return 0;
            p += 16;
            while (p < end) {
                if (n >= (int)sizeof(number) - 1) return 0;
                number[n++] = *p++;
            }
            number[n] = 0;
            if (!hermesxp_remote_parse_uint(number, 0, 512, &value)) return 0;
            found = 1;
        }
        p = end + 2;
    }
    *present = found;
    *length = (int)value;
    return 1;
}

static int hermesxp_remote_parse_click(const char *body, int length,
        unsigned int width, unsigned int height, unsigned int *x, unsigned int *y, int *right) {
    char number[12];
    int i = 2, n = 0;
    if (!body || !x || !y || !right || width == 0 || height == 0 || length < 19 ||
        body[0] != 'x' || body[1] != '=') return 0;
    while (i < length && body[i] != '&') {
        if (n >= (int)sizeof(number) - 1) return 0;
        number[n++] = body[i++];
    }
    if (i >= length || body[i] != '&') return 0;
    number[n] = 0;
    if (!hermesxp_remote_parse_uint(number, 0, width - 1, x)) return 0;
    ++i;
    if (i + 2 >= length || body[i] != 'y' || body[i + 1] != '=') return 0;
    i += 2; n = 0;
    while (i < length && body[i] != '&') {
        if (n >= (int)sizeof(number) - 1) return 0;
        number[n++] = body[i++];
    }
    if (i >= length || body[i] != '&') return 0;
    number[n] = 0;
    if (!hermesxp_remote_parse_uint(number, 0, height - 1, y)) return 0;
    ++i;
    if (length - i == 12 && remote_literal_equal(body + i, "button=right", 12)) { *right = 1; return 1; }
    if (length - i == 11 && remote_literal_equal(body + i, "button=left", 11)) { *right = 0; return 1; }
    return 0;
}

static int remote_take_field(const char *body, int length, int *offset,
        const char *key, char *value, int value_size, int more) {
    int key_length = 0, n = 0;
    while (key[key_length]) ++key_length;
    if (!body || !offset || !value || value_size < 2 || *offset < 0 ||
        length < *offset || length - *offset < key_length ||
        !remote_literal_equal(body + *offset, key, key_length)) return 0;
    *offset += key_length;
    while (*offset < length && body[*offset] != '&') {
        if (n >= value_size - 1) return 0;
        value[n++] = body[(*offset)++];
    }
    if (n == 0) return 0;
    value[n] = 0;
    if (more) {
        if (*offset >= length || body[*offset] != '&') return 0;
        ++*offset;
    } else if (*offset != length) return 0;
    return 1;
}

static int hermesxp_remote_parse_drag(const char *body, int length,
        unsigned int width, unsigned int height, unsigned int *x1, unsigned int *y1,
        unsigned int *x2, unsigned int *y2) {
    char value[12];
    int offset = 0;
    if (!body || !x1 || !y1 || !x2 || !y2 || width == 0 || height == 0 ||
        length < 1 || length > 47) return 0;
    if (!remote_take_field(body,length,&offset,"x1=",value,sizeof(value),1) ||
        !hermesxp_remote_parse_uint(value,0,width-1,x1) ||
        !remote_take_field(body,length,&offset,"y1=",value,sizeof(value),1) ||
        !hermesxp_remote_parse_uint(value,0,height-1,y1) ||
        !remote_take_field(body,length,&offset,"x2=",value,sizeof(value),1) ||
        !hermesxp_remote_parse_uint(value,0,width-1,x2) ||
        !remote_take_field(body,length,&offset,"y2=",value,sizeof(value),0) ||
        !hermesxp_remote_parse_uint(value,0,height-1,y2)) return 0;
    return 1;
}

static int remote_parse_delta(const char *text, int *delta) {
    int i = 0, sign = 1, value = 0;
    if (!text || !delta || !text[0]) return 0;
    if (text[i] == '-') { sign = -1; ++i; }
    if (!text[i]) return 0;
    for (; text[i]; ++i) {
        if (text[i] < '0' || text[i] > '9') return 0;
        value = value * 10 + (text[i] - '0');
        if (value > 5) return 0;
    }
    *delta = sign * value;
    return *delta != 0;
}

static int hermesxp_remote_parse_scroll(const char *body, int length,
        unsigned int width, unsigned int height, unsigned int *x, unsigned int *y, int *delta) {
    char value[12];
    int offset = 0;
    if (!body || !x || !y || !delta || width == 0 || height == 0 ||
        length < 1 || length > 40) return 0;
    if (!remote_take_field(body,length,&offset,"x=",value,sizeof(value),1) ||
        !hermesxp_remote_parse_uint(value,0,width-1,x) ||
        !remote_take_field(body,length,&offset,"y=",value,sizeof(value),1) ||
        !hermesxp_remote_parse_uint(value,0,height-1,y) ||
        !remote_take_field(body,length,&offset,"delta=",value,sizeof(value),0) ||
        !remote_parse_delta(value,delta)) return 0;
    return 1;
}

static unsigned int hermesxp_remote_double_click_delay(unsigned int system_ms) {
    unsigned int delay = system_ms / 4u;
    if (delay < 10u) delay = 10u;
    if (delay > 100u) delay = 100u;
    return delay;
}

static int hermesxp_remote_rate_allowed(unsigned int now, unsigned int *last,
        unsigned int *seen) {
    if (!last || !seen) return 0;
    if (*seen && (unsigned int)(now - *last) < 100u) return 0;
    *last = now;
    *seen = 1;
    return 1;
}

static int hermesxp_remote_text_is_safe(const char *text, int length) {
    int i;
    if (!text || length < 1 || length > 128) return 0;
    for (i = 0; i < length; ++i) if ((unsigned char)text[i] < 32 || (unsigned char)text[i] > 126) return 0;
    return 1;
}

static int remote_string_equal(const char *a, const char *b) {
    int i = 0;
    if (!a || !b) return 0;
    while (a[i] && b[i] && a[i] == b[i]) ++i;
    return a[i] == 0 && b[i] == 0;
}

static unsigned int hermesxp_remote_key_code(const char *name) {
    if (remote_string_equal(name, "Enter")) return 0x0D;
    if (remote_string_equal(name, "Tab")) return 0x09;
    if (remote_string_equal(name, "Esc")) return 0x1B;
    if (remote_string_equal(name, "Backspace")) return 0x08;
    if (remote_string_equal(name, "Delete")) return 0x2E;
    if (remote_string_equal(name, "Left")) return 0x25;
    if (remote_string_equal(name, "Up")) return 0x26;
    if (remote_string_equal(name, "Right")) return 0x27;
    if (remote_string_equal(name, "Down")) return 0x28;
    return 0;
}

#endif
