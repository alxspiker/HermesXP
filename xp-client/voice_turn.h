/* XP SP3 WinMM speech turns for HermesXP's separate companion voice path.
   Deliberately NOT native Windows Live Messenger SIP/RTP. The Messenger
   text channel remains untouched. No C runtime, WMI, or third-party DLL. */
#define WAVE_FORMAT_PCM 1
#define WAVE_MAPPER 0xFFFFFFFFu
#define WHDR_DONE 1
#define VOICE_INPUT_BYTES (16000*2*5)
#define VOICE_OUTPUT_BYTES (16000*2*45)
#define VOICE_PORT 18770
typedef struct { WORD wFormatTag,nChannels; DWORD nSamplesPerSec,nAvgBytesPerSec;
                 WORD nBlockAlign,wBitsPerSample,cbSize; } WAVEFORMATEX_XP;
typedef struct { char *lpData; DWORD dwBufferLength,dwBytesRecorded,dwUser,dwFlags,dwLoops;
                 void *lpNext; DWORD reserved; } WAVEHDR_XP;
IMPORT UINT WINAPI waveInOpen(void **,UINT,const WAVEFORMATEX_XP *,DWORD,DWORD,DWORD);
IMPORT UINT WINAPI waveInPrepareHeader(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveInAddBuffer(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveInStart(void *);
IMPORT UINT WINAPI waveInStop(void *);
IMPORT UINT WINAPI waveInReset(void *);
IMPORT UINT WINAPI waveInUnprepareHeader(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveInClose(void *);
IMPORT UINT WINAPI waveOutOpen(void **,UINT,const WAVEFORMATEX_XP *,DWORD,DWORD,DWORD);
IMPORT UINT WINAPI waveOutPrepareHeader(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveOutWrite(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveOutReset(void *);
IMPORT UINT WINAPI waveOutUnprepareHeader(void *,WAVEHDR_XP *,UINT);
IMPORT UINT WINAPI waveOutClose(void *);

static volatile LONG g_voice_running=0;
static HWND g_voice_button=NULL;
static WAVEFORMATEX_XP voice_format(void){
 WAVEFORMATEX_XP fmt;
 fmt.wFormatTag=WAVE_FORMAT_PCM;fmt.nChannels=1;fmt.nSamplesPerSec=16000;
 fmt.nAvgBytesPerSec=32000;fmt.nBlockAlign=2;fmt.wBitsPerSample=16;fmt.cbSize=0;
 return fmt;
}
/* Header construction is bounded; no untrusted user string or token may
   extend beyond a preallocated 512-byte request header. */
static int voice_append(char *out,int *index,int max,const char *value){
 while(*value){
  if(*index>=max-1)return 0;
  out[(*index)++]=*value++;
 }
 out[*index]=0;
 return 1;
}
static int voice_http(const char *host,const char *token,const char *method,
                      const char *path,const char *body,int body_size,
                      char *out,int cap,int *out_size){
 char wsa[512],header[512],num[12];int pos=0,k=0,n=0,total=0,header_end=-1,status=0;
 unsigned int sock=INVALID_SOCKET;SOCKADDR_IN addr;DWORD timeout=8000;
 if(WSAStartup(0x0202,wsa)!=0)return 0;
 sock=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
 if(sock==INVALID_SOCKET)goto done;
 addr.sin_family=AF_INET;addr.sin_port=htons(VOICE_PORT);addr.sin_addr=inet_addr(host);
 for(k=0;k<8;k++)addr.sin_zero[k]=0;
 if(addr.sin_addr==0xFFFFFFFFUL || connect(sock,&addr,sizeof(addr))!=0)goto done;
 setsockopt(sock,SOL_SOCKET,SO_RCVTIMEO,(char*)&timeout,sizeof(timeout));
 setsockopt(sock,SOL_SOCKET,SO_SNDTIMEO,(char*)&timeout,sizeof(timeout));
 header[0]=0;
 if(!voice_append(header,&pos,sizeof(header),method) ||
    !voice_append(header,&pos,sizeof(header)," ") ||
    !voice_append(header,&pos,sizeof(header),path) ||
    !voice_append(header,&pos,sizeof(header)," HTTP/1.0\r\nHost: ") ||
    !voice_append(header,&pos,sizeof(header),host) ||
    !voice_append(header,&pos,sizeof(header),"\r\nX-Hermes-Token: ") ||
    !voice_append(header,&pos,sizeof(header),token) ||
    !voice_append(header,&pos,sizeof(header),
       "\r\nContent-Type: application/octet-stream\r\nContent-Length: "))goto done;
 {unsigned int value=(unsigned int)body_size;int reverse=0;
  do{num[reverse++]=(char)('0'+value%10);value/=10;}while(value && reverse<11);
  while(reverse>0){char part[2];part[0]=num[--reverse];part[1]=0;
   if(!voice_append(header,&pos,sizeof(header),part))goto done;}}
 if(!voice_append(header,&pos,sizeof(header),"\r\nConnection: close\r\n\r\n"))goto done;
 if(!send_all(sock,header,pos))goto done;
 if(body_size>0 && !send_all(sock,body,body_size))goto done;
 while(total<cap){
  n=recv(sock,out+total,cap-total,0);
  if(n<0)goto done;
  if(n==0)break;
  total+=n;
 }
 if(total<12 || n>0 || out[0]!='H' || out[1]!='T' || out[2]!='T' || out[3]!='P')
  goto done;
 status=(out[9]-'0')*100+(out[10]-'0')*10+out[11]-'0';
 for(k=0;k+3<total && k<2048;k++){
  if(out[k]=='\r'&&out[k+1]=='\n'&&out[k+2]=='\r'&&out[k+3]=='\n'){
   header_end=k+4;break;
  }
 }
 if(header_end<0)goto done;
 *out_size=total-header_end;
 for(k=0;k<*out_size;k++)out[k]=out[header_end+k];
done:
 if(sock!=INVALID_SOCKET)closesocket(sock);
 WSACleanup();
 return status;
}
static int voice_record(char *out,int cap,int *size){
 WAVEFORMATEX_XP fmt=voice_format();WAVEHDR_XP hdr;void *device=NULL;
 int elapsed=0,success=0;
 if(cap<VOICE_INPUT_BYTES)return 0;
 if(waveInOpen(&device,WAVE_MAPPER,&fmt,0,0,0)!=0)return 0;
 hdr.lpData=out;hdr.dwBufferLength=VOICE_INPUT_BYTES;hdr.dwBytesRecorded=0;
 hdr.dwUser=0;hdr.dwFlags=0;hdr.dwLoops=0;hdr.lpNext=NULL;hdr.reserved=0;
 if(waveInPrepareHeader(device,&hdr,sizeof(hdr))==0){
  if(waveInAddBuffer(device,&hdr,sizeof(hdr))==0 && waveInStart(device)==0){
   while(elapsed<5600 && !(hdr.dwFlags&WHDR_DONE) && !g_voice_cancel){
    Sleep(40);elapsed+=40;
   }
   waveInStop(device);waveInReset(device);
   *size=(int)(hdr.dwBytesRecorded&~1u);
   success=(*size>=3200 && *size<=VOICE_INPUT_BYTES && !g_voice_cancel);
  }
  waveInUnprepareHeader(device,&hdr,sizeof(hdr));
 }
 waveInClose(device);
 return success;
}
static int voice_play(char *pcm,int size){
 WAVEFORMATEX_XP fmt=voice_format();WAVEHDR_XP hdr;void *device=NULL;
 int elapsed=0,ok=0;
 if(size<2 || size>VOICE_OUTPUT_BYTES || size%2)return 0;
 if(waveOutOpen(&device,WAVE_MAPPER,&fmt,0,0,0)!=0)return 0;
 hdr.lpData=pcm;hdr.dwBufferLength=(DWORD)size;hdr.dwBytesRecorded=0;
 hdr.dwUser=0;hdr.dwFlags=0;hdr.dwLoops=0;hdr.lpNext=NULL;hdr.reserved=0;
 if(waveOutPrepareHeader(device,&hdr,sizeof(hdr))==0){
  if(waveOutWrite(device,&hdr,sizeof(hdr))==0){
   while(!(hdr.dwFlags&WHDR_DONE) && elapsed<47000 && !g_voice_cancel){
    Sleep(40);elapsed+=40;
   }
   ok=(hdr.dwFlags&WHDR_DONE)!=0 && !g_voice_cancel;
  }
  waveOutReset(device);
  waveOutUnprepareHeader(device,&hdr,sizeof(hdr));
 }
 waveOutClose(device);
 return ok;
}
static DWORD WINAPI voice_worker(void *ignored){
 char host[64],id[28],path[64],*input=NULL,*reply=NULL;int n=0,size=0,code,tries=0,i;
 (void)ignored;
 host[0]=0;GetWindowTextA(g_host,host,sizeof(host));
 if(!g_remote_token[0] || !g_remote_allowed_ip[0] ||
    !remote_string_equal(host,g_remote_allowed_ip)){
  update_status("Voice locked: pair XP and match the Hermes host IP.");
  goto cleanup;
 }
 input=(char*)HeapAlloc(GetProcessHeap(),0,VOICE_INPUT_BYTES);
 reply=(char*)HeapAlloc(GetProcessHeap(),0,VOICE_OUTPUT_BYTES+4096);
 if(!input || !reply){update_status("Voice: out of memory.");goto cleanup;}
 update_status("Voice: recording microphone (5 seconds)...");
 if(!voice_record(input,VOICE_INPUT_BYTES,&size)){
  if(!g_voice_cancel)update_status("Voice: microphone unavailable or no audio.");
  goto cleanup;
 }
 update_status("Voice: sending speech to Hermes...");
 code=voice_http(host,g_remote_token,"POST","/voice/turn",input,size,
                 reply,VOICE_OUTPUT_BYTES+4096,&n);
 if(code!=202 || n!=24){update_status("Voice gateway unavailable or busy.");goto cleanup;}
 for(i=0;i<24;i++){
  char c=reply[i];
  if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))){
   update_status("Voice gateway returned an invalid turn.");goto cleanup;
  }
  id[i]=c;
 }
 id[24]=0;
 {int p=0;path[0]=0;
  voice_append(path,&p,sizeof(path),"/voice/turn/");
  voice_append(path,&p,sizeof(path),id);
 }
 update_status("Voice: Hermes is thinking...");
 while(tries++<250 && !g_voice_cancel){
  Sleep(2000);
  code=voice_http(host,g_remote_token,"GET",path,NULL,0,
                  reply,VOICE_OUTPUT_BYTES+4096,&n);
  if(code==202)continue;
  if(code==200){
   update_status("Voice: playing Hermes reply...");
   if(!voice_play(reply,n) && !g_voice_cancel)
    update_status("Voice: speakers unavailable.");
   else if(!g_voice_cancel)
    update_status("Voice: ready; click Talk to speak again.");
   goto cleanup;
  }
  update_status("Voice: agent or server failed.");goto cleanup;
 }
 if(!g_voice_cancel)update_status("Voice: response timed out.");
cleanup:
 if(input)HeapFree(GetProcessHeap(),0,input);
 if(reply)HeapFree(GetProcessHeap(),0,reply);
 if(g_voice_cancel)update_status("Voice: stopped.");
 g_voice_running=0;g_voice_cancel=0;
 if(g_voice_button)SetWindowTextA(g_voice_button,"Talk to Hermes (5s)");
 return 0;
}
static void voice_toggle(void){
 DWORD thread_id=0;HANDLE thread;
 if(g_voice_running){g_voice_cancel=1;update_status("Voice: stopping...");return;}
 g_voice_running=1;g_voice_cancel=0;
 if(g_voice_button)SetWindowTextA(g_voice_button,"Stop voice");
 thread=CreateThread(NULL,0,voice_worker,NULL,0,&thread_id);
 if(thread)CloseHandle(thread);
 else{
  g_voice_running=0;
  if(g_voice_button)SetWindowTextA(g_voice_button,"Talk to Hermes (5s)");
  update_status("Voice: unable to start audio thread.");
 }
}
