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
#define EVENT_MODIFY_STATE 0x0002u
#define SYNCHRONIZE 0x00100000u
#define FILE_APPEND_DATA 4u
#define FILE_SHARE_READ 1u
#define OPEN_ALWAYS 4u
#define FILE_ATTRIBUTE_NORMAL 0x80u
#define HXP_READY_EVENT "Local\\HermesXP.Updater.Ready"
#define HXP_GO_EVENT "Local\\HermesXP.Updater.Go"
#define HXP_NEW_GUI_EVENT "Local\\HermesXP.Updated.GuiReady"
#define HXP_SINGLE_INSTANCE_MUTEX "Local\\HermesXP.Companion.SingleInstance"
#define HXP_ERROR_ALREADY_EXISTS 183
#define HXP_FIONBIO 0x8004667Eu
#define HXP_WSAEWOULDBLOCK 10035
#define HXP_WSAEINPROGRESS 10036
#define HXP_SOL_SOCKET 0xFFFF
#define HXP_SO_ERROR 0x1007
typedef struct {
 DWORD cb;char *reserved,*desktop,*title;
 DWORD x,y,width,height,charsx,charsy,fill,flags;
 WORD show,cbReserved;unsigned char *reserved2;
 HANDLE in,out,err;
} STARTUPINFOA;
typedef struct {HANDLE process,thread;DWORD pid,tid;} PROCESS_INFORMATION;
typedef struct {short family;unsigned short port;unsigned long address;unsigned char zero[8];} SOCKADDR_IN;
typedef struct {unsigned int fd_count;unsigned int fd_array[1];} HXP_FDSET;
typedef struct {long tv_sec;long tv_usec;} HXP_TIMEVAL;
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
IMPORT DWORD WINAPI GetLastError(void);
IMPORT HANDLE WINAPI OpenEventA(DWORD,BOOL,const char*);
IMPORT HANDLE WINAPI CreateEventA(void*,BOOL,BOOL,const char*);
IMPORT HANDLE WINAPI OpenMutexA(DWORD,BOOL,const char*);
IMPORT BOOL WINAPI SetEvent(HANDLE);
IMPORT HANDLE WINAPI CreateFileA(const char*,DWORD,DWORD,void*,DWORD,DWORD,HANDLE);
IMPORT BOOL WINAPI WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);
IMPORT int WINAPI WSAStartup(WORD,void*);
IMPORT int WINAPI WSACleanup(void);
IMPORT unsigned int WINAPI socket(int,int,int);
IMPORT int WINAPI connect(unsigned int,const void*,int);
IMPORT int WINAPI closesocket(unsigned int);
IMPORT unsigned short WINAPI htons(unsigned short);
IMPORT unsigned long WINAPI inet_addr(const char*);
IMPORT int WINAPI ioctlsocket(unsigned int,unsigned long,unsigned long*);
IMPORT int WINAPI select(int,void*,void*,void*,const void*);
IMPORT int WINAPI getsockopt(unsigned int,int,int,char*,int*);
IMPORT int WINAPI WSAGetLastError(void);

