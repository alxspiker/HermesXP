/* Authenticated, bounded LAN-only binary update receiver.
   Server accepts one client at a time; no external URLs or shell input.
   The companion verifies SHA-256 BEFORE handing off to the rollback helper.
   PROV_RSA_AES / SHA-256 are supported on fully patched Windows XP SP3. */
#define HXP_UPDATE_MAX_BYTES 524288
#define HXP_PROV_RSA_AES 24
#define HXP_VERIFY_CONTEXT 0xF0000000u
#define HXP_SHA256 0x0000800Cu
#define HXP_HP_HASHVAL 2
#define HXP_UPDATER_READY_EVENT "Local\\HermesXP.Updater.Ready"
#define HXP_UPDATER_GO_EVENT "Local\\HermesXP.Updater.Go"
#define HXP_ERROR_ALREADY_EXISTS 183

typedef struct {
 DWORD cb;char *reserved,*desktop,*title;
 DWORD x,y,width,height,charsx,charsy,fill,flags;
 WORD show,cbReserved;unsigned char *reserved2;
 HANDLE in,out,err;
} HXP_STARTUPINFO;
typedef struct {HANDLE process,thread;DWORD pid,tid;} HXP_PROCESSINFO;

static int update_ct_same(const char *a,const char *b,int n){
 unsigned int diff=0;int i;
 for(i=0;i<n;i++)diff|=(unsigned char)a[i]^(unsigned char)b[i];
 return diff==0;
}
static void update_hex(const unsigned char *bytes,char *out){
 const char *hex="0123456789abcdef";int i;
 for(i=0;i<32;i++){
  out[i*2]=hex[(bytes[i]>>4)&15];out[i*2+1]=hex[bytes[i]&15];
 }
 out[64]=0;
}
static int update_crypto_start(void **provider,void **hash){
 *provider=NULL;*hash=NULL;
 if(!CryptAcquireContextA(provider,NULL,NULL,HXP_PROV_RSA_AES,HXP_VERIFY_CONTEXT))return 0;
 if(!CryptCreateHash(*provider,HXP_SHA256,NULL,0,hash)){
  CryptReleaseContext(*provider,0);*provider=NULL;return 0;
 }
 return 1;
}
static int update_crypto_finish(void *provider,void *hash,char *hex){
 unsigned char bytes[32];DWORD size=32;
 int ok=CryptGetHashParam(hash,HXP_HP_HASHVAL,bytes,&size,0) && size==32;
 CryptDestroyHash(hash);CryptReleaseContext(provider,0);
 if(ok)update_hex(bytes,hex);
 return ok;
}
static int update_file_sha256(const char *path,char *hex){
 HANDLE file;void *provider,*hash;unsigned char chunk[2048];
 DWORD got;int ok=1;
 if(!update_crypto_start(&provider,&hash))return 0;
 file=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 if(file==(HANDLE)-1){
  CryptDestroyHash(hash);CryptReleaseContext(provider,0);return 0;
 }
 for(;;){
  if(!ReadFile(file,chunk,sizeof(chunk),&got,NULL)){ok=0;break;}
  if(got==0)break;
  if(!CryptHashData(hash,chunk,got,0)){ok=0;break;}
 }
 CloseHandle(file);
 if(!update_crypto_finish(provider,hash,hex))ok=0;
 return ok;
}
/* Reject ambiguous/malformed/multiple headers, 1MiB bombs and nonhex hashes. */
static int update_parse_headers(const char *req,int header_end,DWORD *length,char expected[65]){
 const char *p=req,*end,*stop=req+header_end;int seen_len=0,seen_hash=0;
 while(p<stop && !(p[0]=='\r' && p[1]=='\n'))p++;
 if(p>=stop)return 0;
 p+=2;*length=0;expected[0]=0;
 while(p<stop && !(p[0]=='\r' && p[1]=='\n')){
  end=p;
  while(end<stop && !(end[0]=='\r' && end[1]=='\n'))end++;
  if(end>=stop)return 0;
  if(remote_line_prefix(p,"Content-Length: ")){
   unsigned int val=0;const char *q=p+16;
   if(seen_len || q==end)return 0;
   while(q<end){
    unsigned int digit;
    if(*q<'0' || *q>'9')return 0;
    digit=(unsigned int)(*q++-'0');
    if(val>(HXP_UPDATE_MAX_BYTES-digit)/10)return 0;
    val=val*10+digit;
   }
   if(val<4096 || val>HXP_UPDATE_MAX_BYTES)return 0;
   *length=val;seen_len=1;
  }else if(remote_line_prefix(p,"X-Hermes-SHA256: ")){
   const char *q=p+17;int i;
   if(seen_hash || end-q!=64)return 0;
   for(i=0;i<64;i++){
    char v=q[i];
    if(v>='A' && v<='F')v=(char)(v-'A'+'a');
    if(!remote_hex((unsigned char)v))return 0;
    expected[i]=v;
   }
   expected[64]=0;seen_hash=1;
  }
  p=end+2;
 }
 return seen_len && seen_hash;
}
static int update_start_helper(const char *directory,HANDLE *go_signal){
 char path[512];HXP_STARTUPINFO si;HXP_PROCESSINFO proc;
 HANDLE ready,go;DWORD state;int ok=0;
 int i;unsigned char *p=(unsigned char*)&si,*q=(unsigned char*)&proc;
 *go_signal=NULL;
 ready=CreateEventA(NULL,1,0,HXP_UPDATER_READY_EVENT);
 if(!ready)return 0;
 if(GetLastError()==HXP_ERROR_ALREADY_EXISTS){CloseHandle(ready);return 0;}
 go=CreateEventA(NULL,1,0,HXP_UPDATER_GO_EVENT);
 if(!go){CloseHandle(ready);return 0;}
 if(GetLastError()==HXP_ERROR_ALREADY_EXISTS){CloseHandle(go);CloseHandle(ready);return 0;}
 for(i=0;i<(int)sizeof(si);i++)p[i]=0;
 for(i=0;i<(int)sizeof(proc);i++)q[i]=0;
 join_path(path,directory,"HermesXP-Updater.exe");
 if(GetFileAttributesA(path)==INVALID_FILE_ATTRIBUTES)goto cleanup;
 si.cb=sizeof(si);
 if(!CreateProcessA(path,NULL,NULL,NULL,0,0,NULL,NULL,&si,&proc))goto cleanup;
 state=WaitForSingleObject(ready,6000);
 ok=state==0 && WaitForSingleObject(proc.process,0)!=0;
 CloseHandle(proc.thread);CloseHandle(proc.process);
cleanup:
 CloseHandle(ready);
 if(!ok){CloseHandle(go);return 0;}
 *go_signal=go;return 1;
}
/* A candidate must prove that Windows XP can actually load and initialize
   its UI before we close the running companion. This catches invalid PE
   entry points, missing imports, damaged DLL dependencies and a broken
   window procedure without risking the running connection. */
