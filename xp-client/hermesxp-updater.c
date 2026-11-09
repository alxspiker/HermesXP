/* HermesXP XP SP3 (x86) rollback helper. No CRT, internet, paths from user,
   or third-party DLLs. Runs after the GUI receives a SHA-256-verified image.
   Saves the previous executable and restores it if the new GUI won't start. */
typedef void *HANDLE;
typedef unsigned long DWORD;
typedef unsigned short WORD;
typedef unsigned int UINT;
typedef int BOOL;
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
#define NULL ((void*)0)
#define INVALID_SOCKET ((unsigned int)~0u)
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define WAIT_OBJECT_0 0
#define MOVEFILE_REPLACE_EXISTING 1
typedef struct {
 DWORD cb;char *reserved,*desktop,*title;
 DWORD x,y,width,height,charsx,charsy,fill,flags;
 WORD show,cbReserved;unsigned char *reserved2;
 HANDLE in,out,err;
} STARTUPINFOA;
typedef struct {HANDLE process,thread;DWORD pid,tid;} PROCESS_INFORMATION;
typedef struct {short family;unsigned short port;unsigned long address;unsigned char zero[8];} SOCKADDR_IN;
IMPORT DWORD WINAPI GetModuleFileNameA(void*,char*,DWORD);
IMPORT void WINAPI ExitProcess(UINT);
IMPORT void WINAPI Sleep(DWORD);
IMPORT BOOL WINAPI MoveFileExA(const char*,const char*,DWORD);
IMPORT BOOL WINAPI DeleteFileA(const char*);
IMPORT BOOL WINAPI CreateProcessA(const char*,char*,void*,void*,BOOL,DWORD,void*,const char*,void*,void*);
IMPORT DWORD WINAPI WaitForSingleObject(HANDLE,DWORD);
IMPORT BOOL WINAPI TerminateProcess(HANDLE,UINT);
IMPORT BOOL WINAPI GetExitCodeProcess(HANDLE,DWORD*);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT int WINAPI WSAStartup(WORD,void*);
IMPORT int WINAPI WSACleanup(void);
IMPORT unsigned int WINAPI socket(int,int,int);
IMPORT int WINAPI connect(unsigned int,const void*,int);
IMPORT int WINAPI closesocket(unsigned int);
IMPORT unsigned short WINAPI htons(unsigned short);
IMPORT unsigned long WINAPI inet_addr(const char*);

static void clear(void *p,int n){unsigned char *b=(unsigned char*)p;while(n--)*b++=0;}
static int length(const char *s){int n=0;while(s[n])n++;return n;}
static void append(char *out,const char *s){int n=length(out),i=0;while(s[i] && n<490)out[n++]=s[i++];out[n]=0;}
static int paths(char *dir,char *live,char *pending,char *backup){
 int i=0,last=-1;
 if(!GetModuleFileNameA(NULL,dir,470))return 0;
 while(dir[i]){if(dir[i]=='\\')last=i;i++;}
 if(last<2 || last>415)return 0;
 dir[last+1]=0;
 live[0]=pending[0]=backup[0]=0;
 append(live,dir);append(live,"HermesXP.exe");
 append(pending,dir);append(pending,"HermesXP.next.exe");
 append(backup,dir);append(backup,"HermesXP.previous.exe");
 return 1;
}
static int launch(const char *path,PROCESS_INFORMATION *process){
 STARTUPINFOA si;clear(&si,sizeof(si));clear(process,sizeof(*process));
 si.cb=sizeof(si);return CreateProcessA(path,NULL,NULL,NULL,0,0,NULL,NULL,&si,process);
}
static int ready(void){
 unsigned char wsadata[512];SOCKADDR_IN addr;unsigned int sock;int ok;
 if(WSAStartup(0x0202,wsadata)!=0)return 0;
 sock=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(sock==INVALID_SOCKET){WSACleanup();return 0;}
 clear(&addr,sizeof(addr));addr.family=AF_INET;addr.port=htons(18768);
 addr.address=inet_addr("127.0.0.1");
 ok=connect(sock,&addr,sizeof(addr))==0;
 closesocket(sock);WSACleanup();return ok;
}
static int preflight(const char *path){
 STARTUPINFOA si;PROCESS_INFORMATION process;
 char arguments[512];int i=0,j=0;DWORD exitcode=1,done;
 const char *tail=" /update-selftest";
 if(length(path)>455)return 0;
 clear(&si,sizeof(si));clear(&process,sizeof(process));si.cb=sizeof(si);
 arguments[i++]='"';while(path[j])arguments[i++]=path[j++];
 arguments[i++]='"';j=0;while(tail[j])arguments[i++]=tail[j++];
 arguments[i]=0;
 if(!CreateProcessA(path,arguments,NULL,NULL,0,0,NULL,NULL,&si,&process))return 0;
 done=WaitForSingleObject(process.process,7000);
 if(done!=WAIT_OBJECT_0){
  TerminateProcess(process.process,1);WaitForSingleObject(process.process,2000);
 }
 if(done==WAIT_OBJECT_0 && !GetExitCodeProcess(process.process,&exitcode))
  exitcode=1;
 CloseHandle(process.thread);CloseHandle(process.process);
 return done==WAIT_OBJECT_0 && exitcode==0;
}
void WINAPI WinMainCRTStartup(void){
 char dir[512],live[512],pending[512],backup[512],failed[512];
 PROCESS_INFORMATION child;int i,swapped=0,quarantined=0;
 if(!paths(dir,live,pending,backup))ExitProcess(2);
 failed[0]=0;append(failed,dir);append(failed,"HermesXP.failed.exe");
 /* Defense in depth. Even if the GUI gets a new upload API, never replace
    the known-good executable with something that cannot initialize on XP. */
 if(!preflight(pending))ExitProcess(6);
 for(i=0;i<35;i++){
  if(MoveFileExA(live,backup,MOVEFILE_REPLACE_EXISTING)){swapped=1;break;}
  Sleep(400);
 }
 if(!swapped)ExitProcess(3);
 if(!MoveFileExA(pending,live,MOVEFILE_REPLACE_EXISTING)){
  MoveFileExA(backup,live,MOVEFILE_REPLACE_EXISTING);ExitProcess(4);
 }
 if(launch(live,&child)){
  for(i=0;i<24;i++){
   if(WaitForSingleObject(child.process,0)==WAIT_OBJECT_0)break;
   if(ready()){CloseHandle(child.thread);CloseHandle(child.process);ExitProcess(0);}
   Sleep(500);
  }
  if(WaitForSingleObject(child.process,0)!=WAIT_OBJECT_0)
   TerminateProcess(child.process,1);
  WaitForSingleObject(child.process,3000);
  CloseHandle(child.thread);CloseHandle(child.process);
 }
 /* Windows XP does not always permit MOVEFILE_REPLACE_EXISTING over a live
    EXE pathname, even after the child exits. First quarantine the failed
    image to make the destination free; then move the good backup back.
    Never delete the good backup unless restoration succeeded. */
 DeleteFileA(pending);
 for(i=0;i<30;i++){
  if(MoveFileExA(live,failed,MOVEFILE_REPLACE_EXISTING)){quarantined=1;break;}
  Sleep(500);
 }
 if(quarantined && MoveFileExA(backup,live,MOVEFILE_REPLACE_EXISTING)
    && launch(live,&child)){
  CloseHandle(child.thread);CloseHandle(child.process);
 }
 ExitProcess(5);
}
