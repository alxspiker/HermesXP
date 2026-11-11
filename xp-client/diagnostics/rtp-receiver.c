/*
 * Read-only Windows XP RTP arrival diagnostic. Not a packet logger:
 * it never stores or prints audio payloads, IP conversations, or addresses.
 * Receive a controlled, silent IPv4 UDP PCMU RTP test stream from Hermes.
 *
 * Uses ordinary UDP sockets (not raw socket packet capture) and listens on
 * port 45678 for 25 seconds. It cannot inspect Messenger's audio buffers.
 * It measures the network/IP/Winsock receive timing on the same XP host.
 * The output is aggregate RTP header/arrival counters only.
 */
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
typedef unsigned int DWORD;
typedef unsigned int SOCKET;
typedef unsigned short WORD;
typedef int BOOL;
typedef void *HANDLE;
typedef struct { DWORD low; int high; } QPC;
typedef struct {
  short family; unsigned short port; unsigned int address; char padding[8];
} SOCKADDR_IN;

IMPORT int WINAPI WSAStartup(WORD, void *);
IMPORT int WINAPI WSACleanup(void);
IMPORT SOCKET WINAPI socket(int, int, int);
IMPORT int WINAPI bind(SOCKET, const void *, int);
IMPORT int WINAPI closesocket(SOCKET);
IMPORT int WINAPI recvfrom(SOCKET, char *, int, int, void *, int *);
IMPORT int WINAPI setsockopt(SOCKET, int, int, const char *, int);
IMPORT DWORD WINAPI inet_addr(const char *);
IMPORT unsigned short WINAPI htons(unsigned short);
IMPORT int WINAPI WSAGetLastError(void);
IMPORT BOOL WINAPI QueryPerformanceCounter(QPC *);
IMPORT BOOL WINAPI QueryPerformanceFrequency(QPC *);
IMPORT DWORD WINAPI GetTickCount(void);
IMPORT HANDLE WINAPI GetStdHandle(DWORD);
IMPORT BOOL WINAPI WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
IMPORT char * WINAPI GetCommandLineA(void);
IMPORT void WINAPI ExitProcess(DWORD);

#define AF_INET 2
#define SOCK_DGRAM 2
#define IPPROTO_UDP 17
#define RECEIVE_PORT 45678
#define SO_RCVTIMEO 0x1006
#define SOL_SOCKET 0xFFFF
#define INVALID_SOCKET 0xFFFFFFFFu
#define STD_OUTPUT_HANDLE 0xFFFFFFF5u
#define CAPTURE_MS 25000u

static HANDLE out_handle;
static char output[350];
static DWORD used;

static void emit(void) {
  DWORD written = 0;
  if (used) WriteFile(out_handle, output, used, &written, (void *)0);
  used = 0;
}
static void put(const char *s) {
  while (*s && used < sizeof(output) - 3) output[used++] = *s++;
}
static void num(DWORD n) {
  char digits[12]; int i = 0;
  do { digits[i++] = (char)('0' + n % 10); n /= 10; } while (n && i < 11);
  while (i && used < sizeof(output) - 3) output[used++] = digits[--i];
}
static void key(const char *s, DWORD value) {
  put(s); num(value); put(" ");
}
static unsigned short be16(const unsigned char *p) {
  return (unsigned short)(((unsigned int)p[0] << 8) | p[1]);
}
static int is_rtp(const unsigned char *data, int size, unsigned short *seq) {
  /* 12-byte RTP header + exactly 160 bytes G.711 PCMU per 20ms frame. */
  if (size != 172 || (data[0] >> 6) != 2 || (data[1] & 0x7f) != 0 ||
      (data[0] & 0x3f) != 0) return 0;
  *seq = be16(data + 2);
  return 1;
}
static void fail(const char *stage, DWORD error) {
  put("ERROR stage="); put(stage); put(" code="); num(error); put("\r\n");
  emit();
}

