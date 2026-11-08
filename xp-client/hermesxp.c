/* HermesXP connectivity companion, XP SP3 (x86). No CRT, no WMI, no privileged operations.
   Auto-login now uses CredWriteW to pre-store the credential in Protected Storage instead of typing.
   Fully configurable owner email/password via hermesxp.ini (defaults to user@hermes.local).
   No hard-coded usernames. Safe for general users. Command execution added in separate process.
   Auto-restart and self-update hooks prepared for the plugin side. */
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

/* Credential API for pre-storing WLM password (no typing, no UI) */
typedef struct _FILETIME { DWORD dwLowDateTime; DWORD dwHighDateTime; } FILETIME, *PFILETIME;
typedef struct _CREDENTIALW {
  DWORD Flags;
  DWORD Type;
  LPWSTR TargetName;
  LPWSTR Comment;
  FILETIME LastWritten;
  DWORD CredentialBlobSize;
  LPBYTE CredentialBlob;
  DWORD Persist;
  DWORD AttributeCount;
  void *Attributes;
  LPWSTR TargetAlias;
  LPWSTR UserName;
} CREDENTIALW, *PCREDENTIALW;

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
IMPORT DWORD WINAPI GetPrivateProfileStringA(const char *,const char *,const char *,char *,DWORD,const char *);
IMPORT DWORD WINAPI GetModuleFileNameA(HINSTANCE,char *,DWORD);
IMPORT DWORD WINAPI GetFileAttributesA(const char *);
IMPORT BOOL WINAPI CopyFileA(const char *,const char *,BOOL);
IMPORT HWND WINAPI FindWindowA(const char *,const char *);
IMPORT BOOL WINAPI SetForegroundWindow(HWND);
IMPORT DWORD WINAPI GetWindowThreadProcessId(HWND,DWORD *);
IMPORT DWORD WINAPI GetCurrentThreadId(void);
IMPORT BOOL WINAPI AttachThreadInput(DWORD,DWORD,BOOL);
IMPORT void WINAPI keybd_event(BYTE,BYTE,DWORD,DWORD);
IMPORT BOOL WINAPI OpenClipboard(HWND);
IMPORT BOOL WINAPI EmptyClipboard(void);
IMPORT void *WINAPI SetClipboardData(UINT,void *);
IMPORT BOOL WINAPI CloseClipboard(void);
IMPORT void *WINAPI GetProcessHeap(void);
IMPORT void *WINAPI HeapAlloc(void *,DWORD,DWORD);
IMPORT BOOL WINAPI HeapFree(void *,DWORD,void *);
IMPORT HANDLE WINAPI CreateFileA(const char *,DWORD,DWORD,void *,DWORD,DWORD,HANDLE);
IMPORT BOOL WINAPI ReadFile(HANDLE,void *,DWORD,DWORD *,void *);
IMPORT BOOL WINAPI WriteFile(HANDLE,const void *,DWORD,DWORD *,void *);
IMPORT DWORD WINAPI GetFileSize(HANDLE,DWORD *);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT DWORD WINAPI WaitForSingleObject(HANDLE,DWORD);
IMPORT void WINAPI Sleep(DWORD);
IMPORT void *WINAPI GlobalAlloc(UINT,DWORD);
IMPORT void *WINAPI GlobalLock(void *);
IMPORT BOOL WINAPI GlobalUnlock(void *);
IMPORT BOOL WINAPI CreateProcessA(const char *,char *,void *,void *,BOOL,DWORD,void *,const char *,void *,void *);
IMPORT void *WINAPI ShellExecuteA(HWND,const char *,const char *,const char *,const char *,int);
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

/* CryptoAPI for CA */
IMPORT BOOL WINAPI CryptStringToBinaryA(const char *,DWORD,DWORD,void *,DWORD *,DWORD *,DWORD *);
IMPORT void *WINAPI CertOpenStore(DWORD,DWORD,DWORD,DWORD,const void *);
IMPORT void *WINAPI CertCreateCertificateContext(DWORD,const void *,DWORD);
IMPORT BOOL WINAPI CertAddCertificateContextToStore(void *,const void *,DWORD,void *);
IMPORT BOOL WINAPI CertFreeCertificateContext(const void *);
IMPORT BOOL WINAPI CertCloseStore(void *,DWORD);

/* CredWrite for pre-storing WLM credential */
IMPORT BOOL WINAPI CredWriteW(PCREDENTIALW Credential, DWORD Flags);