static int update_preflight(const char *exe){
 HXP_STARTUPINFO si;HXP_PROCESSINFO proc;
 char args[512];DWORD code=1,done;int i;
 unsigned char *p=(unsigned char*)&si,*q=(unsigned char*)&proc;
 for(i=0;i<(int)sizeof(si);i++)p[i]=0;
 for(i=0;i<(int)sizeof(proc);i++)q[i]=0;
 if(strlen0(exe)>455)return 0;
 si.cb=sizeof(si);args[0]='"';i=1;
 {int j=0;while(exe[j] && i<460)args[i++]=exe[j++];}
 args[i++]='"';args[i++]=' ';
 {const char *suffix="/update-selftest";int j=0;
  while(suffix[j])args[i++]=suffix[j++];}
 args[i]=0;
 if(!CreateProcessA(exe,args,NULL,NULL,0,0,NULL,NULL,&si,&proc))return 0;
 done=WaitForSingleObject(proc.process,7000);
 if(done!=0){
  TerminateProcess(proc.process,1);
  WaitForSingleObject(proc.process,2500);
 }
 if(done==0 && !GetExitCodeProcess(proc.process,&code))code=1;
 CloseHandle(proc.thread);CloseHandle(proc.process);
 return done==0 && code==0;
}
static int handle_update_stream(unsigned int sock,char *req,int used){
 char expected[65],actual[65],dir[512],pending[512],helper[512],previous[512];
 int head=http_header_end(req,used),remaining,first,ok=1;
 int is_helper=request_is(req,"POST","/update/helper");
 HANDLE go_signal=NULL;
 unsigned char buffer[4096];DWORD length,got;HANDLE file;
 void *provider,*hash;
 if(head<=0 || !update_parse_headers(req,head,&length,expected)){
  send_http_text(sock,"400 Bad Request","invalid update manifest");return 0;
 }
 first=used-head;
 if(first<0 || (DWORD)first>length){
  send_http_text(sock,"400 Bad Request","invalid update length");return 0;
 }
 exe_dir(dir,sizeof(dir));
 join_path(pending,dir,is_helper?"HermesXP-Updater.next.exe":"HermesXP.next.exe");
 join_path(helper,dir,"HermesXP-Updater.exe");
 join_path(previous,dir,"HermesXP-Updater.previous.exe");
 if(!is_helper && GetFileAttributesA(helper)==INVALID_FILE_ATTRIBUTES){
  send_http_text(sock,"409 Conflict","XP updater helper not installed");return 0;
 }
 if(!update_crypto_start(&provider,&hash)){
  send_http_text(sock,"503 Service Unavailable","XP SHA-256 provider unavailable");return 0;
 }
 file=CreateFileA(pending,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(file==(HANDLE)-1){
  CryptDestroyHash(hash);CryptReleaseContext(provider,0);
  send_http_text(sock,"500 Internal Server Error","cannot stage update");return 0;
 }
 if(first){
  if(!WriteFile(file,req+head,first,&got,NULL) || got!=(DWORD)first ||
     !CryptHashData(hash,(unsigned char*)req+head,first,0))ok=0;
 }
 remaining=(int)length-first;
 while(ok && remaining>0){
  int n=recv(sock,(char*)buffer,remaining<(int)sizeof(buffer)?remaining:(int)sizeof(buffer),0);
  if(n<=0){ok=0;break;}
  if(!WriteFile(file,buffer,n,&got,NULL) || got!=(DWORD)n ||
     !CryptHashData(hash,buffer,n,0)){ok=0;break;}
  remaining-=n;
 }
 CloseHandle(file);
 if(!update_crypto_finish(provider,hash,actual))ok=0;
 if(ok && !update_ct_same(actual,expected,64))ok=0;
 /* A SHA match alone is insufficient if the host accidentally sent a text
    artifact; an XP PE starts with MZ and has an on-disk image header. */
 if(ok){
  unsigned char mz[2];file=CreateFileA(pending,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
  if(file==(HANDLE)-1)ok=0;
  else{
   if(!ReadFile(file,mz,2,&got,NULL) || got!=2 || mz[0]!='M' || mz[1]!='Z')ok=0;
   CloseHandle(file);
  }
 }
 if(!ok){
  DeleteFileA(pending);
  send_http_text(sock,"422 Unprocessable Entity","image hash or length mismatch");
  return 0;
 }
 if(is_helper){
  /* The rollback helper is never running during this upload. Replace it
     transactionally before the GUI update, with a previous copy retained. */
  if(GetFileAttributesA(helper)!=INVALID_FILE_ATTRIBUTES &&
     !MoveFileExA(helper,previous,1)){
   DeleteFileA(pending);
   send_http_text(sock,"409 Conflict","rollback helper is busy");
   return 0;
  }
  if(!MoveFileExA(pending,helper,1)){
   MoveFileExA(previous,helper,1);
   DeleteFileA(pending);
   send_http_text(sock,"500 Internal Server Error","cannot activate helper");
   return 0;
  }
  send_http_text(sock,"200 OK","helper updated");
  return 0;
 }
 if(!update_preflight(pending)){
  DeleteFileA(pending);
  send_http_text(sock,"422 Unprocessable Entity","candidate failed XP startup preflight");
  return 0;
 }
 /* Start the helper BEFORE acknowledging success. It cannot rename the
    running image until we close the old GUI after this response is sent. */
 if(!update_start_helper(dir,&go_signal)){
  DeleteFileA(pending);
  send_http_text(sock,"503 Service Unavailable","rollback helper failed readiness handshake");
  return 0;
 }
 if(!SetEvent(go_signal)){
  CloseHandle(go_signal);
  send_http_text(sock,"503 Service Unavailable","rollback helper could not be released");
  return 0;
 }
 CloseHandle(go_signal);
 send_http_text(sock,"200 OK","verified; restarting");
 Sleep(300);
 PostMessageA(g_main_window,WM_CLOSE,0,0);
 return 1;
}
static void handle_update_status(unsigned int sock,int is_helper){
 char path[512],dir[512],hash[65],body[95];
 int i=0,j=0;
 exe_dir(dir,sizeof(dir));join_path(path,dir,
                                  is_helper?"HermesXP-Updater.exe":"HermesXP.exe");
 if(!update_file_sha256(path,hash)){
  send_http_text(sock,"503 Service Unavailable","SHA-256 not available");return;
 }
 while(i<7)body[i]="sha256="[i],i++;
 while(j<64)body[i++]=hash[j++];
 body[i]=0;
 send_http_text(sock,"200 OK",body);
}
