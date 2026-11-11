/*
 * HermesXP XP SP3 x86 background health service.
 *
 * Does not own the interactive desktop, execute remote commands, accept
 * inbound network requests, or carry model credentials. The desktop
 * companion starts at user logon through the installer's optional HKLM Run
 * entry and holds the existing authenticated 18768 listener.
 *
 * The service monitors that listener and logs state transitions to the
 * Windows Application event log. It runs under NT AUTHORITY\LocalService,
 * not LocalSystem, so CUA never gains service privileges.
 */
typedef void *HANDLE;
typedef unsigned long DWORD;
typedef unsigned short WORD;
typedef unsigned int UINT;
typedef int BOOL;
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
#define NULL ((void*)0)

#define SERVICE_WIN32_OWN_PROCESS 0x10u
#define SERVICE_AUTO_START 2u
#define SERVICE_ERROR_NORMAL 1u
#define SERVICE_STOPPED 1u
#define SERVICE_START_PENDING 2u
#define SERVICE_STOP_PENDING 3u
#define SERVICE_RUNNING 4u
#define SERVICE_ACCEPT_STOP 1u
#define SERVICE_CONTROL_STOP 1u
#define SC_MANAGER_CONNECT 1u
#define SC_MANAGER_CREATE_SERVICE 2u
#define SERVICE_QUERY_STATUS 4u
#define SERVICE_START 0x10u
#define SERVICE_STOP 0x20u
#define SERVICE_CHANGE_CONFIG 2u
#define DELETE_ACCESS 0x10000u
#define SERVICE_NO_CHANGE 0xFFFFFFFFu
#define WAIT_OBJECT_0 0u
#define ERROR_SERVICE_EXISTS 1073u
#define ERROR_SERVICE_ALREADY_RUNNING 1056u
#define AF_INET 2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define INVALID_SOCKET (~0u)
#define HXP_FIONBIO 0x8004667Eu
#define HXP_WSAEWOULDBLOCK 10035
#define HXP_WSAEINPROGRESS 10036
#define HXP_SOL_SOCKET 0xFFFF
#define HXP_SO_ERROR 0x1007
#define EVENTLOG_INFORMATION_TYPE 4
#define EVENTLOG_WARNING_TYPE 2

typedef struct {
 DWORD dwServiceType, dwCurrentState, dwControlsAccepted;
 DWORD dwWin32ExitCode, dwServiceSpecificExitCode, dwCheckPoint, dwWaitHint;
} SERVICE_STATUS;
typedef void (WINAPI *SERVICE_MAIN)(DWORD,char**);
typedef struct { char *name; SERVICE_MAIN proc; } SERVICE_TABLE_ENTRYA;
typedef struct {short family; WORD port; DWORD address; char padding[8];} SOCKADDR_IN;
typedef struct {UINT count; UINT sockets[1];} HXP_FDSET;
typedef struct {long seconds;long microseconds;} HXP_TIMEVAL;

IMPORT DWORD WINAPI GetModuleFileNameA(void*,char*,DWORD);
IMPORT char* WINAPI GetCommandLineA(void);
IMPORT DWORD WINAPI GetLastError(void);
IMPORT void WINAPI ExitProcess(UINT);
IMPORT HANDLE WINAPI CreateEventA(void*,BOOL,BOOL,const char*);
IMPORT BOOL WINAPI SetEvent(HANDLE);
IMPORT DWORD WINAPI WaitForSingleObject(HANDLE,DWORD);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT void* WINAPI OpenSCManagerA(const char*,const char*,DWORD);
IMPORT void* WINAPI CreateServiceA(void*,const char*,const char*,DWORD,DWORD,DWORD,DWORD,const char*,const char*,DWORD*,const char*,const char*,const char*);
IMPORT void* WINAPI OpenServiceA(void*,const char*,DWORD);
IMPORT BOOL WINAPI ChangeServiceConfigA(void*,DWORD,DWORD,DWORD,const char*,const char*,DWORD*,const char*,const char*,const char*,const char*);
IMPORT BOOL WINAPI DeleteService(void*);
IMPORT BOOL WINAPI ControlService(void*,DWORD,SERVICE_STATUS*);
IMPORT BOOL WINAPI QueryServiceStatus(void*,SERVICE_STATUS*);
IMPORT BOOL WINAPI StartServiceA(void*,DWORD,const char**);
IMPORT BOOL WINAPI CloseServiceHandle(void*);
IMPORT BOOL WINAPI StartServiceCtrlDispatcherA(SERVICE_TABLE_ENTRYA*);
IMPORT void* WINAPI RegisterServiceCtrlHandlerA(const char*,void (WINAPI*)(DWORD));
IMPORT BOOL WINAPI SetServiceStatus(void*,SERVICE_STATUS*);
IMPORT HANDLE WINAPI RegisterEventSourceA(const char*,const char*);
IMPORT BOOL WINAPI ReportEventA(HANDLE,WORD,WORD,DWORD,void*,WORD,DWORD,const char**,void*);
IMPORT BOOL WINAPI DeregisterEventSource(HANDLE);
IMPORT int WINAPI WSAStartup(WORD,void*);
IMPORT int WINAPI WSACleanup(void);
IMPORT UINT WINAPI socket(int,int,int);
IMPORT int WINAPI closesocket(UINT);
IMPORT int WINAPI connect(UINT,const void*,int);
IMPORT int WINAPI ioctlsocket(UINT,DWORD,DWORD*);
IMPORT int WINAPI select(int,void*,void*,void*,const void*);
IMPORT int WINAPI getsockopt(UINT,int,int,char*,int*);
IMPORT int WINAPI WSAGetLastError(void);
IMPORT WORD WINAPI htons(WORD);
IMPORT DWORD WINAPI inet_addr(const char*);