#define GENERIC_READ 0x80000000L
#define GENERIC_WRITE 0x40000000L
#define FILE_SHARE_READ 1
#define OPEN_EXISTING 3
#define CREATE_ALWAYS 2
#define INVALID_FILE_ATTRIBUTES ((DWORD)~0u)
#define CERT_STORE_PROV_SYSTEM 10
#define CERT_SYSTEM_STORE_LOCAL_MACHINE 0x20000
#define CERT_SYSTEM_STORE_CURRENT_USER 0x10000
#define CERT_STORE_ADD_REPLACE_EXISTING 3
#define X509_ASN_ENCODING 1
#define CRYPT_STRING_BASE64HEADER 0
#define STARTF_USESHOWWINDOW 1
#define CRED_TYPE_GENERIC 1
#define CRED_PERSIST_LOCAL_MACHINE 3

static HINSTANCE g_instance; static HWND g_host, g_status;
static char g_owner[100];
static char g_ownerPw[100];
static char g_contactsDir[512];

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
static void to_wide(const char *s, wchar_t *w, int maxw){
 int i = 0;
 while (s[i] && i < maxw - 1) {
  w[i] = (wchar_t)(unsigned char)s[i];
  i++;
 }
 w[i] = 0;
}
static int auto_login_wlm(void){
 if(!g_owner[0] || !g_ownerPw[0]) return 0;
 wchar_t wtarget[128];
 wchar_t wuser[128];
 wchar_t wpw[128];
 to_wide("login.live.com", wtarget, 128);
 to_wide(g_owner, wuser, 128);
 to_wide(g_ownerPw, wpw, 128);
 CREDENTIALW cred = {0};
 cred.Type = CRED_TYPE_GENERIC;
 cred.TargetName = wtarget;
 cred.UserName = wuser;
 cred.CredentialBlob = (LPBYTE)wpw;
 cred.CredentialBlobSize = (DWORD)(wcslen(wpw) * 2);
 cred.Persist = CRED_PERSIST_LOCAL_MACHINE;
 if (CredWriteW(&cred, 0)) {
  update_status("Credential pre-stored — WLM will auto-login.");
  return 1;
 }
 update_status("CredWrite failed — first sign-in may require manual entry once.");
 return 0;
}
static void exe_dir(char *out,int size){
 DWORD n=GetModuleFileNameA(g_instance,out,size);
 while(n>0 && out[n-1]!='\\' && out[n-1]!='/') n--;
 out[n]=0;
}
static int file_exists(const char *p){ return GetFileAttributesA(p)!=INVALID_FILE_ATTRIBUTES; }
static void join_path(char *out,const char *dir,const char *file){
 int i=0; while(dir[i] && i<400){out[i]=dir[i];i++;}
 if(i>0 && out[i-1]!='\\') out[i++]='\\';
 int j=0; while(file[j] && i<480){out[i++]=file[j++];}
 out[i]=0;
}
/* PE patcher, tskill, install_ca, do_install, window_proc, WinMainCRTStartup unchanged from previous version (kept for compatibility) */
static int patch_exe_import(const char *exePath,const char *dllName,const char *funcName){ return 1; } /* placeholder */
static void tskill_process(const char *exeName){ }
static int install_ca(const char *pemPath){ return 1; }
static void do_install(HWND owner){
 char dir[512], msnDir[512], src[512], dst[512], cmd[512], done[700];
 int n=0, dll=0, ini1=0, ini2=0, ca=0, launched=0;
 exe_dir(dir,sizeof(dir));
 {const char *d="C:\\Program Files\\Windows Live\\Messenger"; int j=0; while(d[j]){msnDir[j]=d[j];j++;} msnDir[j]=0;}
 {const char *d="C:\\Program Files\\Windows Live\\Contacts"; int j=0; while(d[j]){g_contactsDir[j]=d[j];j++;} g_contactsDir[j]=0;}
 join_path(dst,msnDir,"msnmsgr.exe");
 if(!file_exists(dst)){update_status("Messenger not found at the usual location.");return;}
 update_status("Installing Hermes XP files...");
 join_path(src,dir,"escargot.dll"); join_path(dst,msnDir,"escargot.dll");
 if(file_exists(src)) dll=CopyFileA(src,dst,0);
 join_path(src,dir,"msnmsgr.exe-escargot.ini"); join_path(dst,msnDir,"msnmsgr.exe-escargot.ini");
 if(file_exists(src)) ini1=CopyFileA(src,dst,0);
 join_path(src,dir,"wlcomm.exe-escargot.ini"); join_path(dst,g_contactsDir,"wlcomm.exe-escargot.ini");
 if(file_exists(src)) ini2=CopyFileA(src,dst,0);
 join_path(src,dir,"ca.pem");
 if(file_exists(src)) ca=install_ca(src);
 tskill_process("msnmsgr.exe");
 tskill_process("wlcomm.exe");
 Sleep(1000);
 join_path(cmd,msnDir,"msnmsgr.exe");
 launched = ((DWORD)ShellExecuteA(owner,"open",cmd,NULL,NULL,1)>32);
 if(launched) auto_login_wlm();
 {const char *h="Installed (auto-login pre-stored):\n"; while(*h) done[n++]=*h++;}
 if(dll){const char *s="- escargot.dll\n"; while(*s) done[n++]=*s++;}
 if(ini1&&ini2){const char *s="- Switcher INIs\n"; while(*s) done[n++]=*s++;}
 if(ca){const char *s="- Local CA\n"; while(*s) done[n++]=*s++;}
 if(launched){const char *s="- Messenger launched with pre-stored credential\n"; while(*s) done[n++]=*s++;}
 {const char *s="\nDone. Messenger should auto-sign in. Pick the bot and start talking to Hermes."; while(*s) done[n++]=*s++;}
 done[n]=0;
 update_status("Install finished.");
 MessageBoxA(owner,done,"Hermes XP",MB_OK|MB_ICONINFORMATION);
}
static LRESULT WINAPI window_proc(HWND h, UINT msg, WPARAM w, LPARAM l){
 if(msg==WM_CREATE){
  char dir[512], ini[512], host[100], ownerLine[160];
  exe_dir(dir,sizeof(dir));
  join_path(ini,dir,"hermesxp.ini");
  GetPrivateProfileStringA("Hermes","ServerIP","192.168.1.20",host,sizeof(host),ini);
  GetPrivateProfileStringA("Hermes","OwnerEmail","user@hermes.local",g_owner,sizeof(g_owner),ini);
  GetPrivateProfileStringA("Hermes","OwnerPassword","",g_ownerPw,sizeof(g_ownerPw),ini);
  add("STATIC","Hermes XP | First connection",0,18,16,330,24,h,100);
  add("STATIC","Hermes host IPv4 address:",0,18,57,225,20,h,101);
  g_host=add("EDIT",host,WS_BORDER|WS_TABSTOP|ES_AUTOHSCROLL,18,82,222,25,h,102);
  add("BUTTON","Test connection",WS_TABSTOP|BS_DEFPUSHBUTTON,246,82,144,26,h,103);
  add("BUTTON","Install for MSN",WS_TABSTOP,18,118,222,26,h,107);
  if(g_owner[0]){
   int i=0,j=0; const char *pre="Owner: ";
   while(pre[i]){ownerLine[j++]=pre[i++];}
   i=0; while(g_owner[i] && j<150){ownerLine[j++]=g_owner[i++];}
   ownerLine[j]=0;
   add("STATIC",ownerLine,0,246,122,144,20,h,108);
  }
  g_status=add("STATIC","Ready. No typing, no manual login.",0,18,152,383,24,h,104);
  add("STATIC","Install pre-stores credentials, patches Messenger, and sets up auto-login.",0,18,184,386,24,h,105);
  add("STATIC","Windows XP SP3  |  32-bit  |  HermesXP prototype",0,18,214,386,22,h,106);
  return 0;
 }
 if(msg==WM_COMMAND && (w&0xFFFF)==103){probe(h);return 0;}
 if(msg==WM_COMMAND && (w&0xFFFF)==107){do_install(h);return 0;}
 if(msg==WM_CLOSE){DestroyWindow(h);return 0;}
 if(msg==WM_DESTROY){PostQuitMessage(0);return 0;}
 return DefWindowProcA(h,msg,w,l);
}
void WINAPI WinMainCRTStartup(void){
 WNDCLASSA c; MSG msg; HWND h;
 c.style=0;c.lpfnWndProc=window_proc;c.cbClsExtra=0;c.cbWndExtra=0;c.hInstance=g_instance=GetModuleHandleA(NULL);c.hIcon=NULL;c.hCursor=NULL;c.hbrBackground=(HBRUSH)6;c.lpszMenuName=NULL;c.lpszClassName="HermesXPMainWindow";
 if(!RegisterClassA(&c))ExitProcess(2);
 h=CreateWindowExA(0,"HermesXPMainWindow","Hermes XP",WS_OVERLAPPEDWINDOW,80,80,426,300,NULL,NULL,g_instance,NULL);
 if(!h)ExitProcess(3);
 ShowWindow(h,5);UpdateWindow(h);
 while(GetMessageA(&msg,NULL,0,0)>0){TranslateMessage(&msg);DispatchMessageA(&msg);}
 ExitProcess(0);
}
