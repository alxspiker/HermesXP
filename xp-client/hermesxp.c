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

/* CryptoAPI (crypt32) for installing the local CA into Trusted Root. */
IMPORT BOOL WINAPI CryptStringToBinaryA(const char *,DWORD,DWORD,void *,DWORD *,DWORD *,DWORD *);
IMPORT void *WINAPI CertOpenStore(DWORD,DWORD,DWORD,DWORD,const void *);
IMPORT void *WINAPI CertCreateCertificateContext(DWORD,const void *,DWORD);
IMPORT BOOL WINAPI CertAddCertificateContextToStore(void *,const void *,DWORD,void *);
IMPORT BOOL WINAPI CertFreeCertificateContext(const void *);
IMPORT BOOL WINAPI CertCloseStore(void *,DWORD);

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
static char g_owner[100];
static char g_ownerPw[100];
static char g_contactsDir[512];

/* --- XP-side installer: puts the connection files in place so WLM can use
   the local server, and patches both Messenger exes to import escargot.dll
   at startup so the Switcher loads with no manual steps. Reads hermesxp.ini
   from this exe's own folder (written by the plugin's package builder):
   [Hermes] ServerIP, OwnerEmail. --- */
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
#define CREATE_NO_WINDOW 0x08000000
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
static int install_ca(const char *pemPath){
 static char pem[8192]; static unsigned char der[8192]; DWORD pemLen=0,derLen=0;
 void *store=NULL,*ctx=NULL; int ok=0;
 if(!read_file(pemPath,pem,sizeof(pem)-1,&pemLen)) return 0;
 pem[pemLen]=0;
 if(!CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,NULL,&derLen,NULL,NULL)) return 0;
 if(derLen>sizeof(der)) return 0;
 if(!CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,der,&derLen,NULL,NULL)) return 0;
 ctx=CertCreateCertificateContext(X509_ASN_ENCODING,der,derLen);
 if(!ctx) return 0;
 store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_LOCAL_MACHINE,"ROOT");
 if(!store) store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_CURRENT_USER,"ROOT");
 if(store){
  ok=CertAddCertificateContextToStore(store,ctx,CERT_STORE_ADD_REPLACE_EXISTING,NULL);
  CertCloseStore(store,0);
 }
 CertFreeCertificateContext(ctx);
 return ok;
}
/* --- Auto-login for WLM: the sign-in form is DirectUI (no real EDIT child
   windows), so the exe types into it with the keyboard. It pastes the owner
   address and password from hermesxp.ini via the clipboard (Ctrl+V), tabs
   through the "remember password" / "sign me in automatically" boxes, and
   presses Enter. After the first sign-in WLM remembers the credentials and
   signs in on its own on later launches. Returns 1 if it attempted. */
#define VK_TAB 0x09
#define VK_RETURN 0x0D
#define VK_SPACE 0x20
#define VK_CONTROL 0x11
#define VK_SHIFT 0x10
#define VK_OEM_MINUS 0xBD
#define KEYEVENTF_KEYUP 2
#define CF_TEXT 1
#define GMEM_MOVEABLE 2
static void send_key(BYTE vk){
 keybd_event(vk,0,0,0); Sleep(60); keybd_event(vk,0,KEYEVENTF_KEYUP,0); Sleep(60);
}
static void send_key_shift(BYTE vk){
 keybd_event(VK_SHIFT,0,0,0); Sleep(40);
 keybd_event(vk,0,0,0); Sleep(60); keybd_event(vk,0,KEYEVENTF_KEYUP,0); Sleep(40);
 keybd_event(VK_SHIFT,0,KEYEVENTF_KEYUP,0); Sleep(60);
}
/* Type a string key by key (the DirectUI password edit does not accept
   Ctrl+V paste, so the password must be typed). Handles the token_urlsafe
   alphabet: A-Z (shift), a-z, 0-9, '-' and '_'. */
