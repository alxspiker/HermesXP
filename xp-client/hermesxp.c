/* HermesXP connectivity companion, XP SP3 (x86). No CRT, no WMI.
   Fully automatic setup: the installer stores the owner credential in the
   Windows Credential Manager (CredWriteW) and sets the registry
   DefaultMemberName, so WLM auto-signs-in on launch. No form typing, no
   user-entered password. Install also fixes the default gateway, the hosts
   file, the Switcher INIs and the local CA, all without manual steps. */
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
#define ES_PASSWORD 0x0020L
#define BS_DEFPUSHBUTTON 0x00000001L
#define CW_USEDEFAULT ((int)0x80000000)
#define WM_CREATE 1
#define WM_DESTROY 2
#define WM_COMMAND 0x111
#define WM_TIMER 0x113
#define WM_CLOSE 16
#define WM_HERMESXP_VOICE_INVITE 0x8001
#define MB_OK 0
#define MB_ICONINFORMATION 0x40
#define MB_ICONWARNING 0x30
#define MB_YESNO 0x00000004
#define IDYES 6
#define KEYEVENTF_KEYUP 0x0002
#define MOUSEEVENTF_LEFTDOWN 0x0002
#define MOUSEEVENTF_LEFTUP 0x0004
#define MOUSEEVENTF_RIGHTDOWN 0x0008
#define MOUSEEVENTF_RIGHTUP 0x0010
#define VK_SHIFT 0x10
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define SOL_SOCKET 0xFFFF
#define SO_REUSEADDR 0x0004
#define SO_SNDTIMEO 0x1005
#define SO_RCVTIMEO 0x1006
#define INVALID_SOCKET ((unsigned int)~0u)

typedef struct { long x,y; } POINT;
typedef struct { HWND hwnd; UINT message; WPARAM wParam; LPARAM lParam; DWORD time; POINT pt; } MSG;
typedef LRESULT (WINAPI *WNDPROC)(HWND,UINT,WPARAM,LPARAM);
typedef struct { UINT style; WNDPROC lpfnWndProc; int cbClsExtra,cbWndExtra; HINSTANCE hInstance; HICON hIcon; HCURSOR hCursor; HBRUSH hbrBackground; const char *lpszMenuName,*lpszClassName; } WNDCLASSA;
typedef struct { short sin_family; unsigned short sin_port; unsigned long sin_addr; unsigned char sin_zero[8]; } SOCKADDR_IN;
#include "remote_control.h"
/* Credential Manager (advapi32). CREDENTIALW is 48 bytes on 32-bit. */
typedef struct { DWORD Flags; DWORD Type; unsigned short *TargetName; unsigned short *Comment; DWORD LastWrittenLow; DWORD LastWrittenHigh; DWORD CredentialBlobSize; unsigned char *CredentialBlob; DWORD Persist; DWORD AttributeCount; void *Attributes; unsigned short *TargetAlias; unsigned short *UserName; } CREDENTIALW;
typedef struct { DWORD cbData; unsigned char *pbData; } CRYPT_HASH_BLOB;
typedef struct _IP_ADDR_STRING { struct _IP_ADDR_STRING *Next; char IpAddress[16]; char IpMask[16]; DWORD Context; } IP_ADDR_STRING;
typedef struct _IP_ADAPTER_INFO { struct _IP_ADAPTER_INFO *Next; DWORD ComboIndex; char AdapterName[260]; char Description[132]; UINT AddressLength; BYTE Address[8]; DWORD Index; UINT Type; UINT DhcpEnabled; void *CurrentIpAddress; IP_ADDR_STRING IpAddressList; IP_ADDR_STRING GatewayList; IP_ADDR_STRING DhcpServer; int HaveWins; IP_ADDR_STRING PrimaryWinsServer; IP_ADDR_STRING SecondaryWinsServer; long LeaseObtained; long LeaseExpires; } IP_ADAPTER_INFO;
typedef struct { DWORD biSize; LONG biWidth; LONG biHeight; WORD biPlanes; WORD biBitCount; DWORD biCompression; DWORD biSizeImage; LONG biXPelsPerMeter; LONG biYPelsPerMeter; DWORD biClrUsed; DWORD biClrImportant; } BITMAPINFOHEADER;

IMPORT HINSTANCE WINAPI GetModuleHandleA(const char *);
IMPORT HINSTANCE WINAPI LoadLibraryA(const char *);
IMPORT void *WINAPI GetProcAddress(HINSTANCE,const char *);
IMPORT BOOL WINAPI FreeLibrary(HINSTANCE);
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
IMPORT BOOL WINAPI PostMessageA(HWND,UINT,WPARAM,LPARAM);
IMPORT int WINAPI MessageBoxA(HWND,const char *,const char *,UINT);
IMPORT int WINAPI GetWindowTextA(HWND,char *,int);
IMPORT UINT WINAPI SetTimer(HWND,UINT,UINT,void *);
IMPORT BOOL WINAPI KillTimer(HWND,UINT);
IMPORT BOOL WINAPI SetWindowTextA(HWND,const char *);
IMPORT LRESULT WINAPI SendMessageA(HWND,UINT,WPARAM,LPARAM);
IMPORT BOOL WINAPI SetCursorPos(int,int);
IMPORT void WINAPI mouse_event(DWORD,DWORD,DWORD,DWORD,void *);
IMPORT short WINAPI VkKeyScanA(char);
IMPORT void WINAPI keybd_event(BYTE,BYTE,DWORD,void *);
IMPORT HWND WINAPI GetForegroundWindow(void);
IMPORT void *WINAPI GetDC(HWND);
IMPORT int WINAPI ReleaseDC(HWND,void *);
IMPORT int WINAPI GetSystemMetrics(int);
/* GDI (gdi32) for the screenshot capture. */
IMPORT void *WINAPI CreateCompatibleDC(void *);
IMPORT void *WINAPI CreateCompatibleBitmap(void *,int,int);
IMPORT void *WINAPI SelectObject(void *,void *);
IMPORT BOOL WINAPI BitBlt(void *,int,int,int,int,void *,int,int,DWORD);
IMPORT int WINAPI GetDIBits(void *,void *,UINT,UINT,void *,void *,UINT);
IMPORT BOOL WINAPI DeleteDC(void *);
IMPORT BOOL WINAPI DeleteObject(void *);
IMPORT DWORD WINAPI GetPrivateProfileStringA(const char *,const char *,const char *,char *,DWORD,const char *);
IMPORT BOOL WINAPI WritePrivateProfileStringA(const char *,const char *,const char *,const char *);
IMPORT DWORD WINAPI GetModuleFileNameA(HINSTANCE,char *,DWORD);
IMPORT DWORD WINAPI GetFileAttributesA(const char *);
IMPORT BOOL WINAPI CopyFileA(const char *,const char *,BOOL);
IMPORT BOOL WINAPI DeleteFileA(const char *);
IMPORT BOOL WINAPI MoveFileExA(const char *,const char *,DWORD);
IMPORT void *WINAPI GetProcessHeap(void);
IMPORT void *WINAPI HeapAlloc(void *,DWORD,DWORD);
IMPORT BOOL WINAPI HeapFree(void *,DWORD,void *);
IMPORT HANDLE WINAPI CreateFileA(const char *,DWORD,DWORD,void *,DWORD,DWORD,HANDLE);
IMPORT BOOL WINAPI ReadFile(HANDLE,void *,DWORD,DWORD *,void *);
IMPORT BOOL WINAPI WriteFile(HANDLE,const void *,DWORD,DWORD *,void *);
IMPORT DWORD WINAPI GetFileSize(HANDLE,DWORD *);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT DWORD WINAPI GetLastError(void);
IMPORT DWORD WINAPI WaitForSingleObject(HANDLE,DWORD);
IMPORT void WINAPI Sleep(DWORD);
IMPORT BOOL WINAPI CreateProcessA(const char *,char *,void *,void *,BOOL,DWORD,void *,const char *,void *,void *);
IMPORT BOOL WINAPI GetExitCodeProcess(HANDLE,DWORD *);
IMPORT BOOL WINAPI TerminateProcess(HANDLE,UINT);
IMPORT HANDLE WINAPI CreateEventA(void *,BOOL,BOOL,const char *);
IMPORT HANDLE WINAPI OpenEventA(DWORD,BOOL,const char *);
IMPORT BOOL WINAPI SetEvent(HANDLE);
IMPORT HANDLE WINAPI CreateMutexA(void *,BOOL,const char *);
IMPORT UINT WINAPI GetWindowsDirectoryA(char *,UINT);
IMPORT HANDLE WINAPI CreateThread(void *,DWORD,void *,void *,DWORD,DWORD *);
IMPORT BOOL WINAPI CreateDirectoryA(const char *,void *);
IMPORT const char *WINAPI GetCommandLineA(void);
IMPORT void *WINAPI ShellExecuteA(HWND,const char *,const char *,const char *,const char *,int);
IMPORT int WINAPI WSAStartup(WORD,void *);
IMPORT int WINAPI WSACleanup(void);
IMPORT unsigned int WINAPI socket(int,int,int);
IMPORT int WINAPI connect(unsigned int,const void *,int);
IMPORT int WINAPI bind(unsigned int,const void *,int);
IMPORT int WINAPI listen(unsigned int,int);
IMPORT unsigned int WINAPI accept(unsigned int,void *,int *);
IMPORT int WINAPI send(unsigned int,const char *,int,int);
IMPORT int WINAPI recv(unsigned int,char *,int,int);
IMPORT int WINAPI closesocket(unsigned int);
IMPORT unsigned long WINAPI inet_addr(const char *);
IMPORT unsigned short WINAPI htons(unsigned short);
IMPORT int WINAPI setsockopt(unsigned int,int,int,const char *,int);
IMPORT int WINAPI WSAGetLastError(void);

