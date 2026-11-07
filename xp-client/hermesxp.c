/* HermesXP connectivity companion, XP SP3 (x86). No CRT, no WMI, no privileged operations. */
typedef void *HANDLE; typedef void *HINSTANCE; typedef void *HWND; typedef void *HICON;
typedef void *HCURSOR; typedef void *HBRUSH; typedef unsigned long DWORD; typedef unsigned int UINT;
typedef long LONG; typedef unsigned long ULONG; typedef unsigned long WPARAM; typedef long LPARAM;
typedef long LRESULT; typedef int BOOL; typedef unsigned short WORD; typedef unsigned char BYTE;
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
#define NULL ((void*)0)
#define WS_OVERLAPPEDWINDOW 0x00CF0000L
#define WS_VISIBLE 0x10000000L
#define WS_CHILD 0x40000000L
#define WS_BORDER 0x00800000L
#define WS_TABSTOP 0x00010000L
#define ES_AUTOHSCROLL 0x0080L
#define BS_DEFPUSHBUTTON 0x00000001L
#define CW_USEDEFAULT ((int)0x80000000)
#define WM_CREATE 1
#define WM_DESTROY 2
#define WM_COMMAND 0x111
#define WM_CLOSE 16
#define MB_OK 0
#define MB_ICONINFORMATION 0x40
#define MB_ICONWARNING 0x30
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 0xFFFF
#define SO_SNDTIMEO 0x1005
#define SO_RCVTIMEO 0x1006
#define INVALID_SOCKET ((unsigned int)~0u)

typedef struct { long x,y; } POINT;
typedef struct { HWND hwnd; UINT message; WPARAM wParam; LPARAM lParam; DWORD time; POINT pt; } MSG;
typedef LRESULT (WINAPI *WNDPROC)(HWND,UINT,WPARAM,LPARAM);
typedef struct { UINT style; WNDPROC lpfnWndProc; int cbClsExtra,cbWndExtra; HINSTANCE hInstance; HICON hIcon; HCURSOR hCursor; HBRUSH hbrBackground; const char *lpszMenuName,*lpszClassName; } WNDCLASSA;
typedef struct { short sin_family; unsigned short sin_port; unsigned long sin_addr; unsigned char sin_zero[8]; } SOCKADDR_IN;

IMPORT HINSTANCE WINAPI GetModuleHandleA(const char *);
IMPORT void WINAPI ExitProcess(UINT);
IMPORT BOOL WINAPI GetComputerNameA(char *, DWORD *);
IMPORT unsigned short WINAPI RegisterClassA(const WNDCLASSA *);
IMPORT HWND WINAPI CreateWindowExA(DWORD,const char *,const char *,DWORD,int,int,int,int,HWND,void *,HINSTANCE,void *);
IMPORT BOOL WINAPI ShowWindow(HWND,int);
IMPORT BOOL WINAPI UpdateWindow(HWND);
IMPORT LRESULT WINAPI DefWindowProcA(HWND,UINT,WPARAM,LPARAM);
IMPORT BOOL WINAPI GetMessageA(MSG *,HWND,UINT,UINT);
IMPORT BOOL WINAPI TranslateMessage(const MSG *);
IMPORT LRESULT WINAPI DispatchMessageA(const MSG *);
IMPORT void WINAPI PostQuitMessage(int);
IMPORT BOOL WINAPI DestroyWindow(HWND);
IMPORT int WINAPI MessageBoxA(HWND,const char *,const char *,UINT);
IMPORT int WINAPI GetWindowTextA(HWND,char *,int);
IMPORT BOOL WINAPI SetWindowTextA(HWND,const char *);
IMPORT int WINAPI WSAStartup(WORD,void *);
IMPORT int WINAPI WSACleanup(void);
IMPORT unsigned int WINAPI socket(int,int,int);
IMPORT int WINAPI connect(unsigned int,const void *,int);
IMPORT int WINAPI send(unsigned int,const char *,int,int);
IMPORT int WINAPI recv(unsigned int,char *,int,int);
IMPORT int WINAPI closesocket(unsigned int);
IMPORT unsigned long WINAPI inet_addr(const char *);
IMPORT unsigned short WINAPI htons(unsigned short);
IMPORT int WINAPI setsockopt(unsigned int,int,int,const char *,int);
IMPORT int WINAPI WSAGetLastError(void);