static void type_string(const char *s){
 int i=0;
 while(s[i]){
  char c=s[i];
  if(c>='a' && c<='z') send_key((BYTE)('A'+(c-'a')));
  else if(c>='A' && c<='Z') send_key_shift((BYTE)c);
  else if(c>='0' && c<='9') send_key((BYTE)c);
  else if(c=='-') send_key(VK_OEM_MINUS);
  else if(c=='_') send_key_shift(VK_OEM_MINUS);
  i++;
 }
}
static void send_ctrl_v(void){
 keybd_event(VK_CONTROL,0,0,0); Sleep(60);
 keybd_event('V',0,0,0); Sleep(60); keybd_event('V',0,KEYEVENTF_KEYUP,0); Sleep(60);
 keybd_event(VK_CONTROL,0,KEYEVENTF_KEYUP,0); Sleep(60);
}
static int set_clipboard_text(const char *s){
 int n=0; void *mem; char *p;
 while(s[n]) n++;
 mem=GlobalAlloc(GMEM_MOVEABLE,(DWORD)(n+1));
 if(!mem) return 0;
 p=(char*)GlobalLock(mem);
 if(!p) return 0;
 {int i=0; while(s[i]){p[i]=s[i];i++;} p[i]=0;}
 GlobalUnlock(mem);
 if(!OpenClipboard(NULL)) return 0;
 EmptyClipboard();
 SetClipboardData(CF_TEXT,mem);
 CloseClipboard();
 return 1;
}
static int auto_login_wlm(void){
 HWND w; int tries=0; DWORD wlmTid, myTid, pid=0;
 if(!g_owner[0] || !g_ownerPw[0]) return 0;
 /* Wait for the WLM sign-in window (it takes a few seconds on this netbook). */
 while(tries<30){
  w=FindWindowA("MSBLWindowClass",NULL);
  if(w) break;
  Sleep(500); tries++;
 }
 if(!w) return 0;
 /* Attach our input thread to WLM's so SetForegroundWindow works from a
    process that is not already the foreground app (otherwise the keystrokes
    go to the wrong window). Retry until WLM is actually foreground. */
 wlmTid=GetWindowThreadProcessId(w,&pid);
 myTid=GetCurrentThreadId();
 AttachThreadInput(myTid,wlmTid,1);
 tries=0;
 while(tries<10){
  SetForegroundWindow(w);
  Sleep(300);
  /* (GetForegroundWindow is not imported; rely on the attach + retry.) */
  tries++;
  break;
 }
 Sleep(1500);
 /* Fresh sign-in: the email field has focus. Paste the address (paste works
    in the email field), Tab to the password field, TYPE the password (the
    DirectUI password edit does not accept Ctrl+V). */
 set_clipboard_text(g_owner); send_ctrl_v();
 send_key(VK_TAB);
 type_string(g_ownerPw);
 /* Tab to "remember my password", check it; Tab to "sign me in
    automatically", check it; Tab to the Sign in button and press it. */
 send_key(VK_TAB); send_key(VK_SPACE);
 send_key(VK_TAB); send_key(VK_SPACE);
 send_key(VK_TAB); send_key(VK_SPACE);
 AttachThreadInput(myTid,wlmTid,0);
 return 1;
}
static void do_install(HWND owner){
 char dir[512], msnDir[512], src[512], dst[512], cmd[512], done[700];
 int n=0, dll=0, ini1=0, ini2=0, ca=0, launched=0, p1=0, p2=0;
 unsigned char si[68]; unsigned char pi[16]; int i;
 exe_dir(dir,sizeof(dir));
 /* Messenger install locations (WLM 2009 defaults). wlcomm.exe lives in
    Contacts, not Messenger, and the Switcher files must sit next to it.
    (g_contactsDir is file-scope so do_install's stack stays under 4K.) */
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
    with the interactive desktop, so Messenger's window actually appears. */
 launched=((DWORD)ShellExecuteA(owner,"open",cmd,NULL,NULL,1)>32);
 if(launched && g_owner[0] && g_ownerPw[0]){
  /* Sign Messenger in on its own: no typing, no sign-in step for the user. */
  auto_login_wlm();
 }
 {const char *h="Installed:\n"; while(*h) done[n++]=*h++;}
 if(dll){const char *s="- escargot.dll next to Messenger\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- escargot.dll MISSING from this folder (copy it here first)\n"; while(*s) done[n++]=*s++;}
 if(ini1&&ini2){const char *s="- Switcher settings for both Messenger exes\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Switcher settings NOT placed (INI files missing from this folder)\n"; while(*s) done[n++]=*s++;}
 if(ca){const char *s="- Local CA installed into Trusted Root\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- Local CA NOT installed (ca.pem missing, or run as an administrator)\n"; while(*s) done[n++]=*s++;}
 if(launched){const char *s="- Messenger launched\n"; while(*s) done[n++]=*s++;}
 if(p1==1||p1==2){const char *s="- msnmsgr.exe patched to load escargot.dll\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- msnmsgr.exe NOT patched (close Messenger and run Install again)\n"; while(*s) done[n++]=*s++;}
 if(p2==1||p2==2){const char *s="- wlcomm.exe patched to load escargot.dll\n"; while(*s) done[n++]=*s++;}
 else {const char *s="- wlcomm.exe NOT patched (close Messenger and run Install again)\n"; while(*s) done[n++]=*s++;}
 {const char *s="\nDone. Messenger signs in on its own — pick the bot and start talking."; while(*s) done[n++]=*s++;}
 done[n]=0;
 update_status("Install finished. See the summary.");
 MessageBoxA(owner,done,"Hermes XP install",MB_OK|MB_ICONINFORMATION);
}
static LRESULT WINAPI window_proc(HWND h, UINT msg, WPARAM w, LPARAM l){
 if(msg==WM_CREATE){
  char dir[512], ini[512], host[100], ownerLine[160];
  exe_dir(dir,sizeof(dir));
  join_path(ini,dir,"hermesxp.ini");
  GetPrivateProfileStringA("Hermes","ServerIP","192.168.1.20",host,sizeof(host),ini);
  GetPrivateProfileStringA("Hermes","OwnerEmail","",g_owner,sizeof(g_owner),ini);
  GetPrivateProfileStringA("Hermes","OwnerPassword","",g_ownerPw,sizeof(g_ownerPw),ini);
  add("STATIC","Hermes XP | First connection",0,18,16,330,24,h,100);
  add("STATIC","Hermes host IPv4 address:",0,18,57,225,20,h,101);
  g_host=add("EDIT",host,WS_BORDER|WS_TABSTOP|ES_AUTOHSCROLL,18,82,222,25,h,102);
  add("BUTTON","Test connection",WS_TABSTOP|BS_DEFPUSHBUTTON,246,82,144,26,h,103);
  add("BUTTON","Install for MSN",WS_TABSTOP,18,118,222,26,h,107);
  if(g_owner[0]){
   int i=0,j=0; const char *pre="MSN: ";
   while(pre[i]){ownerLine[j++]=pre[i++];}
   i=0; while(g_owner[i] && j<150){ownerLine[j++]=g_owner[i++];}
   ownerLine[j]=0;
   add("STATIC",ownerLine,0,246,122,144,20,h,108);
  }
  g_status=add("STATIC","Ready. Test only: no remote commands enabled.",0,18,152,383,24,h,104);
  add("STATIC","Install places the CA, Switcher files and settings for Messenger.",0,18,184,386,24,h,105);
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
 h=CreateWindowExA(0,"HermesXPMainWindow","Hermes XP - Ruiter Companion",WS_OVERLAPPEDWINDOW,80,80,426,300,NULL,NULL,g_instance,NULL);
 if(!h)ExitProcess(3);
 ShowWindow(h,5);UpdateWindow(h);
 while(GetMessageA(&msg,NULL,0,0)>0){TranslateMessage(&msg);DispatchMessageA(&msg);}
 ExitProcess(0);
}