static void clear(void *p,int n){unsigned char *b=(unsigned char*)p;while(n--)*b++=0;}
static int length(const char *s){int n=0;while(s[n])n++;return n;}
static void append(char *out,const char *s){int n=length(out),i=0;while(s[i] && n<490)out[n++]=s[i++];out[n]=0;}
static char g_update_log[512];
static void trace(const char *stage,DWORD code){
 char line[100],digits[12];DWORD written;HANDLE file;int i=0,j=0,k=0;
 if(!g_update_log[0])return;
 file=CreateFileA(g_update_log,FILE_APPEND_DATA,FILE_SHARE_READ,NULL,
                  OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
 if(file==(HANDLE)-1)return;
 while(stage[j] && i<66)line[i++]=stage[j++];
 line[i++]=' ';
 do{digits[k++]=(char)('0'+code%10);code/=10;}while(code && k<11);
 while(k>0)line[i++]=digits[--k];
 line[i++]='\r';line[i++]='\n';
 WriteFile(file,line,(DWORD)i,&written,NULL);
 CloseHandle(file);
}
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
static int launch(const char *path,PROCESS_INFORMATION *process,int activation){
 STARTUPINFOA si;clear(&si,sizeof(si));clear(process,sizeof(*process));
 char args[512];int i=0,j=0;const char *suffix=" /update-activation";
 si.cb=sizeof(si);
 if(!activation)return CreateProcessA(path,NULL,NULL,NULL,0,0,NULL,NULL,&si,process);
 if(length(path)>455)return 0;
 args[i++]='"';while(path[j])args[i++]=path[j++];args[i++]='"';
 j=0;while(suffix[j])args[i++]=suffix[j++];
 args[i]=0;
 return CreateProcessA(path,args,NULL,NULL,0,0,NULL,NULL,&si,process);
}
static int ready(void){
 unsigned char wsadata[512];SOCKADDR_IN addr;unsigned int sock;
 unsigned long nonblocking=1;int ok=0,err=0;
 if(WSAStartup(0x0202,wsadata)!=0)return 0;
 sock=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(sock==INVALID_SOCKET){WSACleanup();return 0;}
 clear(&addr,sizeof(addr));addr.family=AF_INET;addr.port=htons(18768);
 addr.address=inet_addr("127.0.0.1");
 /* Windows XP may block a default TCP connect for tens of seconds when no
    process is listening. That defeated the health deadline and even let a
    later manual recovery be mistaken for the bad child becoming healthy.
    Always use nonblocking connect with a strictly bounded 200ms select. */
 if(ioctlsocket(sock,HXP_FIONBIO,&nonblocking)==0){
  int rc=connect(sock,&addr,sizeof(addr));
  if(rc==0)ok=1;
  else{
   err=WSAGetLastError();
   if(err==HXP_WSAEWOULDBLOCK || err==HXP_WSAEINPROGRESS){
    HXP_FDSET writable;HXP_TIMEVAL deadline;int opt_error=1,opt_length=sizeof(opt_error);
    writable.fd_count=1;writable.fd_array[0]=sock;
    deadline.tv_sec=0;deadline.tv_usec=200000;
    if(select(0,NULL,&writable,NULL,&deadline)>0 &&
       getsockopt(sock,HXP_SOL_SOCKET,HXP_SO_ERROR,
                  (char*)&opt_error,&opt_length)==0 && opt_error==0){
     ok=1;
    }
   }
  }
 }
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
 HANDLE ready_event,go_event,gui_event;
 if(!paths(dir,live,pending,backup))ExitProcess(2);
 g_update_log[0]=0;append(g_update_log,dir);append(g_update_log,"HermesXP-update.log");
 trace("helper-started",0);
 failed[0]=0;append(failed,dir);append(failed,"HermesXP.failed.exe");
 ready_event=OpenEventA(EVENT_MODIFY_STATE|SYNCHRONIZE,0,HXP_READY_EVENT);
 go_event=OpenEventA(SYNCHRONIZE,0,HXP_GO_EVENT);
 if(!ready_event || !go_event){
  trace("events-missing",GetLastError());
  if(ready_event)CloseHandle(ready_event);
  if(go_event)CloseHandle(go_event);
  ExitProcess(7);
 }
 /* Defense in depth. Even if the GUI gets a new upload API, never replace
    the known-good executable with something that cannot initialize on XP. */
 if(!preflight(pending)){
  trace("helper-preflight-failed",GetLastError());
  CloseHandle(ready_event);CloseHandle(go_event);
  ExitProcess(6);
 }
 trace("helper-preflight-passed",0);
 if(!SetEvent(ready_event)){
  trace("ready-signal-failed",GetLastError());
  CloseHandle(ready_event);CloseHandle(go_event);
  ExitProcess(8);
 }
 CloseHandle(ready_event);
 trace("waiting-for-go",0);
 if(WaitForSingleObject(go_event,8000)!=WAIT_OBJECT_0){
  trace("go-signal-timeout",0);CloseHandle(go_event);ExitProcess(9);
 }
 CloseHandle(go_event);
 trace("go-signal-received",0);
 /* Windows XP may allow renaming a running image before the old GUI has
    released its named single-instance mutex. Launching immediately would
    cause the replacement to exit cleanly as a duplicate. Wait for the OLD
    process to release its handle before touching either executable. */
 for(i=0;i<40;i++){
  HANDLE old_mutex=OpenMutexA(SYNCHRONIZE,0,HXP_SINGLE_INSTANCE_MUTEX);
  if(!old_mutex)break;
  CloseHandle(old_mutex);
  Sleep(250);
 }
 if(i==40){trace("old-gui-still-running",0);ExitProcess(12);}
 trace("old-gui-exited",0);
 gui_event=CreateEventA(NULL,1,0,HXP_NEW_GUI_EVENT);
 if(!gui_event){trace("gui-ready-event-create-failed",GetLastError());ExitProcess(10);}
 if(GetLastError()==HXP_ERROR_ALREADY_EXISTS){
  trace("gui-ready-event-already-exists",0);
  CloseHandle(gui_event);
  ExitProcess(11);
 }
 for(i=0;i<35;i++){
  if(MoveFileExA(live,backup,MOVEFILE_REPLACE_EXISTING)){swapped=1;break;}
  Sleep(400);
 }
 if(!swapped){
  trace("backup-rename-failed",GetLastError());
  CloseHandle(gui_event);ExitProcess(3);
 }
 trace("previous-saved",0);
 if(!MoveFileExA(pending,live,MOVEFILE_REPLACE_EXISTING)){
  trace("staged-activate-failed",GetLastError());
  MoveFileExA(backup,live,MOVEFILE_REPLACE_EXISTING);
  CloseHandle(gui_event);ExitProcess(4);
 }
 trace("new-image-activated",0);
 if(launch(live,&child,1)){
  trace("new-process-started",0);
  for(i=0;i<40;i++){
   if(WaitForSingleObject(child.process,0)==WAIT_OBJECT_0)break;
   if(WaitForSingleObject(gui_event,500)==WAIT_OBJECT_0){
    /* Require the specific newly-launched process to remain alive after
       signalling its own listener. A stale port alone is not success. */
    Sleep(1500);
    if(WaitForSingleObject(child.process,0)!=WAIT_OBJECT_0 && ready()){
     trace("new-process-signalled-listener-and-stayed-alive",0);
     CloseHandle(gui_event);
     CloseHandle(child.thread);CloseHandle(child.process);ExitProcess(0);
    }
    break;
   }
  }
  trace("new-process-failed-health",0);
  if(WaitForSingleObject(child.process,0)!=WAIT_OBJECT_0)
   TerminateProcess(child.process,1);
  WaitForSingleObject(child.process,3000);
  CloseHandle(child.thread);CloseHandle(child.process);
 }
 CloseHandle(gui_event);
 /* Windows XP does not always permit MOVEFILE_REPLACE_EXISTING over a live
    EXE pathname, even after the child exits. First quarantine the failed
    image to make the destination free; then move the good backup back.
    Never delete the good backup unless restoration succeeded. */
 DeleteFileA(pending);
 for(i=0;i<30;i++){
  if(MoveFileExA(live,failed,MOVEFILE_REPLACE_EXISTING)){quarantined=1;break;}
  Sleep(500);
 }
 if(!quarantined)trace("failed-image-quarantine-failed",GetLastError());
 else{
  trace("failed-image-quarantined",0);
  for(i=0;i<30;i++){
   if(MoveFileExA(backup,live,MOVEFILE_REPLACE_EXISTING)){
    trace("previous-image-restored",0);
    if(launch(live,&child,0)){
     trace("previous-process-restarted",0);
     CloseHandle(child.thread);CloseHandle(child.process);
    }else trace("previous-process-launch-failed",GetLastError());
    break;
   }
   Sleep(500);
  }
  if(i==30)trace("previous-restore-failed",GetLastError());
 }
 ExitProcess(5);
}
