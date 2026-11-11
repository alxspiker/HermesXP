#include <assert.h>
#include <string.h>
#include "../xp-client/remote_control.h"
#include "../xp-client/service_control.h"

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
    unsigned int x1 = 0, y1 = 0, x2 = 0, y2 = 0;
    int delta = 0;
    assert(hermesxp_remote_parse_drag("x1=1&y1=2&x2=90&y2=80", strlen("x1=1&y1=2&x2=90&y2=80"), 100, 100, &x1, &y1, &x2, &y2));
    assert(x1 == 1 && y1 == 2 && x2 == 90 && y2 == 80);
    assert(!hermesxp_remote_parse_drag("x1=1&y1=2&x2=100&y2=80", strlen("x1=1&y1=2&x2=100&y2=80"), 100, 100, &x1, &y1, &x2, &y2));
    assert(!hermesxp_remote_parse_drag("x1=1&y1=2&x2=90&y2=80&extra=1", strlen("x1=1&y1=2&x2=90&y2=80&extra=1"), 100, 100, &x1, &y1, &x2, &y2));
    assert(hermesxp_remote_parse_scroll("x=10&y=20&delta=-5", strlen("x=10&y=20&delta=-5"), 100, 100, &x, &y, &delta));
    assert(x == 10 && y == 20 && delta == -5);
    assert(!hermesxp_remote_parse_scroll("x=10&y=20&delta=6", strlen("x=10&y=20&delta=6"), 100, 100, &x, &y, &delta));
    assert(!hermesxp_remote_parse_scroll("x=10&y=20&delta=0", strlen("x=10&y=20&delta=0"), 100, 100, &x, &y, &delta));
    assert(hermesxp_remote_double_click_delay(500) == 100);
    assert(hermesxp_remote_double_click_delay(200) == 50);
    assert(hermesxp_remote_double_click_delay(0) == 10);
    unsigned int last_action = 0, action_seen = 0;
    assert(hermesxp_remote_rate_allowed(1000, &last_action, &action_seen));
    assert(!hermesxp_remote_rate_allowed(1099, &last_action, &action_seen));
    assert(hermesxp_remote_rate_allowed(1100, &last_action, &action_seen));
    assert(!hermesxp_remote_rate_allowed(1150, &last_action, &action_seen));
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
    char svc_request[256];
    strcpy(svc_request, "POST /system/service HTTP/1.0\r\nX-Hermes-Token: ");
    strcat(svc_request, token);
    strcat(svc_request, "\r\nContent-Length: 34\r\n\r\naction=restart&name=FreeSSHDService");
    assert(hermesxp_remote_authorized(svc_request, token));
    strcpy(svc_request, "GET /network/status HTTP/1.0\r\nX-Hermes-Token: ");
    strcat(svc_request, token);
    strcat(svc_request, "\r\n\r\n");
    assert(hermesxp_remote_authorized(svc_request, token));
    svc_request[0]='P';
    assert(!hermesxp_remote_authorized(svc_request, token));
    HERMESXP_SERVICE_COMMAND cmd;
    assert(hermesxp_service_parse("action=status&name=AudioSrv", strlen("action=status&name=AudioSrv"), &cmd));
    assert(cmd.action == HERMESXP_SERVICE_STATUS && strcmp(cmd.name, "AudioSrv")==0);
    assert(hermesxp_service_parse("action=restart&name=FreeSSHDService", strlen("action=restart&name=FreeSSHDService"), &cmd));
    assert(cmd.action == HERMESXP_SERVICE_RESTART && strcmp(cmd.name, "FreeSSHDService")==0);
    assert(hermesxp_service_parse("action=stop&name=SQL Server", strlen("action=stop&name=SQL Server"), &cmd));
    assert(cmd.action == HERMESXP_SERVICE_STOP);
    assert(hermesxp_service_parse("action=start&name=MSSQL$SQLEXPRESS", strlen("action=start&name=MSSQL$SQLEXPRESS"), &cmd));
    assert(cmd.action == HERMESXP_SERVICE_START);
    assert(!hermesxp_service_parse("action=delete&name=AudioSrv", strlen("action=delete&name=AudioSrv"), &cmd));
    assert(!hermesxp_service_parse("action=restart&name=AudioSrv&extra=1", strlen("action=restart&name=AudioSrv&extra=1"), &cmd));
    assert(!hermesxp_service_parse("action=start&name=a/b", strlen("action=start&name=a/b"), &cmd));
    assert(!hermesxp_service_parse("action=start&name= A", strlen("action=start&name= A"), &cmd));
    assert(!hermesxp_service_parse("action=start&name=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                                   strlen("action=start&name=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), &cmd));
    return 0;
}
