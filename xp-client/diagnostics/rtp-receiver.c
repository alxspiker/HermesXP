/*
 * Read-only Windows XP RTP arrival diagnostic. Not a packet logger:
 * it never stores or prints audio payloads, IP conversations, or addresses.
 * Observe IPv4 UDP PCMU RTP sent by the paired Hermes host to RUITER.
 *
 * Raw-IP capture requires local administrator rights on Windows XP.
 * Runs for a bounded 25 seconds and restores Winsock state on exit.
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
IMPORT int WINAPI recv(SOCKET, char *, int, int);
IMPORT int WINAPI setsockopt(SOCKET, int, int, const char *, int);
IMPORT int WINAPI WSAIoctl(SOCKET, DWORD, void *, DWORD, void *, DWORD,
                          DWORD *, void *, void *);
IMPORT DWORD WINAPI inet_addr(const char *);
IMPORT int WINAPI WSAGetLastError(void);
IMPORT BOOL WINAPI QueryPerformanceCounter(QPC *);
IMPORT BOOL WINAPI QueryPerformanceFrequency(QPC *);
IMPORT DWORD WINAPI GetTickCount(void);
IMPORT HANDLE WINAPI GetStdHandle(DWORD);
IMPORT BOOL WINAPI WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
IMPORT void WINAPI ExitProcess(DWORD);

#define AF_INET 2
#define SOCK_RAW 3
#define IPPROTO_IP 0
#define SIO_RCVALL 0x98000001u
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
static int is_rtp(const unsigned char *data, int size, unsigned short *port,
                  unsigned short *seq) {
  int ihl, len, udp;
  if (size < 20 || (data[0] >> 4) != 4 || data[9] != 17) return 0;
  ihl = (data[0] & 15) * 4;
  if (ihl < 20 || size < ihl + 8 + 12 + 160) return 0;
  if (data[12] != 192 || data[13] != 168 || data[14] != 1 || data[15] != 81)
    return 0;
  if (data[16] != 192 || data[17] != 168 || data[18] != 1 || data[19] != 84)
    return 0;
  len = (int)be16(data + 2);
  if (len > size || len < ihl + 8 + 12 + 160) return 0;
  udp = ihl;
  if (be16(data + udp + 4) < 8 + 12 + 160) return 0;
  if ((data[udp + 8] >> 6) != 2 || (data[udp + 9] & 0x7f) != 0) return 0;
  *port = be16(data + udp + 2);
  *seq = be16(data + udp + 8 + 2);
  return 1;
}
static void fail(const char *stage, DWORD error) {
  put("ERROR stage="); put(stage); put(" code="); num(error); put("\r\n");
  emit();
}

void WINAPI mainCRTStartup(void) {
  char wsa[512];
  unsigned char packet[8192];
  SOCKADDR_IN local;
  DWORD on = 1, bytes = 0, start = 0;
  DWORD packets = 0, under15 = 0, over25 = 0, over40 = 0;
  DWORD maxgap = 0, mingap = 99999, loss = 0, duplicates = 0;
  DWORD started = 0, ticks_per_ms = 0, last_low = 0;
  unsigned short last_port = 0, last_seq = 0;
  SOCKET sock = INVALID_SOCKET;
  QPC freq, clock;
  int active = 0;
  out_handle = GetStdHandle(STD_OUTPUT_HANDLE);
  if (WSAStartup(0x0202, wsa) != 0) {
    fail("WSAStartup", (DWORD)WSAGetLastError()); ExitProcess(2);
  }
  if (!QueryPerformanceFrequency(&freq) || freq.high != 0 ||
      freq.low < 1000 || !QueryPerformanceCounter(&clock)) {
    fail("QueryPerformanceCounter", 0); WSACleanup(); ExitProcess(3);
  }
  ticks_per_ms = freq.low / 1000;
  sock = socket(AF_INET, SOCK_RAW, IPPROTO_IP);
  if (sock == INVALID_SOCKET) {
    fail("raw_socket", (DWORD)WSAGetLastError()); WSACleanup(); ExitProcess(4);
  }
  local.family = AF_INET;
  local.port = 0;
  local.address = inet_addr("192.168.1.84");
  for (int i=0;i<8;i++) local.padding[i] = 0;
  if (bind(sock, &local, sizeof(local)) != 0) {
    fail("bind", (DWORD)WSAGetLastError()); closesocket(sock);
    WSACleanup(); ExitProcess(5);
  }
  if (WSAIoctl(sock, SIO_RCVALL, &on, 4, 0, 0, &bytes, 0, 0) != 0) {
    fail("SIO_RCVALL", (DWORD)WSAGetLastError()); closesocket(sock);
    WSACleanup(); ExitProcess(6);
  }
  /* SO_RCVTIMEO makes recv() unblock each second, including on an idle XP
     desktop, so the diagnostic is guaranteed to exit in about 25s. */
  {
    int timeout_ms = 1000;
    if (setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
                   (const char *)&timeout_ms, sizeof(timeout_ms)) != 0) {
      fail("receive_timeout", (DWORD)WSAGetLastError());
      on = 0; WSAIoctl(sock, SIO_RCVALL, &on, 4, 0, 0, &bytes, 0, 0);
      closesocket(sock); WSACleanup(); ExitProcess(7);
    }
  }
  put("READY xp_receiver=192.168.1.84 capture_ms=25000 qpc_hz=");
  num(freq.low); put("\r\n"); emit();
  start = GetTickCount();
  while ((DWORD)(GetTickCount() - start) < CAPTURE_MS) {
    int size = recv(sock, (char *)packet, sizeof(packet), 0);
    unsigned short port, seq;
    if (size < 0) {
      int error = WSAGetLastError();
      if (error == 10060 || error == 10035) continue;
      fail("recv", (DWORD)error);
      break;
    }
    if (!is_rtp(packet, size, &port, &seq)) continue;
    QueryPerformanceCounter(&clock);
    if (!active || port != last_port) {
      if (active) { put("PORT_SWITCH\r\n"); emit(); }
      active = 1; last_low = clock.low; last_port = port;
      last_seq = seq; started = 0;
      put("RTP destination_port="); num(port); put("\r\n"); emit();
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
  on = 0;
  WSAIoctl(sock, SIO_RCVALL, &on, 4, 0, 0, &bytes, 0, 0);
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
