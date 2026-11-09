#ifndef HERMESXP_SERVICE_CONTROL_H
#define HERMESXP_SERVICE_CONTROL_H

/* Service control is a first-class, reusable HermesXP capability. It never
   accepts a command line, executable path, arbitrary process ID, registry
   path, or service installation/configuration operation. */
enum {
    HERMESXP_SERVICE_STATUS = 1,
    HERMESXP_SERVICE_START = 2,
    HERMESXP_SERVICE_STOP = 3,
    HERMESXP_SERVICE_RESTART = 4,
};

typedef struct {
    unsigned int action;
    char name[81];
} HERMESXP_SERVICE_COMMAND;

static int hermesxp_service_match(const char *value, int size, const char *expected) {
    int n = 0;
    while (expected[n]) {
        if (n >= size || value[n] != expected[n]) return 0;
        ++n;
    }
    return n == size;
}

static int hermesxp_service_parse(const char *body, int length,
                                  HERMESXP_SERVICE_COMMAND *out) {
    int i, sep = -1, name_size, action_size;
    if (!body || !out || length < 16 || length > 120) return 0;
    /* Form body must be canonical: action={...}&name={exact SCM name}.
       No URL decoding, NUL bytes, percent-escapes or extra fields. */
    if (!(body[0]=='a' && body[1]=='c' && body[2]=='t' && body[3]=='i' &&
          body[4]=='o' && body[5]=='n' && body[6]=='=')) return 0;
    for (i=7; i<length; i++) {
        if (body[i]=='&') { sep=i; break; }
    }
    if (sep < 8 || sep + 6 > length) return 0;
    if (!(body[sep+1]=='n' && body[sep+2]=='a' && body[sep+3]=='m' &&
          body[sep+4]=='e' && body[sep+5]=='=')) return 0;
    action_size = sep - 7;
    if (hermesxp_service_match(body+7,action_size,"status"))
        out->action = HERMESXP_SERVICE_STATUS;
    else if (hermesxp_service_match(body+7,action_size,"start"))
        out->action = HERMESXP_SERVICE_START;
    else if (hermesxp_service_match(body+7,action_size,"stop"))
        out->action = HERMESXP_SERVICE_STOP;
    else if (hermesxp_service_match(body+7,action_size,"restart"))
        out->action = HERMESXP_SERVICE_RESTART;
    else return 0;
    name_size = length - sep - 6;
    if (name_size < 1 || name_size > 80) return 0;
    for (i=0; i<name_size; i++) {
        unsigned char c=(unsigned char)body[sep+6+i];
        if (!((c>='a'&&c<='z') || (c>='A'&&c<='Z') ||
              (c>='0'&&c<='9') || c=='_' || c=='-' || c=='.' ||
              c==' ' || c=='$' || c=='+')) return 0;
        if (c==' ' && (i==0 || i==name_size-1)) return 0;
        out->name[i]=(char)c;
    }
    out->name[name_size]=0;
    return 1;
}

#endif