static HINSTANCE g_instance; static HWND g_host, g_status;
static int strlen0(const char *s){int n=0;while(s[n])n++;return n;}
static void update_status(const char *s){ SetWindowTextA(g_status,s); }
static HWND add(const char *kind,const char *text,DWORD style,int x,int y,int w,int h,HWND parent,int id){
 return CreateWindowExA(0,kind,text,WS_CHILD|WS_VISIBLE|style,x,y,w,h,parent,(void*)id,g_instance,NULL);
}
static void probe(HWND owner){
 char host[100], response[96], machine[80], request[180]; DWORD n=sizeof(machine);
 unsigned char wsadata[512]; unsigned int sock; SOCKADDR_IN address; int count;
 GetWindowTextA(g_host,host,sizeof(host));
 if(!host[0]) {update_status("Enter the Hermes host IPv4 address.");return;}
 if(WSAStartup(0x0202,wsadata)!=0) {update_status("Winsock initialization failed.");return;}
 sock=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(sock==INVALID_SOCKET){update_status("Could not create socket.");WSACleanup();return;}
 address.sin_family=AF_INET;address.sin_port=htons(18765);
 address.sin_addr=inet_addr(host);
 for(int i=0;i<8;i++) address.sin_zero[i]=0;
 if(address.sin_addr==0xFFFFFFFFu){update_status("Use an IPv4 address, e.g. 192.168.1.20.");closesocket(sock);WSACleanup();return;}
 update_status("Connecting to Hermes on port 18765...");
 {int timeout_ms=4000;setsockopt(sock,SOL_SOCKET,SO_SNDTIMEO,(const char*)&timeout_ms,sizeof(timeout_ms));setsockopt(sock,SOL_SOCKET,SO_RCVTIMEO,(const char*)&timeout_ms,sizeof(timeout_ms));}
 if(connect(sock,&address,sizeof(address))!=0){update_status("Connection failed. Check IP and firewall.");closesocket(sock);WSACleanup();return;}
 if(!GetComputerNameA(machine,&n)) {machine[0]='X';machine[1]='P';machine[2]=0;}
 /* Endpoint is a read-only, unauthenticated connectivity probe. Do not send credentials. */
 int off=0; const char *head="HXP1 "; for(int i=0;head[i] && off<150;i++)request[off++]=head[i];
 for(int i=0;machine[i] && off<150;i++) {char c=machine[i]; if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-')request[off++]=c;}
 request[off++]='\r';request[off++]='\n';request[off]=0;
 if(send(sock,request,off,0)!=off){update_status("Probe send failed.");closesocket(sock);WSACleanup();return;}
 count=recv(sock,response,sizeof(response)-1,0);
 if(count<=0){update_status("No response from Hermes.");closesocket(sock);WSACleanup();return;}
 response[count]=0;
 closesocket(sock);WSACleanup();
 if(count>=7 && response[0]=='H' && response[1]=='X' && response[2]=='P' && response[3]=='1' && response[4]==' ' && response[5]=='O' && response[6]=='K'){
  update_status("Hermes host reached! Probe OK. Not yet paired.");
  MessageBoxA(owner,"Hermes host responded. Connection verified!\n\nThis is a connectivity test, not authenticated pairing.","Hermes XP",MB_OK|MB_ICONINFORMATION);
 } else update_status("Unexpected server response.");
}
static LRESULT WINAPI window_proc(HWND h, UINT msg, WPARAM w, LPARAM l){
 if(msg==WM_CREATE){
  add("STATIC","Hermes XP | First connection",0,18,16,330,24,h,100);
  add("STATIC","Hermes host IPv4 address:",0,18,57,225,20,h,101);
  g_host=add("EDIT","192.168.1.20",WS_BORDER|WS_TABSTOP|ES_AUTOHSCROLL,18,82,222,25,h,102);
  add("BUTTON","Test connection",WS_TABSTOP|BS_DEFPUSHBUTTON,246,82,144,26,h,103);
  g_status=add("STATIC","Ready. Test only: no remote commands enabled.",0,18,130,383,24,h,104);
  add("STATIC","MSN login is configured separately on the Hermes host.",0,18,162,386,24,h,105);
  add("STATIC","Windows XP SP3  |  32-bit  |  HermesXP prototype",0,18,202,386,22,h,106);
  return 0;
 }
 if(msg==WM_COMMAND && (w&0xFFFF)==103){probe(h);return 0;}
 if(msg==WM_CLOSE){DestroyWindow(h);return 0;}
 if(msg==WM_DESTROY){PostQuitMessage(0);return 0;}
 return DefWindowProcA(h,msg,w,l);
}
void WINAPI WinMainCRTStartup(void){
 WNDCLASSA c; MSG msg; HWND h;
 c.style=0;c.lpfnWndProc=window_proc;c.cbClsExtra=0;c.cbWndExtra=0;c.hInstance=g_instance=GetModuleHandleA(NULL);c.hIcon=NULL;c.hCursor=NULL;c.hbrBackground=(HBRUSH)6;c.lpszMenuName=NULL;c.lpszClassName="HermesXPMainWindow";
 if(!RegisterClassA(&c))ExitProcess(2);
 h=CreateWindowExA(0,"HermesXPMainWindow","Hermes XP - Ruiter Companion",WS_OVERLAPPEDWINDOW,80,80,426,280,NULL,NULL,g_instance,NULL);
 if(!h)ExitProcess(3);
 ShowWindow(h,5);UpdateWindow(h);
 while(GetMessageA(&msg,NULL,0,0)>0){TranslateMessage(&msg);DispatchMessageA(&msg);}
 ExitProcess(0);
}