static const char SERVICE_NAME[]="HermesXPService";
static void *g_handler=NULL;
static HANDLE g_stop=NULL;
static SERVICE_STATUS g_status;

static void clear(void *ptr,UINT size){
 char *p=(char*)ptr;while(size--)*p++=0;
}
static int length(const char *s){int i=0;while(s[i])i++;return i;}
static int equals(const char *a,const char *b){int i=0;while(a[i]&&a[i]==b[i])i++;return !a[i]&&!b[i];}
static void append(char *out,const char *src){
 int at=length(out),i=0;
 while(src[i]&&at<495)out[at++]=src[i++];
 out[at]=0;
}
static const char *argument(void){
 const char *c=GetCommandLineA();
 if(*c=='"'){c++;while(*c&&*c!='"')c++;if(*c)c++;}
 else while(*c&&*c!=' '&&*c!='\t')c++;
 while(*c==' '||*c=='\t')c++;
 return c;
}
static void log_transition(const char *message,int warning){
 HANDLE log=RegisterEventSourceA(NULL,SERVICE_NAME);
 const char *strings[1];
 if(!log)return;
 strings[0]=message;
 ReportEventA(log,warning?EVENTLOG_WARNING_TYPE:EVENTLOG_INFORMATION_TYPE,
              0,warning?2:1,NULL,1,0,strings,NULL);
 DeregisterEventSource(log);
}
/* Never binds to XP's LAN or accepts requests; a bounded loopback check only. */
static int companion_listening(void){
 unsigned char wsadata[512];
 SOCKADDR_IN address;
 HXP_FDSET writable;
 HXP_TIMEVAL wait;
 UINT fd;
 DWORD nonblock=1;
 int ok=0,error=1,error_length=sizeof(error),state;
 if(WSAStartup(0x0202,wsadata)!=0)return 0;
 fd=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(fd==INVALID_SOCKET){WSACleanup();return 0;}
 clear(&address,sizeof(address));
 address.family=AF_INET;
 address.port=htons(18768);
 address.address=inet_addr("127.0.0.1");
 if(ioctlsocket(fd,HXP_FIONBIO,&nonblock)==0){
  state=connect(fd,&address,sizeof(address));
  if(state==0)ok=1;
  else if((state=WSAGetLastError())==HXP_WSAEWOULDBLOCK ||
          state==HXP_WSAEINPROGRESS){
   /* select and SO_ERROR enforce a bounded 300ms monitor deadline. */
   writable.count=1;writable.sockets[0]=fd;
   wait.seconds=0;wait.microseconds=300000;
   if(select(0,NULL,&writable,NULL,&wait)>0 &&
      getsockopt(fd,HXP_SOL_SOCKET,HXP_SO_ERROR,(char*)&error,&error_length)==0 &&
      error==0)ok=1;
  }
 }
 closesocket(fd);
 WSACleanup();
 return ok;
}
static void status(DWORD state,DWORD wait_hint){
 g_status.dwCurrentState=state;
 g_status.dwControlsAccepted=(state==SERVICE_RUNNING)?SERVICE_ACCEPT_STOP:0;
 g_status.dwWaitHint=wait_hint;
 if(g_handler)SetServiceStatus(g_handler,&g_status);
}
static void WINAPI control(DWORD code){
 if(code==SERVICE_CONTROL_STOP){
  status(SERVICE_STOP_PENDING,3000);
  if(g_stop)SetEvent(g_stop);
 }
}
static void WINAPI service_main(DWORD argc,char **argv){
 int seen_online=0,previous=-1;
 (void)argc;(void)argv;
 clear(&g_status,sizeof(g_status));
 g_status.dwServiceType=SERVICE_WIN32_OWN_PROCESS;
 g_handler=RegisterServiceCtrlHandlerA(SERVICE_NAME,control);
 if(!g_handler)return;
 status(SERVICE_START_PENDING,3000);
 g_stop=CreateEventA(NULL,1,0,NULL);
 if(!g_stop){g_status.dwWin32ExitCode=GetLastError();status(SERVICE_STOPPED,0);return;}
 status(SERVICE_RUNNING,0);
 for(;;){
  int online=companion_listening();
  if(online!=previous){
   if(online){seen_online=1;log_transition("HermesXP desktop companion is listening locally",0);}
   else if(seen_online)log_transition("HermesXP desktop companion is unavailable; it starts at user sign-in",1);
   previous=online;
  }
  if(WaitForSingleObject(g_stop,15000)==WAIT_OBJECT_0)break;
 }
 CloseHandle(g_stop);g_stop=NULL;
 status(SERVICE_STOPPED,0);
}
static UINT register_service(int remove){
 void *scm,*service;
 char path[512],command[512];UINT result=0;
 SERVICE_STATUS current;
 scm=OpenSCManagerA(NULL,NULL,SC_MANAGER_CONNECT|SC_MANAGER_CREATE_SERVICE);
 if(!scm)return 10;
 service=OpenServiceA(scm,SERVICE_NAME,DELETE_ACCESS|SERVICE_STOP|SERVICE_QUERY_STATUS|
                       SERVICE_START|SERVICE_CHANGE_CONFIG);
 if(remove){
  if(service){
   if(QueryServiceStatus(service,&current)&&current.dwCurrentState!=SERVICE_STOPPED){
    int attempts;
    ControlService(service,SERVICE_CONTROL_STOP,&current);
    for(attempts=0;attempts<30;attempts++){
     if(QueryServiceStatus(service,&current)&&current.dwCurrentState==SERVICE_STOPPED)break;
     /* Event wait isn't available in CLI mode; use Sleep on kernel32. */
     { HANDLE pause=CreateEventA(NULL,0,0,NULL);
       if(pause){WaitForSingleObject(pause,200);CloseHandle(pause);} }
    }
   }
   if(!DeleteService(service))result=12;
  }
 }else{
  int path_length,i;
  if(!GetModuleFileNameA(NULL,path,440))result=13;
  else{
   path_length=length(path);clear(command,sizeof(command));
   command[0]='"';i=0;
   while(i<path_length){command[i+1]=path[i];i++;}
   command[i+1]='"';command[i+2]=0;
   append(command," /service");
   if(service){
    if(!ChangeServiceConfigA(service,SERVICE_NO_CHANGE,SERVICE_AUTO_START,
                              SERVICE_NO_CHANGE,command,NULL,NULL,NULL,
                              "NT AUTHORITY\\LocalService",NULL,
                              "HermesXP background health monitor"))result=14;
   }else{
    service=CreateServiceA(scm,SERVICE_NAME,"HermesXP background health monitor",
      SERVICE_START|SERVICE_QUERY_STATUS|SERVICE_STOP|DELETE_ACCESS|SERVICE_CHANGE_CONFIG,
      SERVICE_WIN32_OWN_PROCESS,SERVICE_AUTO_START,SERVICE_ERROR_NORMAL,
      command,NULL,NULL,NULL,"NT AUTHORITY\\LocalService",NULL);
    if(!service)result=15;
   }
   if(!result&&!StartServiceA(service,0,NULL)&&GetLastError()!=ERROR_SERVICE_ALREADY_RUNNING)
    result=16;
  }
 }
 if(service)CloseServiceHandle(service);
 CloseServiceHandle(scm);
 return result;
}
void WINAPI WinMainCRTStartup(void){
 const char *cmd=argument();
 SERVICE_TABLE_ENTRYA entries[2];
 if(equals(cmd,"/install"))ExitProcess(register_service(0));
 if(equals(cmd,"/remove"))ExitProcess(register_service(1));
 if(!equals(cmd,"/service"))ExitProcess(2);
 entries[0].name=(char*)SERVICE_NAME;entries[0].proc=service_main;
 entries[1].name=NULL;entries[1].proc=NULL;
 ExitProcess(StartServiceCtrlDispatcherA(entries)?0:3);
}