/* CryptoAPI (crypt32) for installing the local CA into Trusted Root. */
IMPORT BOOL WINAPI CryptStringToBinaryA(const char *,DWORD,DWORD,void *,DWORD *,DWORD *,DWORD *);
IMPORT void *WINAPI CertOpenStore(DWORD,DWORD,DWORD,DWORD,const void *);
IMPORT void *WINAPI CertCreateCertificateContext(DWORD,const void *,DWORD);
IMPORT BOOL WINAPI CertAddCertificateContextToStore(void *,const void *,DWORD,void *);
IMPORT BOOL WINAPI CertFreeCertificateContext(const void *);
IMPORT BOOL WINAPI CertCloseStore(void *,DWORD);
IMPORT void *WINAPI CertFindCertificateInStore(void *,DWORD,DWORD,DWORD,const void *,void *);
IMPORT BOOL WINAPI CertGetCertificateContextProperty(void *,DWORD,void *,DWORD *);

/* Credential Manager, registry, CryptoAPI RNG (advapi32). */
IMPORT BOOL WINAPI CredWriteW(void *,DWORD);
IMPORT LONG WINAPI RegCreateKeyExA(void *,const char *,DWORD,char *,DWORD,DWORD,void *,void **,DWORD *);
IMPORT LONG WINAPI RegSetValueExA(void *,const char *,DWORD,DWORD,const unsigned char *,DWORD);
IMPORT LONG WINAPI RegCloseKey(void *);
IMPORT BOOL WINAPI CryptAcquireContextA(void **,const char *,const char *,DWORD,DWORD);
IMPORT BOOL WINAPI CryptGenRandom(void *,DWORD,unsigned char *);
IMPORT BOOL WINAPI CryptReleaseContext(void *,DWORD);
IMPORT BOOL WINAPI CryptCreateHash(void *,DWORD,void *,DWORD,void **);
IMPORT BOOL WINAPI CryptHashData(void *,const unsigned char *,DWORD,DWORD);
IMPORT BOOL WINAPI CryptGetHashParam(void *,DWORD,unsigned char *,DWORD *,DWORD);
IMPORT BOOL WINAPI CryptDestroyHash(void *);

/* Adapter info (iphlpapi) for the default-gateway check. */
IMPORT DWORD WINAPI GetAdaptersInfo(void *,DWORD *);

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
#define CERT_HASH_PROP_ID 3
#define CERT_FIND_SHA1_HASH 0x00010000
#define REG_SZ 1
#define KEY_SET_VALUE 0x0002
#define CRED_TYPE_GENERIC 1
#define CRED_PERSIST_LOCAL_MACHINE 2
#define PROV_RSA_FULL 1
#define CRYPT_VERIFYCONTEXT 0xF0000000
#define STARTF_USESHOWWINDOW 1
#define CREATE_NO_WINDOW 0x08000000
#define HKEY_CURRENT_USER ((void*)0x80000001)
#define SM_CXSCREEN 0
#define SM_CYSCREEN 1
#define SRCCOPY 0x00CC0020
#define DIB_RGB_COLORS 0

static HINSTANCE g_instance; static HWND g_host, g_status, g_network_status, g_main_window;
static int g_update_activation;
static char g_remote_token[65], g_remote_allowed_ip[16];
static volatile LONG g_voice_cancel=0;
static int strlen0(const char *s){int n=0;while(s[n])n++;return n;}
static void append_number(char *out,int *pos,unsigned int value){
 char rev[10];int n=0;
 do {rev[n++]=(char)('0'+value%10);value/=10;} while(value && n<10);
 while(n>0)out[(*pos)++]=rev[--n];
}
static void update_status(const char *s){ SetWindowTextA(g_status,s); }
static HWND add(const char *kind,const char *text,DWORD style,int x,int y,int w,int h,HWND parent,int id){
 return CreateWindowExA(0,kind,text,WS_CHILD|WS_VISIBLE|style,x,y,w,h,parent,(void*)id,g_instance,NULL);
}
/* Read an assigned IPv4 address from XP. This is connection status only:
   no WLAN scanning, password storage, or network configuration of any kind. */
