#include <assert.h>
#include <string.h>
#include "../xp-client/remote_control.h"

int main(void) {
    const char *token = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    char valid[256];
    strcpy(valid, "POST /ui/click HTTP/1.0\r\nX-Hermes-Token: ");
    strcat(valid, token);
    strcat(valid, "\r\nContent-Length: 9\r\n\r\nx=12&y=34");
    assert(hermesxp_remote_authorized(valid, token));
    assert(!hermesxp_remote_authorized(valid, "short"));
    valid[0] = 'G';
    assert(!hermesxp_remote_authorized(valid, token));

    strcpy(valid, "POST /ui/click HTTP/1.0\r\nX-Hermes-Token: ");
    strcat(valid, token);
    strcat(valid, "\r\nX-Hermes-Token: ");
    strcat(valid, token);
    strcat(valid, "\r\n\r\nx=1&y=2");
    assert(!hermesxp_remote_authorized(valid, token));

    assert(hermesxp_remote_parse_uint("0", 0, 1920, &(unsigned int){0}));
    assert(hermesxp_remote_parse_uint("1920", 0, 1920, &(unsigned int){0}));
    assert(!hermesxp_remote_parse_uint("1921", 0, 1920, &(unsigned int){0}));
    assert(!hermesxp_remote_parse_uint("-1", 0, 1920, &(unsigned int){0}));
    unsigned int x = 0, y = 0;
    int right = 0;
    assert(hermesxp_remote_parse_click("x=12&y=34&button=left", strlen("x=12&y=34&button=left"), 100, 100, &x, &y, &right));
    assert(x == 12 && y == 34 && right == 0);
    assert(hermesxp_remote_parse_click("x=99&y=99&button=right", strlen("x=99&y=99&button=right"), 100, 100, &x, &y, &right));
    assert(x == 99 && y == 99 && right == 1);
    assert(!hermesxp_remote_parse_click("x=-1&y=2&button=left", strlen("x=-1&y=2&button=left"), 100, 100, &x, &y, &right));
    const char *request = "POST /ui/click HTTP/1.0\r\nX-Hermes-Token: ";
    int has_length = 0, body_length = 0;
    char request_buffer[256];
    strcpy(request_buffer, request);
    strcat(request_buffer, token);
    strcat(request_buffer, "\r\nContent-Length: 9\r\n\r\nx=12&y=34");
    assert(hermesxp_remote_header_end(request_buffer, (int)strlen(request_buffer)) > 0);
    assert(hermesxp_remote_content_length(request_buffer, &body_length, &has_length));
    assert(has_length && body_length == 9);
    char duplicate[128];
    strcpy(duplicate, "POST /ui/type HTTP/1.0\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\na");
    assert(!hermesxp_remote_content_length(duplicate, &body_length, &has_length));
    assert(hermesxp_remote_text_is_safe("Hello, XP!", 10));
    assert(!hermesxp_remote_text_is_safe("line\nfeed", 9));
    assert(!hermesxp_remote_text_is_safe("", 0));
    assert(hermesxp_remote_key_code("Enter") == 0x0D);
    assert(hermesxp_remote_key_code("Left") == 0x25);
    assert(hermesxp_remote_key_code("Win") == 0);
    return 0;
}