void WINAPI mainCRTStartup(void) {
  char wsa[512];
  unsigned char packet[8192];
  SOCKADDR_IN local, sender;
  DWORD start = 0;
  DWORD packets = 0, under15 = 0, over25 = 0, over40 = 0;
  DWORD maxgap = 0, mingap = 99999, loss = 0, duplicates = 0;
  DWORD started = 0, ticks_per_ms = 0, last_low = 0;
  unsigned short last_seq = 0;
  char sender_ip[16];
  const char *arg = GetCommandLineA();
  int ip_len = 0, dots = 0;
  SOCKET sock = INVALID_SOCKET;
  QPC freq, clock;
  int active = 0;
  out_handle = GetStdHandle(STD_OUTPUT_HANDLE);
  /* An explicit host IP is mandatory. No developer LAN address is built in.
     Win32 command-line parsing is sufficient for one unquoted IPv4 argument. */
  if (*arg == '"') {
    arg++;
    while (*arg && *arg != '"') arg++;
    if (*arg) arg++;
  } else {
    while (*arg && *arg != ' ' && *arg != '\t') arg++;
  }
  while (*arg == ' ' || *arg == '\t') arg++;
  while ((*arg >= '0' && *arg <= '9') || *arg == '.') {
    if (ip_len >= 15) break;
    if (*arg == '.') dots++;
    sender_ip[ip_len++] = *arg++;
  }
  sender_ip[ip_len] = 0;
  if (!ip_len || dots != 3 || (*arg != 0 && *arg != ' ' && *arg != '\t') ||
      inet_addr(sender_ip) == 0xFFFFFFFFu) {
    put("Usage: rtp-receiver.exe <sender-ipv4>\r\n");
    emit();
    ExitProcess(1);
  }
  if (WSAStartup(0x0202, wsa) != 0) {
    fail("WSAStartup", (DWORD)WSAGetLastError()); ExitProcess(2);
  }
  if (!QueryPerformanceFrequency(&freq) || freq.high != 0 ||
      freq.low < 1000 || !QueryPerformanceCounter(&clock)) {
    fail("QueryPerformanceCounter", 0); WSACleanup(); ExitProcess(3);
  }
  ticks_per_ms = freq.low / 1000;
  sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  if (sock == INVALID_SOCKET) {
    fail("udp_socket", (DWORD)WSAGetLastError()); WSACleanup(); ExitProcess(4);
  }
  local.family = AF_INET;
  local.port = htons(RECEIVE_PORT);
  /* Bind whichever Windows XP interface is active (Wi-Fi or Ethernet).
     The control-plane pairing and PCMU stream use the current DHCP lease. */
  local.address = 0;
  for (int i=0;i<8;i++) local.padding[i] = 0;
  if (bind(sock, &local, sizeof(local)) != 0) {
    fail("bind", (DWORD)WSAGetLastError()); closesocket(sock);
    WSACleanup(); ExitProcess(5);
  }
  /* SO_RCVTIMEO makes recv() unblock each second, including on an idle XP
     desktop, so the diagnostic is guaranteed to exit in about 25s. */
  {
    int timeout_ms = 1000;
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                   (const char *)&timeout_ms, sizeof(timeout_ms)) != 0) {
      fail("receive_timeout", (DWORD)WSAGetLastError());
      closesocket(sock); WSACleanup(); ExitProcess(7);
    }
  }
  put("READY xp_udp_receiver_port=45678 capture_ms=25000 qpc_hz=");
  num(freq.low); put("\r\n"); emit();
  start = GetTickCount();
  while ((DWORD)(GetTickCount() - start) < CAPTURE_MS) {
    int senderlen = sizeof(sender);
    int size = recvfrom(sock, (char *)packet, sizeof(packet), 0,
                        &sender, &senderlen);
    unsigned short seq;
    if (size < 0) {
      int error = WSAGetLastError();
      if (error == 10060 || error == 10035) continue;
      fail("recv", (DWORD)error);
      break;
    }
    if (sender.address != inet_addr(sender_ip) ||
        !is_rtp(packet, size, &seq)) continue;
    QueryPerformanceCounter(&clock);
    if (!active) {
      active = 1; last_low = clock.low;
      last_seq = seq; started = 0;
      put("RTP received\r\n"); emit();
    } else {
      DWORD gap = (clock.low - last_low) / ticks_per_ms;
      unsigned short step = (unsigned short)(seq - last_seq);
      if (step == 0) duplicates++;
      else if (step < 32768) {
        if (step > 1) loss += (DWORD)step - 1;
        last_seq = seq;
      }
      if (gap < 15) under15++;
      if (gap > 25) over25++;
      if (gap > 40) over40++;
      if (gap > maxgap) maxgap = gap;
      if (gap < mingap) mingap = gap;
      last_low = clock.low;
      started++;
    }
    packets++;
  }
  closesocket(sock);
  WSACleanup();
  put("SUMMARY ");
  key("packets=", packets);
  key("missing_sequence=", loss);
  key("duplicates=", duplicates);
  key("spacing_under15=", under15);
  key("spacing_over25=", over25);
  key("spacing_over40=", over40);
  key("min_ms=", started ? mingap : 0);
  key("max_ms=", maxgap);
  put("\r\n");
  emit();
  ExitProcess(0);
}