static void refresh_network_status(void){
 DWORD size=0; void *buf=NULL;
 const char *ip=NULL; char line[110]; int pos=0,i;
 const char *prefix="Network: IPv4 ";
 if(!g_network_status) return;
 GetAdaptersInfo(NULL,&size);
 if(size>=sizeof(IP_ADAPTER_INFO) && size<=65536){
  buf=HeapAlloc(GetProcessHeap(),0,size);
  if(buf){
   if(GetAdaptersInfo(buf,&size)==0){
    IP_ADAPTER_INFO *adapter=(IP_ADAPTER_INFO*)buf;
    while(adapter){
     const char *addr=adapter->IpAddressList.IpAddress;
     if(addr[0] && !(addr[0]=='0' && addr[1]=='.') &&
        !(addr[0]=='1' && addr[1]=='2' && addr[2]=='7' && addr[3]=='.') &&
        !(addr[0]=='1' && addr[1]=='6' && addr[2]=='9' && addr[3]=='.')){
      ip=addr;break;
     }
     adapter=adapter->Next;
    }
    if(ip){
     for(i=0;prefix[i] && pos<90;i++)line[pos++]=prefix[i];
     for(i=0;ip[i] && pos<105;i++)line[pos++]=ip[i];
     line[pos]=0;SetWindowTextA(g_network_status,line);
    }
   }
   HeapFree(GetProcessHeap(),0,buf);
  }
 }
 if(!ip) SetWindowTextA(g_network_status,"Network: no assigned IPv4 address");
}
static void open_windows_network_connections(HWND owner){
 /* XP's built-in Network Connections control-panel applet. */
 if((DWORD)ShellExecuteA(owner,"open","control.exe","ncpa.cpl",NULL,1)<=32){
  update_status("Could not open Network Connections. Use Control Panel instead.");
 }
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
static char g_owner[100];
static char g_ownerPw[100];
static char g_contactsDir[512];
static char g_serverIp[100];

/* --- XP-side installer: puts the connection files in place so WLM can use
   the local server, and patches both Messenger exes to import escargot.dll
   at startup so the Switcher loads with no manual steps. Reads hermesxp.ini
   from this exe's own folder (written by the plugin's package builder):
   [Hermes] ServerIP, OwnerEmail, OwnerPassword.
   OwnerEmail defaults to user@hermes.local (the generic account for every
   HermesXP user, never a personal address). OwnerPassword must be at most
   16 chars (WLM 2009 truncates longer passwords); if empty, the installer
   generates a random 16-char one and writes it back to the ini. --- */
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
static int str_eq(const char *a,const char *b){ while(*a && *b){ if(*a!=*b) return 0; a++; b++; } return *a==*b; }
static const char *str_find(const char *hay,const char *needle){
 int nl=strlen0(needle); if(!nl) return hay;
 for(int i=0;hay[i];i++){ int j=0; while(j<nl && hay[i+j]==needle[j]) j++; if(j==nl) return hay+i; }
 return NULL;
}
/* Copy the "a.b.c." prefix (through the last dot) of an IPv4 address. */
static void prefix24(const char *ip,char *out){
 int last=-1; int i=0;
 while(ip[i]){ if(ip[i]=='.') last=i; i++; }
 if(last<0){ out[0]=0; return; }
 for(i=0;i<=last;i++) out[i]=ip[i];
 out[last+1]=0;
}
/* --- PE import-table patcher: add an import of <dll>!<func> to a PE32 exe.
   Appends a new section holding a rebuilt import directory (old descriptors
   copied verbatim, plus one for the DLL), then points the PE header at it.
   The DLL's DllMain runs when the exe starts, which is how the Escargot
   Switcher patches Messenger's connections. Backs the exe up to <exe>.bak
   first (only if no backup exists yet); returns 1 patched, 2 already
   patched, 0 failed. --- */
#define HEAP_ZERO_MEMORY 0x00000008
static DWORD align_up(DWORD v,DWORD a){ return (v+a-1)&~(a-1); }
static DWORD pe_dword(BYTE *b,DWORD off){ return b[off]|(b[off+1]<<8)|(b[off+2]<<16)|((DWORD)b[off+3]<<24); }
static void pe_put_dword(BYTE *b,DWORD off,DWORD v){ b[off]=v&0xFF;b[off+1]=(v>>8)&0xFF;b[off+2]=(v>>16)&0xFF;b[off+3]=(v>>24)&0xFF; }
static WORD pe_word(BYTE *b,DWORD off){ return b[off]|(b[off+1]<<8); }
static void pe_put_word(BYTE *b,DWORD off,WORD v){ b[off]=v&0xFF;b[off+1]=(v>>8)&0xFF; }
static DWORD pe_strlen(const char *s){ DWORD n=0; while(s[n]) n++; return n; }
static int pe_strieq(const char *a,const char *b){
 while(*a && *b){ char ca=*a,cb=*b; if(ca>='A'&&ca<='Z')ca+=32; if(cb>='A'&&cb<='Z')cb+=32; if(ca!=cb) return 0; a++; b++; }
 return *a==*b;
}
/* map an RVA to a file offset using the section table; 0xFFFFFFFF if unmapped */
static DWORD pe_rva_to_off(BYTE *buf,DWORD rva,DWORD secOff,int nsec,DWORD sizeHeaders){
 int i;
 if(rva<sizeHeaders) return rva;
 for(i=0;i<nsec;i++){
  DWORD va=pe_dword(buf,secOff+i*40+12);
  DWORD vs=pe_dword(buf,secOff+i*40+8);
  DWORD raw=pe_dword(buf,secOff+i*40+20);
  if(!vs) vs=pe_dword(buf,secOff+i*40+16);
  if(rva>=va && rva<va+vs) return raw+(rva-va);
 }
 return 0xFFFFFFFF;
}
/* --- terminate a running process by exe name, via tskill. The Messenger
   runs as the desktop user while this exe runs as the SSH user, so
   OpenProcess(PROCESS_TERMINATE) is refused cross-user; tskill goes through
   the Terminal Services service and works. Waits for tskill to finish so
   the exe's file lock is released before patching. --- */
static void tskill_process(const char *exeName){
 static unsigned char si[68]; static unsigned char pi[16];
 char cmd[64]; int i,k=0;
 const char *t="tskill ";
 while(t[k]){ cmd[k]=t[k]; k++; }
 i=0; while(exeName[i] && exeName[i]!='.'){ cmd[k++]=exeName[i++]; }
 cmd[k]=0;
 for(i=0;i<68;i++) si[i]=0; for(i=0;i<16;i++) pi[i]=0;
 si[0]=68;
 if(CreateProcessA(NULL,cmd,NULL,NULL,0,CREATE_NO_WINDOW,NULL,NULL,si,pi)){
  HANDLE hProc=(HANDLE)(pi[0]|(pi[1]<<8)|(pi[2]<<16)|((DWORD)pi[3]<<24));
  HANDLE hThread=(HANDLE)(pi[4]|(pi[5]<<8)|(pi[6]<<16)|((DWORD)pi[7]<<24));
  if(hProc){ WaitForSingleObject(hProc,10000); CloseHandle(hProc); }
  if(hThread) CloseHandle(hThread);
 }
}
/* Run a command line (mutable buffer) hidden, wait up to 20s, return the
   process exit code, or -1 if it could not be started. */
static int run_wait(char *cmd){
 static unsigned char si[68]; static unsigned char pi[16];
 int i; DWORD code=0;
 for(i=0;i<68;i++) si[i]=0; for(i=0;i<16;i++) pi[i]=0;
 si[0]=68;
 if(!CreateProcessA(NULL,cmd,NULL,NULL,0,CREATE_NO_WINDOW,NULL,NULL,si,pi)) return -1;
 { HANDLE hProc=(HANDLE)(pi[0]|(pi[1]<<8)|(pi[2]<<16)|((DWORD)pi[3]<<24));
   HANDLE hThread=(HANDLE)(pi[4]|(pi[5]<<8)|(pi[6]<<16)|((DWORD)pi[7]<<24));
   if(hProc){ WaitForSingleObject(hProc,20000); GetExitCodeProcess(hProc,&code); CloseHandle(hProc); }
   if(hThread) CloseHandle(hThread); }
 return (int)code;
}
static int patch_exe_import(const char *exePath,const char *dllName,const char *funcName){
 HANDLE h,heap; DWORD fsize=0,got=0; BYTE *buf=NULL; int rc=0;
 DWORD peOff,optOff,secOff,nsec,optSize,sizeHeaders,sizeImage,secAlign,fileAlign;
 DWORD impRVA=0,impSize=0,impOff; int oldCount=0,i;
 DWORD descBytes,iltOff,iatOff,hintOff,dllOff,contentSize,newVA,newRawSize,newRawPtr;
 BYTE *sec=NULL; DWORD written=0; char bak[520];
 h=CreateFileA(exePath,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 if(h==(HANDLE)-1) return 0;
 fsize=GetFileSize(h,NULL);
 if(fsize<0x200 || fsize>0x2000000){ CloseHandle(h); return 0; }
 heap=GetProcessHeap();
 buf=(BYTE*)HeapAlloc(heap,HEAP_ZERO_MEMORY,fsize);
 if(!buf){ CloseHandle(h); return 0; }
 if(!ReadFile(h,buf,fsize,&got,NULL) || got!=fsize){ HeapFree(heap,0,buf); CloseHandle(h); return 0; }
 CloseHandle(h);
 if(buf[0]!='M' || buf[1]!='Z'){ HeapFree(heap,0,buf); return 0; }
 peOff=pe_dword(buf,0x3C);
 if(peOff+24>fsize || pe_dword(buf,peOff)!=0x00004550){ HeapFree(heap,0,buf); return 0; }
 if(pe_word(buf,peOff+4)!=0x14C){ HeapFree(heap,0,buf); return 0; } /* i386 only */
 nsec=pe_word(buf,peOff+6);
 optSize=pe_word(buf,peOff+20);
 optOff=peOff+24;
 if(pe_word(buf,optOff)!=0x10B){ HeapFree(heap,0,buf); return 0; } /* PE32 only */
 secOff=optOff+optSize;
 sizeHeaders=pe_dword(buf,optOff+60);
 sizeImage=pe_dword(buf,optOff+56);
 secAlign=pe_dword(buf,optOff+32);
 fileAlign=pe_dword(buf,optOff+36);
 if(!secAlign || !fileAlign || secOff+nsec*40>fsize){ HeapFree(heap,0,buf); return 0; }
 /* need room for one more 40-byte section header inside the headers */
 if(secOff+(nsec+1)*40>sizeHeaders){ HeapFree(heap,0,buf); return 0; }
 impRVA=pe_dword(buf,optOff+96+8);
 impSize=pe_dword(buf,optOff+96+12);
 if(impRVA){
  impOff=pe_rva_to_off(buf,impRVA,secOff,nsec,sizeHeaders);
  if(impOff==0xFFFFFFFF || impOff+20>fsize){ HeapFree(heap,0,buf); return 0; }
  while(oldCount<512){
   DWORD dOff=impOff+oldCount*20;
   if(dOff+20>fsize) break;
   if(!pe_dword(buf,dOff) && !pe_dword(buf,dOff+4) && !pe_dword(buf,dOff+8) && !pe_dword(buf,dOff+12) && !pe_dword(buf,dOff+16)) break;
   { DWORD nameRVA=pe_dword(buf,dOff+12); DWORD nameOff=pe_rva_to_off(buf,nameRVA,secOff,nsec,sizeHeaders);
     if(nameOff!=0xFFFFFFFF && nameOff<fsize && pe_strieq((const char*)buf+nameOff,dllName)){ HeapFree(heap,0,buf); return 2; } }
   oldCount++;
  }
 } else impOff=0;
 /* layout of the new section */
 descBytes=(oldCount+2)*20;
 iltOff=descBytes;
 iatOff=iltOff+8;
 { DWORD hb=2+pe_strlen(funcName)+1; if(hb&1) hb++; hintOff=iatOff+8; dllOff=hintOff+hb; }
 contentSize=dllOff+pe_strlen(dllName)+1;
 newVA=align_up(sizeImage,secAlign);
 newRawSize=align_up(contentSize,fileAlign);
 newRawPtr=align_up(fsize,fileAlign);
 sec=(BYTE*)HeapAlloc(heap,HEAP_ZERO_MEMORY,newRawSize);
 if(!sec){ HeapFree(heap,0,buf); return 0; }
 /* copy old descriptors, add the new one, null-terminate */
 if(oldCount && impOff) { DWORD k; for(k=0;k<(DWORD)oldCount*20;k++) sec[k]=buf[impOff+k]; }
 pe_put_dword(sec,oldCount*20,   newVA+iltOff); /* OriginalFirstThunk */
 pe_put_dword(sec,oldCount*20+4, 0);            /* TimeDateStamp */
 pe_put_dword(sec,oldCount*20+8, 0);            /* ForwarderChain */
 pe_put_dword(sec,oldCount*20+12,newVA+dllOff); /* Name */
 pe_put_dword(sec,oldCount*20+16,newVA+iatOff); /* FirstThunk */
 pe_put_dword(sec,iltOff,  newVA+hintOff);
 pe_put_dword(sec,iltOff+4,0);
 pe_put_dword(sec,iatOff,  newVA+hintOff);
 pe_put_dword(sec,iatOff+4,0);
 sec[hintOff]=0; sec[hintOff+1]=0;
 { DWORD k; for(k=0;k<pe_strlen(funcName);k++) sec[hintOff+2+k]=funcName[k]; }
 { DWORD k; for(k=0;k<pe_strlen(dllName);k++) sec[dllOff+k]=dllName[k]; }
 /* backup (only if none exists yet), then write the patched file */
 { int j=0; while(exePath[j] && j<500){ bak[j]=exePath[j]; j++; } bak[j]=0;
   { const char *s=".bak"; int k=0; while(s[k]) bak[j++]=s[k++]; bak[j]=0; } }
 if(!file_exists(bak)){
  if(!CopyFileA(exePath,bak,1)){ HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
 }
 /* patch the headers in the in-memory image */
 pe_put_word(buf,peOff+6,(WORD)(nsec+1));
 pe_put_dword(buf,optOff+56,newVA+align_up(contentSize,secAlign));
 pe_put_dword(buf,optOff+64,0); /* checksum: loader ignores it for exes */
 pe_put_dword(buf,optOff+96+8,newVA);
 pe_put_dword(buf,optOff+96+12,descBytes);
 { DWORD sh=secOff+nsec*40; int k; const char *nm=".escrgt";
   for(k=0;k<8;k++) buf[sh+k]= nm[k]?nm[k]:0;
   pe_put_dword(buf,sh+8,contentSize);
   pe_put_dword(buf,sh+12,newVA);
   pe_put_dword(buf,sh+16,newRawSize);
   pe_put_dword(buf,sh+20,newRawPtr);
   pe_put_dword(buf,sh+24,0); pe_put_dword(buf,sh+28,0);
   pe_put_word(buf,sh+32,0); pe_put_word(buf,sh+34,0);
   pe_put_dword(buf,sh+36,0x40|0x40000000|0x80000000);
 }
 h=CreateFileA(exePath,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 { int attempt=0;
   while(h==(HANDLE)-1 && attempt<6){ Sleep(500); attempt++;
     h=CreateFileA(exePath,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL); } }
 if(h==(HANDLE)-1){ HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
 if(!WriteFile(h,buf,fsize,&written,NULL) || written!=fsize){ CloseHandle(h); HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
 if(newRawPtr>fsize){
  DWORD gap=newRawPtr-fsize, z=0; BYTE *zb=(BYTE*)HeapAlloc(heap,HEAP_ZERO_MEMORY,gap);
  if(!zb){ CloseHandle(h); HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
  if(!WriteFile(h,zb,gap,&written,NULL) || written!=gap){ HeapFree(heap,0,zb); CloseHandle(h); HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
  HeapFree(heap,0,zb);
 }
 if(!WriteFile(h,sec,newRawSize,&written,NULL) || written!=newRawSize){ CloseHandle(h); HeapFree(heap,0,sec); HeapFree(heap,0,buf); return 0; }
 CloseHandle(h);
 HeapFree(heap,0,sec); HeapFree(heap,0,buf);
 rc=1;
 (void)i;
 return rc;
}
static int read_file(const char *path,char *buf,int max,DWORD *outLen){
 HANDLE h=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 DWORD got=0; if(h==(HANDLE)-1) return 0;
 if(!ReadFile(h,buf,max,&got,NULL)){CloseHandle(h);return 0;}
 CloseHandle(h); *outLen=got; return 1;
}
/* Convert an ASCII string to UTF-16LE (wide) for the Credential Manager.
   The owner email and password are ASCII by construction. */
static int a2w(const char *s,unsigned short *out,int max){
 int i=0; while(s[i] && i<max-1){ out[i]=(unsigned short)(unsigned char)s[i]; i++; }
 out[i]=0; return i;
}
/* Store the owner credential in the Windows Credential Manager, exactly as
   WLM itself does: target "WindowsLive:name=<email>", generic type, persist
   local machine, blob = password as UTF-16LE bytes. Returns 1 on success. */
static int store_credential(const char *email,const char *pw){
 static unsigned short target[128], user[100], blob[100];
 CREDENTIALW cred; int i=0, n=0;
 const char *pre="WindowsLive:name=";
 while(pre[i] && i<120){ target[i]=(unsigned short)(unsigned char)pre[i]; i++; }
 { int j=0; while(email[j] && i<127){ target[i++]=(unsigned short)(unsigned char)email[j++]; } }
 target[i]=0;
 a2w(email,user,100);
 a2w(pw,blob,100);
 n=strlen0(pw);
 cred.Flags=0; cred.Type=CRED_TYPE_GENERIC; cred.TargetName=target; cred.Comment=NULL;
 cred.LastWrittenLow=0; cred.LastWrittenHigh=0;
 cred.CredentialBlobSize=(DWORD)(n*2); cred.CredentialBlob=(unsigned char*)blob;
 cred.Persist=CRED_PERSIST_LOCAL_MACHINE; cred.AttributeCount=0; cred.Attributes=NULL;
 cred.TargetAlias=NULL; cred.UserName=user;
 return CredWriteW(&cred,0)?1:0;
}
/* Set the registry DefaultMemberName so WLM knows which account to sign in
   as on launch. Returns 1 on success. */
static int set_default_member(const char *email){
 void *hKey=NULL; DWORD disp=0; LONG rc;
 rc=RegCreateKeyExA(HKEY_CURRENT_USER,"Software\\Microsoft\\MSNMessenger\\PerPassportSettings",0,NULL,0,KEY_SET_VALUE,NULL,&hKey,&disp);
 if(rc!=0 || !hKey) return 0;
 rc=RegSetValueExA(hKey,"DefaultMemberName",0,REG_SZ,(const unsigned char*)email,(DWORD)(strlen0(email)+1));
 RegCloseKey(hKey);
 return rc==0?1:0;
}
/* Generate a random 16-char alphanumeric password via CryptGenRandom.
   Returns 1 on success. */
static int gen_password(char *out){
 void *prov=NULL; unsigned char rnd[16]; int i;
 static const char alpha[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
 if(!CryptAcquireContextA(&prov,NULL,NULL,PROV_RSA_FULL,CRYPT_VERIFYCONTEXT)) return 0;
 if(!CryptGenRandom(prov,16,rnd)){ CryptReleaseContext(prov,0); return 0; }
 CryptReleaseContext(prov,0);
 for(i=0;i<16;i++) out[i]=alpha[rnd[i]%62];
 out[16]=0;
 return 1;
}
/* Install the local CA into Trusted Root. The old CryptoAPI-only path
   reported success while the cert never landed, so this version verifies
   the install the same way the .NET X509Store approach does (caadd2.cs):
   after adding, re-open the store and find the cert by its SHA1 thumbprint.
   Tries LocalMachine first, then CurrentUser. Returns 1 only if the cert
   is verified present in one of them. */
static int install_ca(const char *pemPath){
 static char pem[8192]; static unsigned char der[8192]; DWORD pemLen=0,derLen=0;
 void *store=NULL,*ctx=NULL,*found=NULL; int ok=0;
 unsigned char hash[20]; DWORD hashLen=20; CRYPT_HASH_BLOB blob;
 if(!read_file(pemPath,pem,sizeof(pem)-1,&pemLen)) return 0;
 pem[pemLen]=0;
 if(!CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,NULL,&derLen,NULL,NULL)) return 0;
 if(derLen>sizeof(der)) return 0;
 if(!CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,der,&derLen,NULL,NULL)) return 0;
 ctx=CertCreateCertificateContext(X509_ASN_ENCODING,der,derLen);
 if(!ctx) return 0;
 if(!CertGetCertificateContextProperty(ctx,CERT_HASH_PROP_ID,hash,&hashLen)){ CertFreeCertificateContext(ctx); return 0; }
 blob.cbData=hashLen; blob.pbData=hash;
 /* LocalMachine Root first (the store WLM/SChannel reads). */
 store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_LOCAL_MACHINE,"ROOT");
 if(store){
  CertAddCertificateContextToStore(store,ctx,CERT_STORE_ADD_REPLACE_EXISTING,NULL);
  found=CertFindCertificateInStore(store,X509_ASN_ENCODING,0,CERT_FIND_SHA1_HASH,&blob,NULL);
  if(found){ CertFreeCertificateContext(found); ok=1; }
  CertCloseStore(store,0);
 }
 /* Fall back to CurrentUser Root if LocalMachine did not stick. */
 if(!ok){
  store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_CURRENT_USER,"ROOT");
  if(store){
   CertAddCertificateContextToStore(store,ctx,CERT_STORE_ADD_REPLACE_EXISTING,NULL);
   found=CertFindCertificateInStore(store,X509_ASN_ENCODING,0,CERT_FIND_SHA1_HASH,&blob,NULL);
   if(found){ CertFreeCertificateContext(found); ok=1; }
   CertCloseStore(store,0);
  }
 }
 CertFreeCertificateContext(ctx);
 return ok;
}
/* Find the LAN adapter on the same /24 as the server IP. Fills ip/mask/gw
   (gw is "0.0.0.0" or empty when no gateway is set). Returns 1 if found. */
static int find_lan_adapter(const char *serverIp,char *ipOut,char *maskOut,char *gwOut){
 char pre[32]; DWORD size=0; void *buf=NULL; int found=0;
 prefix24(serverIp,pre);
 if(!pre[0]) return 0;
 GetAdaptersInfo(NULL,&size);
 if(size<sizeof(IP_ADAPTER_INFO) || size>65536) return 0;
 buf=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,size);
 if(!buf) return 0;
 if(GetAdaptersInfo(buf,&size)!=0){ HeapFree(GetProcessHeap(),0,buf); return 0; }
 { IP_ADAPTER_INFO *a=(IP_ADAPTER_INFO*)buf;
   while(a && !found){
    char apre[32]; prefix24(a->IpAddressList.IpAddress,apre);
    if(apre[0] && str_eq(apre,pre)){
     int i=0; while(a->IpAddressList.IpAddress[i] && i<15){ ipOut[i]=a->IpAddressList.IpAddress[i]; i++; } ipOut[i]=0;
     i=0; while(a->IpAddressList.IpMask[i] && i<15){ maskOut[i]=a->IpAddressList.IpMask[i]; i++; } maskOut[i]=0;
     i=0; while(a->GatewayList.IpAddress[i] && i<15){ gwOut[i]=a->GatewayList.IpAddress[i]; i++; } gwOut[i]=0;
     found=1;
    }
    a=a->Next;
   } }
 HeapFree(GetProcessHeap(),0,buf);
 return found;
}
/* Fix a blank default gateway, only if one is missing. The gateway is the
   .1 of the server's /24. Never overwrites an existing gateway.
   Returns 0 failed/unknown, 1 already set, 2 set by installer. */
static int fix_gateway(const char *serverIp){
 static char ip[16], mask[16], gw[16], pre[32], cmd[220];
 int i=0, k=0;
 if(!find_lan_adapter(serverIp,ip,mask,gw)) return 0;
 if(gw[0] && !str_eq(gw,"0.0.0.0")) return 1; /* a gateway is already set */
 prefix24(serverIp,pre);
 if(!pre[0]) return 0;
 { const char *t="netsh interface ip set address \"Local Area Connection\" static ";
   while(t[k]){ cmd[k]=t[k]; k++; } }
 i=0; while(ip[i]){ cmd[k++]=ip[i++]; } cmd[k++]=' ';
 i=0; while(mask[i]){ cmd[k++]=mask[i++]; } cmd[k++]=' ';
 i=0; while(pre[i]){ cmd[k++]=pre[i++]; } cmd[k++]='1'; cmd[k++]=' ';
 cmd[k++]='1'; cmd[k]=0;
 return run_wait(cmd)==0?2:0;
}
/* Ensure the hosts file maps msn.local and g.msn.com to the server IP.
   XP SChannel does not validate an IP against a cert, so the hostname must
   resolve. Appends missing lines only, never duplicates. The whole file is
   read, the missing lines appended in memory, and the file rewritten, so no
   file-pointer seeking is needed.
   Returns 0 failed, 1 already present, 2 added. */
static int fix_hosts(const char *serverIp){
 static char winDir[260], path[300], content[8192];
 char line[120]; DWORD got=0; int hasMs=0, hasG=0;
 HANDLE h;
 if(!GetWindowsDirectoryA(winDir,sizeof(winDir))) return 0;
 { int i=0,k=0; while(winDir[i]){ path[i]=winDir[i]; i++; }
   { const char *s="\\system32\\drivers\\etc\\hosts"; while(s[k]) path[i++]=s[k++]; }
   path[i]=0; }
 if(read_file(path,content,sizeof(content)-1,&got)){
  content[got]=0;
  hasMs=str_find(content,"msn.local")!=NULL;
  hasG=str_find(content,"g.msn.com")!=NULL;
 } else { content[0]=0; got=0; }
 if(hasMs && hasG) return 1;
 /* Make sure the file ends with a newline before appending. */
 if(got>0 && content[got-1]!='\n' && got<8100){ content[got++]='\r'; content[got++]='\n'; content[got]=0; }
 if(!hasMs){
  int i=0,k=0; while(serverIp[i]){ line[i]=serverIp[i]; i++; }
  { const char *s=" msn.local\r\n"; while(s[k]) line[i++]=s[k++]; }
  line[i]=0;
  { int j=0; while(line[j] && got<8100){ content[got++]=line[j++]; } content[got]=0; }
 }
 if(!hasG){
  int i=0,k=0; while(serverIp[i]){ line[i]=serverIp[i]; i++; }
  { const char *s=" g.msn.com\r\n"; while(s[k]) line[i++]=s[k++]; }
  line[i]=0;
  { int j=0; while(line[j] && got<8100){ content[got++]=line[j++]; } content[got]=0; }
 }
 h=CreateFileA(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(h==(HANDLE)-1) return 0;
 { DWORD w=0; BOOL ok=WriteFile(h,content,got,&w,NULL); CloseHandle(h); return (ok && w==got)?2:0; }
}
/* Rewrite a Switcher INI so it points at the hostname, not the raw IP.
   XP SChannel does not validate an IP against the cert. Returns 1. */
static int rewrite_switcher_ini(const char *iniPath){
 int a=WritePrivateProfileStringA("options","server","msn.local",iniPath);
 int b=WritePrivateProfileStringA("options","configserver","msn.local",iniPath);
 return (a && b)?1:0;
}
static void do_install(HWND owner){
 char dir[512], ini[512], msnDir[512], src[512], dst[512], cmd[512], done[1200];
 char host[100], pwNote[200];
 int n=0, dll=0, ini1=0, ini2=0, ca=0, launched=0, p1=0, p2=0;
 int cred=0, dmem=0, gw=0, hosts=0, rw1=0, rw2=0, pwGen=0, pwBad=0;
 unsigned char si[68]; unsigned char pi[16]; int i;
 exe_dir(dir,sizeof(dir));
 join_path(ini,dir,"hermesxp.ini");
 /* Server IP: the host field in the UI is the source of truth (the user
    can type it there); fall back to the ini. No stale hardcoded default. */
 GetWindowTextA(g_host,host,sizeof(host));
 if(!host[0]) GetPrivateProfileStringA("Hermes","ServerIP","",host,sizeof(host),ini);
 if(!host[0]){ update_status("Enter the Hermes host IPv4 address first."); return; }
 { int j=0; while(host[j] && j<90){ g_serverIp[j]=host[j]; j++; } g_serverIp[j]=0; }
 GetPrivateProfileStringA("Hermes","OwnerEmail","user@hermes.local",g_owner,sizeof(g_owner),ini);
 GetPrivateProfileStringA("Hermes","OwnerPassword","",g_ownerPw,sizeof(g_ownerPw),ini);
 if(!g_owner[0]){ const char *d="user@hermes.local"; int j=0; while(d[j]){ g_owner[j]=d[j]; j++; } g_owner[j]=0; }
 /* Password rules: WLM 2009 truncates at 16 chars, so a longer password can
    never sign in. Refuse it (never truncate); generate a fresh 16-char one
    only when the ini password is empty, and write it back to the ini. */
 if(!g_ownerPw[0]){
  if(gen_password(g_ownerPw)){
   WritePrivateProfileStringA("Hermes","OwnerPassword",g_ownerPw,ini);
   pwGen=1;
  }
 } else if(strlen0(g_ownerPw)>16){
  pwBad=1;
 }
 if(pwBad){
  update_status("OwnerPassword in hermesxp.ini is over 16 chars. Fix it and run Install again.");
  MessageBoxA(owner,"The OwnerPassword in hermesxp.ini is longer than 16 characters.\n\nWLM 2009 truncates passwords at 16 characters, so a longer password can never sign in. Shorten it to 16 characters or less (or delete it to let the installer generate one), then run Install again.","Hermes XP install",MB_OK|MB_ICONWARNING);
  return;
 }
 /* Messenger install locations (WLM 2009 defaults). wlcomm.exe lives in
    Contacts, not Messenger, and the Switcher files must sit next to it.
    (g_contactsDir is file-scope so do_install's stack stays under 4K.) */
 {const char *d="C:\\Program Files\\Windows Live\\Messenger"; int j=0; while(d[j]){msnDir[j]=d[j];j++;} msnDir[j]=0;}
 {const char *d="C:\\Program Files\\Windows Live\\Contacts"; int j=0; while(d[j]){g_contactsDir[j]=d[j];j++;} g_contactsDir[j]=0;}
 join_path(dst,msnDir,"msnmsgr.exe");
 if(!file_exists(dst)){update_status("Messenger not found at the usual location.");return;}
 update_status("Installing Hermes XP files...");
 /* Automatic sign-in, no form typing: store the credential in the Windows
    Credential Manager and set the registry DefaultMemberName. WLM reads
    both on launch and signs in on its own. */
 if(g_owner[0] && g_ownerPw[0]){
  cred=store_credential(g_owner,g_ownerPw);
  dmem=set_default_member(g_owner);
 }
 /* Network setup the installer now owns: gateway, hosts, Switcher INIs. */
 gw=fix_gateway(g_serverIp);
 hosts=fix_hosts(g_serverIp);
 join_path(src,dir,"escargot.dll"); join_path(dst,msnDir,"escargot.dll");
 if(file_exists(src)) dll=CopyFileA(src,dst,0);
 join_path(src,dir,"msnmsgr.exe-escargot.ini"); join_path(dst,msnDir,"msnmsgr.exe-escargot.ini");
 if(file_exists(src)){ ini1=CopyFileA(src,dst,0); if(ini1) rw1=rewrite_switcher_ini(dst); }
 join_path(src,dir,"wlcomm.exe-escargot.ini"); join_path(dst,g_contactsDir,"wlcomm.exe-escargot.ini");
 if(file_exists(src)){ ini2=CopyFileA(src,dst,0); if(ini2) rw2=rewrite_switcher_ini(dst); }
 join_path(src,dir,"escargot.dll"); join_path(dst,g_contactsDir,"escargot.dll");
 if(file_exists(src) && file_exists(dst)==0) CopyFileA(src,dst,0);
 join_path(src,dir,"ca.pem");
 if(file_exists(src)) ca=install_ca(src);
 /* Patch both Messenger exes to import escargot.dll at startup, so the
    Switcher loads with no manual PE editing. Backups saved as .bak.
    Close any running Messenger first: a running exe is locked and cannot
    be rewritten. Install relaunches it afterwards. */
 tskill_process("msnmsgr.exe");
 tskill_process("wlcomm.exe");
 Sleep(1000); /* let the terminated processes release their file locks */
 join_path(src,msnDir,"msnmsgr.exe");
 p1=patch_exe_import(src,"escargot.dll","ImportMe");
 join_path(dst,g_contactsDir,"wlcomm.exe");
 p2=file_exists(dst)?patch_exe_import(dst,"escargot.dll","ImportMe"):0;
 join_path(cmd,msnDir,"msnmsgr.exe");
 /* ShellExecute (not CreateProcessA): the shell associates the new process
    with the interactive desktop, so Messenger's window actually appears.
    No typing: the pre-stored credential + DefaultMemberName make WLM
    sign in on its own. */
 launched=((DWORD)ShellExecuteA(owner,"open",cmd,NULL,NULL,1)>32);
 {const char *h="Installed:\n"; while(*h) done[n++]=*h++;}
 if(cred){const char *s="- MSN credential stored (Credential Manager)\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- MSN credential NOT stored (check the account and password)\n"; while(*s) done[n++]=*s++;}
 if(dmem){const char *s="- Default sign-in account set in the registry\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Default sign-in account NOT set in the registry\n"; while(*s) done[n++]=*s++;}
 if(gw==1){const char *s="- Default gateway already set (left alone)\n"; while(*s) done[n++]=*s++;}
 else if(gw==2){const char *s="- Default gateway was blank, set to the LAN gateway\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Default gateway NOT checked (could not read the adapter)\n"; while(*s) done[n++]=*s++;}
 if(hosts==1){const char *s="- Hosts file already maps msn.local\n"; while(*s) done[n++]=*s++;}
 else if(hosts==2){const char *s="- Hosts file updated (msn.local, g.msn.com)\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Hosts file NOT updated (could not write it)\n"; while(*s) done[n++]=*s++;}
 if(dll){const char *s="- escargot.dll next to Messenger\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- escargot.dll MISSING from this folder (copy it here first)\n"; while(*s) done[n++]=*s++;}
 if(ini1&&ini2){const char *s="- Switcher settings for both Messenger exes (now using msn.local)\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Switcher settings NOT placed (INI files missing from this folder)\n"; while(*s) done[n++]=*s++;}
 if(rw1&&rw2){const char *s="- Switcher INIs rewritten to use msn.local\n"; while(*s) done[n++]=*s++;}
 if(ca){const char *s="- Local CA installed into Trusted Root (verified)\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Local CA NOT installed (ca.pem missing, or run as an administrator)\n"; while(*s) done[n++]=*s++;}
 if(launched){const char *s="- Messenger launched\n"; while(*s) done[n++]=*s++;}
 if(p1==1||p1==2){const char *s="- msnmsgr.exe patched to load escargot.dll\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- msnmsgr.exe NOT patched (close Messenger and run Install again)\n"; while(*s) done[n++]=*s++;}
 if(p2==1||p2==2){const char *s="- wlcomm.exe patched to load escargot.dll\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- wlcomm.exe NOT patched (close Messenger and run Install again)\n"; while(*s) done[n++]=*s++;}
 if(pwGen){
  int j=0,k=0; const char *a="\nGenerated MSN password (also saved in hermesxp.ini):\n";
  while(a[j]){ pwNote[j]=a[j]; j++; }
  k=0; while(g_ownerPw[k] && j<180){ pwNote[j++]=g_ownerPw[k++]; }
  pwNote[j]=0;
  {const char *s="\nSet this same password as HERMES_MSN_OWNER_PASSWORD on the Hermes host, or the server will reject the sign-in.\n"; int q=0; while(s[q] && j<195){ pwNote[j++]=s[q++]; } pwNote[j]=0;}
  {const char *s=pwNote; while(*s && n<1150) done[n++]=*s++;}
 }
 {const char *s="\nDone. Messenger signs in on its own — pick the bot and start talking."; while(*s) done[n++]=*s++;}
 done[n]=0;
 update_status("Install finished. See the summary.");
 MessageBoxA(owner,done,"Hermes XP install",MB_OK|MB_ICONINFORMATION);
}
/* --- Screenshot and remote UI listener on port 18768. All HTTP actions
   require the 64-hex X-Hermes-Token and an IPv4 source matching
   [Remote] AllowedHostIP. The only remote actions are inspect, bounded click,
   printable text, allow-listed key, and authenticated BMP screenshot. --- */
static int take_screenshot(void){
 void *hScreen, *hMem, *hBmp, *hOld; int w, h; DWORD rowSize, imgSize; BYTE *px=NULL; int ok=0;
 BITMAPINFOHEADER bmi;
 CreateDirectoryA("C:\\HermesXP",NULL);
 hScreen=GetDC(NULL);
 if(!hScreen) return 0;
 w=GetSystemMetrics(SM_CXSCREEN); h=GetSystemMetrics(SM_CYSCREEN);
 if(w<=0 || h<=0){ ReleaseDC(NULL,hScreen); return 0; }
 hMem=CreateCompatibleDC(hScreen);
 if(!hMem){ ReleaseDC(NULL,hScreen); return 0; }
 hBmp=CreateCompatibleBitmap(hScreen,w,h);
 if(!hBmp){ DeleteDC(hMem); ReleaseDC(NULL,hScreen); return 0; }
 hOld=SelectObject(hMem,hBmp);
 if(!BitBlt(hMem,0,0,w,h,hScreen,0,0,SRCCOPY)){
  SelectObject(hMem,hOld); DeleteObject(hBmp); DeleteDC(hMem); ReleaseDC(NULL,hScreen); return 0;
 }
 rowSize=((DWORD)w*3+3)&~3u; imgSize=rowSize*(DWORD)h;
 px=(BYTE*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,imgSize);
 if(!px){ SelectObject(hMem,hOld); DeleteObject(hBmp); DeleteDC(hMem); ReleaseDC(NULL,hScreen); return 0; }
 bmi.biSize=40; bmi.biWidth=w; bmi.biHeight=h; bmi.biPlanes=1; bmi.biBitCount=24;
 bmi.biCompression=0; bmi.biSizeImage=imgSize; bmi.biXPelsPerMeter=0; bmi.biYPelsPerMeter=0;
 bmi.biClrUsed=0; bmi.biClrImportant=0;
 if(!GetDIBits(hMem,hBmp,0,(UINT)h,px,(void*)&bmi,DIB_RGB_COLORS)){
  HeapFree(GetProcessHeap(),0,px); SelectObject(hMem,hOld); DeleteObject(hBmp); DeleteDC(hMem); ReleaseDC(NULL,hScreen); return 0;
 }
 { HANDLE f=CreateFileA("C:\\HermesXP\\screenshot.bmp",GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
   if(f!=(HANDLE)-1){
    unsigned char hdr[54]; DWORD written=0; DWORD fileSize=54+imgSize; int i;
    for(i=0;i<54;i++) hdr[i]=0;
    hdr[0]='B'; hdr[1]='M';
    hdr[2]=(unsigned char)(fileSize&0xFF); hdr[3]=(unsigned char)((fileSize>>8)&0xFF);
    hdr[4]=(unsigned char)((fileSize>>16)&0xFF); hdr[5]=(unsigned char)((fileSize>>24)&0xFF);
    hdr[10]=54;
    hdr[14]=40;
    hdr[18]=(unsigned char)(w&0xFF); hdr[19]=(unsigned char)((w>>8)&0xFF);
    hdr[20]=(unsigned char)((w>>16)&0xFF); hdr[21]=(unsigned char)((w>>24)&0xFF);
    hdr[22]=(unsigned char)(h&0xFF); hdr[23]=(unsigned char)((h>>8)&0xFF);
    hdr[24]=(unsigned char)((h>>16)&0xFF); hdr[25]=(unsigned char)((h>>24)&0xFF);
    hdr[26]=1; hdr[28]=24;
    hdr[34]=(unsigned char)(imgSize&0xFF); hdr[35]=(unsigned char)((imgSize>>8)&0xFF);
    hdr[36]=(unsigned char)((imgSize>>16)&0xFF); hdr[37]=(unsigned char)((imgSize>>24)&0xFF);
    if(WriteFile(f,hdr,54,&written,NULL) && written==54){
     if(WriteFile(f,px,imgSize,&written,NULL) && written==imgSize) ok=1;
    }
    CloseHandle(f);
   } }
 HeapFree(GetProcessHeap(),0,px);
 SelectObject(hMem,hOld); DeleteObject(hBmp); DeleteDC(hMem); ReleaseDC(NULL,hScreen);
 return ok;
}
static int send_all(unsigned int sock,const char *buf,int len){
 int sent=0;
 while(sent<len){ int n=send(sock,buf+sent,len-sent,0); if(n<=0) return 0; sent+=n; }
 return 1;
}
static int http_header_end(const char *req,int len){
 int i; for(i=0;i<=len-4;i++) if(req[i]=='\r'&&req[i+1]=='\n'&&req[i+2]=='\r'&&req[i+3]=='\n') return i+4;
 return 0;
}
static int request_is(const char *req,const char *method,const char *path);
static int read_http_request(unsigned int sock,char *req,int cap,int *outLen,int *bodyLen){
 int used=0,header=0,hasLength=0,contentLength=0,expected=-1;
 while(used<cap-1){
  int n=recv(sock,req+used,cap-1-used,0);
  if(n<=0) return 0;
  used+=n; req[used]=0;
  if(!header){
   header=http_header_end(req,used);
   if(header){
    if(request_is(req,"POST","/update/exe") || request_is(req,"POST","/update/helper")){
     *outLen=used;*bodyLen=-1;return 1; /* streamed, not 512-byte UI action */
    }
    if(!hermesxp_remote_content_length(req,&contentLength,&hasLength)) return 0;
    if((str_find(req,"POST ")==req) && !hasLength) return 0;
    expected=header+(hasLength?contentLength:0);
    if(expected>=cap) return 0;
   }
  }
  if(header && used>=expected){
   if(used!=expected) return 0;
   req[used]=0; *outLen=used; *bodyLen=hasLength?contentLength:0; return 1;
  }
 }
 return 0;
}
static void send_http_text(unsigned int sock,const char *status,const char *body){
 char response[512]; int i=0,j=0,bodyLen=strlen0(body); const char *a="HTTP/1.0 ",*b="\r\nContent-Type: text/plain\r\nContent-Length: ",*c="\r\nConnection: close\r\n\r\n";
 while(*a)response[i++]=*a++; while(*status)response[i++]=*status++; while(*b)response[i++]=*b++;
 append_number(response,&i,(unsigned int)bodyLen); while(*c)response[i++]=*c++;
 while(body[j])response[i++]=body[j++]; send_all(sock,response,i);
}
static int remote_peer_allowed(const SOCKADDR_IN *peer){
 unsigned long allowed;
 if(!peer || !remote_token_is_valid(g_remote_token) || !g_remote_allowed_ip[0]) return 0;
 allowed=inet_addr(g_remote_allowed_ip);
 return allowed!=0xFFFFFFFFUL && peer->sin_addr==allowed;
}
static int request_is(const char *req,const char *method,const char *path){
 int i=0; while(method[i]){if(req[i]!=method[i])return 0;i++;}
 if(req[i++]!=' ')return 0;
 {int j=0;while(path[j]){if(req[i+j]!=path[j])return 0;j++;}return req[i+j]==' ';}
}
#include "update_receiver.h"
static void press_key(BYTE vk){ keybd_event(vk,0,0,NULL); keybd_event(vk,0,KEYEVENTF_KEYUP,NULL); }
static int do_remote_ui(unsigned int sock,const char *req,int bodyLen){
 int header=http_header_end(req,strlen0(req)); const char *body=req+header;
 if(request_is(req,"GET","/ui/inspect")){
  if(bodyLen!=0){send_http_text(sock,"400 Bad Request","inspect takes no body");return 1;}
  char title[128],out[220]; int w=GetSystemMetrics(SM_CXSCREEN),h=GetSystemMetrics(SM_CYSCREEN),p=0,i=0;
  HWND foreground=GetForegroundWindow();
  if(foreground) GetWindowTextA(foreground,title,sizeof(title)); else title[0]=0;
  if(!title[0]){const char *s="(untitled)";while(*s)title[i++]=*s++;title[i]=0;}
  out[p++]='w';out[p++]='i';out[p++]='d';out[p++]='t';out[p++]='h';out[p++]='=';append_number(out,&p,(unsigned int)w);
  out[p++]=' ';out[p++]='h';out[p++]='e';out[p++]='i';out[p++]='g';out[p++]='h';out[p++]='t';out[p++]='=';append_number(out,&p,(unsigned int)h);
  out[p++]=' ';out[p++]='t';out[p++]='i';out[p++]='t';out[p++]='l';out[p++]='e';out[p++]='=';
  for(i=0;title[i] && p<200;i++){unsigned char c=(unsigned char)title[i];out[p++]=(c<32||c>126)?'?':(char)c;}out[p]=0;
  send_http_text(sock,"200 OK",out); return 1;
 }
 if(request_is(req,"POST","/ui/click")){
  unsigned int x,y; int right; int w=GetSystemMetrics(SM_CXSCREEN),h=GetSystemMetrics(SM_CYSCREEN);
  if(!hermesxp_remote_parse_click(body,bodyLen,(unsigned int)w,(unsigned int)h,&x,&y,&right)){
   send_http_text(sock,"400 Bad Request","invalid coordinates or button");return 1;
  }
  if(!SetCursorPos((int)x,(int)y)){send_http_text(sock,"500 Internal Server Error","click failed");return 1;}
  if(right){mouse_event(MOUSEEVENTF_RIGHTDOWN,0,0,0,NULL);mouse_event(MOUSEEVENTF_RIGHTUP,0,0,0,NULL);}
  else {mouse_event(MOUSEEVENTF_LEFTDOWN,0,0,0,NULL);mouse_event(MOUSEEVENTF_LEFTUP,0,0,0,NULL);}
  send_http_text(sock,"200 OK","clicked");return 1;
 }
 if(request_is(req,"POST","/ui/type")){
  int i; short key; unsigned int mods;
  if(!hermesxp_remote_text_is_safe(body,bodyLen)){send_http_text(sock,"400 Bad Request","text must be 1-128 printable ASCII characters");return 1;}
  for(i=0;i<bodyLen;i++){key=VkKeyScanA(body[i]);mods=((unsigned short)key)>>8;if(key==-1 || (mods&6)){send_http_text(sock,"400 Bad Request","unsupported key character");return 1;}}
  for(i=0;i<bodyLen;i++){
   key=VkKeyScanA(body[i]);mods=((unsigned short)key)>>8;
   if(mods&1)keybd_event(VK_SHIFT,0,0,NULL);
   keybd_event((BYTE)(key&0xFF),0,0,NULL);keybd_event((BYTE)(key&0xFF),0,KEYEVENTF_KEYUP,NULL);
   if(mods&1)keybd_event(VK_SHIFT,0,KEYEVENTF_KEYUP,NULL);
  }
  send_http_text(sock,"200 OK","typed");return 1;
 }
 if(request_is(req,"POST","/ui/key")){
  char name[16]; unsigned int vk; int i;
  if(bodyLen<1 || bodyLen>12){send_http_text(sock,"400 Bad Request","invalid key");return 1;}
  for(i=0;i<bodyLen;i++)name[i]=body[i];name[bodyLen]=0;vk=hermesxp_remote_key_code(name);
  if(!vk){send_http_text(sock,"400 Bad Request","key not allow-listed");return 1;}
  press_key((BYTE)vk);send_http_text(sock,"200 OK","key sent");return 1;
 }
 return 0;
}
static DWORD WINAPI screenshot_server(void *param){
 static unsigned char wsadata[512];
 unsigned int srv, cli; SOCKADDR_IN addr;
 (void)param;
 if(WSAStartup(0x0202,wsadata)!=0) return 1;
 srv=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(srv==INVALID_SOCKET){ WSACleanup(); return 1; }
 /* Updating a running XP companion closes a listener with recent TCP
    connections in TIME_WAIT. Without SO_REUSEADDR, the replacement GUI
    starts successfully but its server thread permanently exits on bind().
    Retry as well: XP sometimes needs a short socket teardown window. */
 {int reuse=1;setsockopt(srv,SOL_SOCKET,SO_REUSEADDR,(const char*)&reuse,sizeof(reuse));}
 addr.sin_family=AF_INET; addr.sin_port=htons(18768); addr.sin_addr=0;
 { int i; for(i=0;i<8;i++) addr.sin_zero[i]=0; }
 {int retry,ok=0;
  for(retry=0;retry<180;retry++){
   if(bind(srv,&addr,sizeof(addr))==0){ok=1;break;}
   Sleep(500);
  }
  if(!ok){closesocket(srv);WSACleanup();return 1;}
 }
 if(listen(srv,5)!=0){ closesocket(srv); WSACleanup(); return 1; }
 /* Only the newly activated GUI can signal this event, and only after its
    own network listener is bound and accepting connections. The rollback
    helper must not mistake the previous process's listener for the new one. */
 if(g_update_activation){
  HANDLE ready=OpenEventA(0x0002u,0,"Local\\HermesXP.Updated.GuiReady");
  if(ready){SetEvent(ready);CloseHandle(ready);}
 }
 for(;;){
  char req[1024]; int n,bodyLen; SOCKADDR_IN caddr; int clen=sizeof(caddr); DWORD timeout=3000;
  cli=accept(srv,&caddr,&clen);
  if(cli==INVALID_SOCKET) continue;
  setsockopt(cli,SOL_SOCKET,SO_RCVTIMEO,(const char*)&timeout,sizeof(timeout));
  if(read_http_request(cli,req,sizeof(req),&n,&bodyLen)){
   if(!remote_peer_allowed(&caddr) || !hermesxp_remote_authorized(req,g_remote_token)){
    send_http_text(cli,"401 Unauthorized","authentication failed");
   } else if((request_is(req,"POST","/update/exe") ||
              request_is(req,"POST","/update/helper")) && bodyLen==-1){
    handle_update_stream(cli,req,n);
   } else if(request_is(req,"GET","/update/status") ||
             request_is(req,"GET","/update/helper-status")){
    if(bodyLen!=0)send_http_text(cli,"400 Bad Request","status takes no body");
    else handle_update_status(cli,request_is(req,"GET","/update/helper-status"));
   } else if(request_is(req,"POST","/voice/invite") && bodyLen==0){
    if(g_main_window && PostMessageA(g_main_window,WM_HERMESXP_VOICE_INVITE,0,0))
     send_http_text(cli,"202 Accepted","voice invite delivered");
    else send_http_text(cli,"503 Unavailable","voice window unavailable");
   } else if(request_is(req,"POST","/voice/end") && bodyLen==0){
    g_voice_cancel=1;
    send_http_text(cli,"202 Accepted","stop requested");
   } else if(request_is(req,"GET","/screenshot.bmp")){
    if(bodyLen!=0){send_http_text(cli,"400 Bad Request","screenshot takes no body");}
    else {
    take_screenshot();
    { HANDLE f=CreateFileA("C:\\HermesXP\\screenshot.bmp",GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
      if(f!=(HANDLE)-1){
       DWORD size=GetFileSize(f,NULL);
       if(size!=0xFFFFFFFF && size>0 && size<0x2000000){
        BYTE *data=(BYTE*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,size);
        if(data){
         DWORD got=0;
         if(ReadFile(f,data,size,&got,NULL) && got==size){
          char hdr[160]; int hl=0; const char *t="HTTP/1.0 200 OK\r\nContent-Type: image/bmp\r\nContent-Length: ";
          while(*t) hdr[hl++]=*t++;
          { char num[16]; int ni=0, k; DWORD v=size;
            if(v==0) num[ni++]='0';
            else { char rev[16]; int ri=0; while(v>0){ rev[ri++]=(char)('0'+v%10); v/=10; } while(ri>0) num[ni++]=rev[--ri]; }
            num[ni]=0; k=0; while(num[k]) hdr[hl++]=num[k++]; }
          { const char *e="\r\n\r\n"; while(*e) hdr[hl++]=*e++; }
          hdr[hl]=0;
          send_all(cli,hdr,hl);
          send_all(cli,(const char*)data,(int)size);
         }
         HeapFree(GetProcessHeap(),0,data);
        }
       }
       CloseHandle(f);
      } else {
       const char *nf="HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n";
       send_all(cli,nf,strlen0(nf));
      } }
    }
   } else if(!do_remote_ui(cli,req,bodyLen)){
    send_http_text(cli,"404 Not Found","unknown endpoint");
   }
  }
  closesocket(cli);
 }
 return 0;
}
#include "voice_turn.h"
static LRESULT WINAPI window_proc(HWND h, UINT msg, WPARAM w, LPARAM l){
 if(msg==WM_CREATE){
  char dir[512], ini[512], host[100], ownerLine[160];
  exe_dir(dir,sizeof(dir));
  join_path(ini,dir,"hermesxp.ini");
  GetPrivateProfileStringA("Hermes","ServerIP","",host,sizeof(host),ini);
  GetPrivateProfileStringA("Hermes","OwnerEmail","user@hermes.local",g_owner,sizeof(g_owner),ini);
  GetPrivateProfileStringA("Hermes","OwnerPassword","",g_ownerPw,sizeof(g_ownerPw),ini);
  add("STATIC","Hermes XP | First connection",0,18,16,330,24,h,100);
  add("STATIC","Hermes host IPv4 address:",0,18,57,225,20,h,101);
  g_host=add("EDIT",host,WS_BORDER|WS_TABSTOP|ES_AUTOHSCROLL,18,82,222,25,h,102);
  add("BUTTON","Test connection",WS_TABSTOP|BS_DEFPUSHBUTTON,246,82,144,26,h,103);
  add("BUTTON","Install for MSN",WS_TABSTOP,18,118,222,26,h,107);
  add("BUTTON","Screenshot",WS_TABSTOP,246,118,144,26,h,109);
  if(g_owner[0]){
   int i=0,j=0; const char *pre="MSN: ";
   while(pre[i]){ownerLine[j++]=pre[i++];}
   i=0; while(g_owner[i] && j<150){ownerLine[j++]=g_owner[i++];}
   ownerLine[j]=0;
   add("STATIC",ownerLine,0,246,122,144,20,h,108);
  }
  add("STATIC","Network status:",0,18,154,210,20,h,110);
  g_network_status=add("STATIC","Checking Windows network status...",0,18,179,372,22,h,112);
  add("STATIC","Connect to Wi-Fi or Ethernet using Windows XP.",0,18,207,374,20,h,113);
  add("BUTTON","Network Connections...",WS_TABSTOP,18,235,214,27,h,111);
  add("BUTTON","Refresh status",WS_TABSTOP,246,235,144,27,h,115);
  refresh_network_status();
  SetTimer(h,1,15000,NULL);
  g_status=add("STATIC","Ready. Test only: remote controls are disabled.",0,18,270,383,24,h,104);
  g_voice_button=add("BUTTON","Talk to Hermes (5s)",WS_TABSTOP,18,297,214,27,h,117);
  if(!g_remote_token[0] || !g_remote_allowed_ip[0]) update_status("Remote UI locked; configure [Remote] Token and AllowedHostIP.");
  add("STATIC","Voice companion uses LAN audio, not Messenger's native Call.",0,18,332,390,22,h,105);
  add("STATIC","Windows XP SP3  |  32-bit  |  HermesXP voice preview",0,18,358,390,22,h,106);
  return 0;
 }
 if(msg==WM_COMMAND && (w&0xFFFF)==103){probe(h);return 0;}
 if(msg==WM_COMMAND && (w&0xFFFF)==107){do_install(h);return 0;}
 if(msg==WM_COMMAND && (w&0xFFFF)==109){
  if(take_screenshot()) update_status("Screenshot saved to C:\\HermesXP\\screenshot.bmp");
  else update_status("Screenshot failed.");
  return 0;
 }
 if(msg==WM_COMMAND && (w&0xFFFF)==111){open_windows_network_connections(h);return 0;}
 if(msg==WM_COMMAND && (w&0xFFFF)==115){refresh_network_status();return 0;}
 if(msg==WM_COMMAND && (w&0xFFFF)==117){voice_toggle();return 0;}
 if(msg==WM_HERMESXP_VOICE_INVITE){
  if(!g_voice_running &&
    MessageBoxA(h,"Hermes is calling from MSN. Accept voice conversation?\n\nThis uses the HermesXP audio companion, not native Messenger calling.",
                "Incoming Hermes voice invite",MB_YESNO|MB_ICONINFORMATION)==IDYES)
   voice_toggle();
  return 0;
 }
 if(msg==WM_TIMER && w==1){refresh_network_status();return 0;}
 if(msg==WM_CLOSE){DestroyWindow(h);return 0;}
 if(msg==WM_DESTROY){g_voice_cancel=1;KillTimer(h,1);PostQuitMessage(0);return 0;}
 return DefWindowProcA(h,msg,w,l);
}
static void load_remote_config(void){
 char dir[512],ini[512]; exe_dir(dir,sizeof(dir)); join_path(ini,dir,"hermesxp.ini");
 GetPrivateProfileStringA("Remote","Token","",g_remote_token,sizeof(g_remote_token),ini);
 GetPrivateProfileStringA("Remote","AllowedHostIP","",g_remote_allowed_ip,sizeof(g_remote_allowed_ip),ini);
 if(!remote_token_is_valid(g_remote_token))g_remote_token[0]=0;
 if(!g_remote_allowed_ip[0] || inet_addr(g_remote_allowed_ip)==0xFFFFFFFFUL)g_remote_allowed_ip[0]=0;
}
void WINAPI WinMainCRTStartup(void){
 WNDCLASSA c; MSG msg; HWND h; DWORD tid=0; HANDLE single_instance=NULL;
 g_instance=GetModuleHandleA(NULL);
 load_remote_config();
 {const char *cl=GetCommandLineA();
  g_update_activation=cl && str_find(cl,"/update-activation")!=NULL;
 }
 /* Command-line trigger: "HermesXP.exe /screenshot" captures the screen
    and exits without opening the window. */
 { const char *cl=GetCommandLineA();
   if(cl && str_find(cl,"/screenshot")){ take_screenshot(); ExitProcess(0); } }
 /* Only one interactive instance may bind the authenticated listener.
    Windows XP otherwise lets two GUI copies race on port 18768 (SO_REUSEADDR)
    and an updater can mistake the wrong process for a successful restart.
    The /update-selftest candidate deliberately bypasses the mutex. */
 {const char *cl=GetCommandLineA();
  if(!cl || !str_find(cl,"/update-selftest")){
   single_instance=CreateMutexA(NULL,0,"Local\\HermesXP.Companion.SingleInstance");
   if(!single_instance || GetLastError()==183){
    if(single_instance)CloseHandle(single_instance);
    ExitProcess(0);
   }
  }
 }
 /* Initialize the interactive GUI before starting the optional listener. */
 c.style=0; c.lpfnWndProc=window_proc; c.cbClsExtra=0; c.cbWndExtra=0;
 c.hInstance=g_instance=GetModuleHandleA(NULL); c.hIcon=NULL; c.hCursor=NULL; c.hbrBackground=(HBRUSH)6;
 c.lpszMenuName=NULL; c.lpszClassName="HermesXPMainWindow";
 if(!RegisterClassA(&c))ExitProcess(2);
 h=CreateWindowExA(0,"HermesXPMainWindow","Hermes XP - Ruiter Companion",WS_OVERLAPPEDWINDOW,80,80,426,440,NULL,NULL,g_instance,NULL);
 if(!h)ExitProcess(1);
 g_main_window=h;
 /* Updater candidate validation: load all DLLs, create the custom window,
    initialize controls, and exit cleanly without opening any listening ports,
    installing any certificates, or changing system settings. */
 {const char *cl=GetCommandLineA();
  if(cl && str_find(cl,"/update-selftest")){
   DestroyWindow(h);
   ExitProcess(0);
  }
 }
 /* Background authenticated screenshot and narrow UI-action listener. */
 CreateThread(NULL,0,screenshot_server,NULL,0,&tid);
 ShowWindow(h,5);UpdateWindow(h);
 while(GetMessageA(&msg,NULL,0,0)>0){TranslateMessage(&msg);DispatchMessageA(&msg);}
 ExitProcess((UINT)msg.wParam);
}
