#ifndef HERMESXP_LAN_DISCOVERY_H
#define HERMESXP_LAN_DISCOVERY_H

/* Authenticated IP-change recovery for any paired HermesXP client.
   Works on XP SP3's standard Winsock and CryptoAPI, no CRT, no WMI,
   no username/password, no external DNS and no shell commands.
   All packets are HMAC-SHA256 authenticated with the existing pairing key.
   The key is NEVER broadcast. A nonce and server response are validated
   before any local configuration can be changed.
*/
#define HXP_LAN_DISCOVERY_PORT 18773
#define HXP_CALG_SHA256 0x0000800Cu
#define HXP_PROV_RSA_AES 24
#define HXP_HP_HASHVAL 2
#define HXP_DISCOVERY_INTERVAL_MS 8000
static volatile DWORD hxp_discovery_status=0;
static volatile DWORD hxp_discovery_verified=0;
static volatile DWORD hxp_discovery_windows_error=0;

static void hxp_hex(const unsigned char *src,int size,char *dst) {
 const char *hex="0123456789abcdef";
 int i;
 for(i=0;i<size;i++){dst[2*i]=hex[src[i]>>4];dst[2*i+1]=hex[src[i]&15];}
 dst[size*2]=0;
}
static int hxp_unhex(const char *src,unsigned char *dst,int size) {
 int i;
 for(i=0;i<size;i++){
  int hi=-1,lo=-1; unsigned char h=(unsigned char)src[i*2], l=(unsigned char)src[i*2+1];
  if(h>='0'&&h<='9')hi=h-'0';
  else if(h>='a'&&h<='f')hi=h-'a'+10;
  if(l>='0'&&l<='9')lo=l-'0';
  else if(l>='a'&&l<='f')lo=l-'a'+10;
  if(hi<0||lo<0)return 0;
  dst[i]=(unsigned char)((hi<<4)|lo);
 }
 return 1;
}
static int hxp_sha256(void *provider,const unsigned char *data,DWORD size,
                      unsigned char result[32]){
 void *hash=NULL;DWORD length=32;int ok=0;
 if(CryptCreateHash(provider,HXP_CALG_SHA256,NULL,0,&hash)){
  ok=CryptHashData(hash,data,size,0)&&
     CryptGetHashParam(hash,HXP_HP_HASHVAL,result,&length,0)&&length==32;
  CryptDestroyHash(hash);
 }
 return ok;
}
static int hxp_hmac(void *provider,const unsigned char key[32],
                    const char *message,char result[65]){
 unsigned char inner[32],outer[32],ipad[64],opad[64];void *hash=NULL;
 DWORD length=32; int i,ok=0;
 for(i=0;i<64;i++){
  unsigned char secret=i<32?key[i]:0;
  ipad[i]=(unsigned char)(secret^0x36);
  opad[i]=(unsigned char)(secret^0x5c);
 }
 if(!CryptCreateHash(provider,HXP_CALG_SHA256,NULL,0,&hash))return 0;
 ok=CryptHashData(hash,ipad,64,0)&&
    CryptHashData(hash,(const BYTE*)message,(DWORD)strlen0(message),0)&&
    CryptGetHashParam(hash,HXP_HP_HASHVAL,inner,&length,0)&&length==32;
 CryptDestroyHash(hash);hash=NULL;
 if(!ok||!CryptCreateHash(provider,HXP_CALG_SHA256,NULL,0,&hash))return 0;
 length=32;
 ok=CryptHashData(hash,opad,64,0)&&
    CryptHashData(hash,inner,32,0)&&
    CryptGetHashParam(hash,HXP_HP_HASHVAL,outer,&length,0)&&length==32;
 CryptDestroyHash(hash);
 if(ok)hxp_hex(outer,32,result);
 return ok;
}
static int hxp_append(char *out,int at,int max,const char *string){
 int i=0;
 while(string[i] && at<max-1)out[at++]=string[i++];
 out[at]=0;
 return at;
}
/* Extract exactly five or six whitespace-separated ASCII fields. Reject
   extra separators, overlength strings and NULs injected into UDP payloads. */
static int hxp_fields(char *packet,int length,char *fields[],int cap){
 int i,n=0;
 if(length<1||length>190)return 0;
 for(i=0;i<length;i++){
  unsigned char c=(unsigned char)packet[i];
  if(c==0||c>126||c<32)return 0;
 }
 packet[length]=0;
 fields[n++]=packet;
 for(i=0;i<length;i++){
  if(packet[i]==' '){
   if(i==0||i+1==length||packet[i+1]==' '||n>=cap)return 0;
   packet[i]=0;fields[n++]=packet+i+1;
  }
 }
 return n;
}
/* Update only the Hermes-managed MSN hostname entries. Keep other XP hosts
   entries byte-for-byte, and do not append duplicate stale mappings. */
static int hxp_update_hosts(const char *server_ip) {
 char windir[260],path[310],existing[8192],updated[8192],line[280];
 DWORD length=0,write_len=0;int pos=0,i=0;
 HANDLE file;
 if(!GetWindowsDirectoryA(windir,sizeof(windir)))return 0;
 pos=hxp_append(path,0,sizeof(path),windir);
 hxp_append(path,pos,sizeof(path),"\\system32\\drivers\\etc\\hosts");
 if(!read_file(path,existing,sizeof(existing)-1,&length))return 0;
 existing[length]=0;
 pos=0;
 while(i<(int)length){
  int start=i,end;
  while(i<(int)length && existing[i]!='\r' && existing[i]!='\n')i++;
  end=i;
  while(i<(int)length && (existing[i]=='\r'||existing[i]=='\n'))i++;
  if(end-start<270){
   int n=0,k=start;
   while(k<end)line[n++]=existing[k++];
   line[n]=0;
   if(str_find(line,"msn.local") || str_find(line,"g.msn.com"))continue;
  }
  if(pos+i-start>=7900)return 0;
  for(int k=start;k<i;k++)updated[pos++]=existing[k];
 }
 if(pos && updated[pos-1]!='\n'){updated[pos++]='\r';updated[pos++]='\n';}
 pos=hxp_append(updated,pos,sizeof(updated),server_ip);
 pos=hxp_append(updated,pos,sizeof(updated)," msn.local\r\n");
 pos=hxp_append(updated,pos,sizeof(updated),server_ip);
 pos=hxp_append(updated,pos,sizeof(updated)," g.msn.com\r\n");
 file=CreateFileA(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(file==(HANDLE)-1)return 0;
 {BOOL ok=WriteFile(file,updated,(DWORD)pos,&write_len,NULL);
  CloseHandle(file);return ok&&write_len==(DWORD)pos;}
}
static void hxp_apply_verified_host(const char *host) {
 char dir[512],ini[512],old[32],msn[512];int changed;
 exe_dir(dir,sizeof(dir));join_path(ini,dir,"hermesxp.ini");
 GetPrivateProfileStringA("Hermes","ServerIP","",old,sizeof(old),ini);
 changed=!str_eq(old,host);
 if(!changed && str_eq(g_remote_allowed_ip,host))return;
 /* Durable update for all follow-on restarts, with the paired-token check
    already completed by the discovery worker. */
 if(!WritePrivateProfileStringA("Remote","AllowedHostIP",host,ini))return;
 if(!WritePrivateProfileStringA("Hermes","ServerIP",host,ini))return;
 {int i=0;while(host[i]&&i<15){g_remote_allowed_ip[i]=host[i];i++;}g_remote_allowed_ip[i]=0;}
 if(!changed)return;
 if(!hxp_update_hosts(host))return;
 /* The Switcher INIs already refer to msn.local, so updating hosts points
    both sign-in and switchboard at the new server without rewriting DLLs.
    WLM's existing TCP sessions are unusable after the server IP moves;
    relaunch only for an actual verified server-address change. */
 tskill_process("msnmsgr.exe");
 tskill_process("wlcomm.exe");
 Sleep(300);
 {const char *folder="C:\\Program Files\\Windows Live\\Messenger";
  join_path(msn,folder,"msnmsgr.exe");
  if(file_exists(msn))ShellExecuteA(g_main_window,"open",msn,NULL,NULL,1);
 }
}
static DWORD WINAPI hxp_discovery_worker(void *unused) {
 unsigned char wsa[512],key[32],noncebytes[8],digest[32];
 char id[17],nonce[17],mac[65],message[180],ack[180],reply[191];
 char *fields[6],oldhost[32],host[32];
 void *provider=NULL;
 (void)unused;
 if(!remote_token_is_valid(g_remote_token)){hxp_discovery_status=1;return 1;}
 if(!hxp_unhex(g_remote_token,key,32)){hxp_discovery_status=2;return 2;}
 if(WSAStartup(0x0202,wsa)!=0){hxp_discovery_status=3;return 3;}
 if(!CryptAcquireContextA(&provider,NULL,NULL,HXP_PROV_RSA_AES,CRYPT_VERIFYCONTEXT)){
  hxp_discovery_windows_error=GetLastError();
  hxp_discovery_status=4;WSACleanup();return 4;
 }
 if(!hxp_sha256(provider,key,32,digest)){
  hxp_discovery_windows_error=GetLastError();
  hxp_discovery_status=5;CryptReleaseContext(provider,0);WSACleanup();return 5;
 }
 hxp_discovery_status=6;
 hxp_hex(digest,8,id);
 for(;;){
  unsigned int sock=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
  SOCKADDR_IN target,from;int broad=1,timeout=2000,fromlen,size;
  if(sock==INVALID_SOCKET){hxp_discovery_windows_error=WSAGetLastError();Sleep(HXP_DISCOVERY_INTERVAL_MS);continue;}
  if(setsockopt(sock,SOL_SOCKET,SO_BROADCAST,(char*)&broad,sizeof(broad))!=0)
    hxp_discovery_windows_error=WSAGetLastError();
  setsockopt(sock,SOL_SOCKET,SO_RCVTIMEO,(char*)&timeout,sizeof(timeout));
  if(!CryptGenRandom(provider,8,noncebytes)){closesocket(sock);Sleep(8000);continue;}
  hxp_hex(noncebytes,8,nonce);
  int length=hxp_append(message,0,sizeof(message),"HXP1 ");
  length=hxp_append(message,length,sizeof(message),id);
  length=hxp_append(message,length,sizeof(message)," ");
  hxp_append(message,length,sizeof(message),nonce);
  if(!hxp_hmac(provider,key,message,mac)){closesocket(sock);Sleep(8000);continue;}
  length=hxp_append(message,strlen0(message),sizeof(message)," ");
  hxp_append(message,length,sizeof(message),mac);
  target.sin_family=AF_INET;target.sin_port=htons(HXP_LAN_DISCOVERY_PORT);
  target.sin_addr=0xFFFFFFFFu;for(int j=0;j<8;j++)target.sin_zero[j]=0;
  if(sendto(sock,message,strlen0(message),0,&target,sizeof(target))<0)
    hxp_discovery_windows_error=WSAGetLastError();
  fromlen=sizeof(from);size=recvfrom(sock,reply,sizeof(reply)-1,0,&from,&fromlen);
  if(size>0 && hxp_fields(reply,size,fields,6)==5 &&
     str_eq(fields[0],"HXP2") && str_eq(fields[1],nonce) &&
     strlen0(fields[2])==16 && strlen0(fields[4])==64 &&
     inet_addr(fields[3])!=0xFFFFFFFFu &&
     inet_addr(fields[3])==from.sin_addr){
   /* Rebuild the canonical signed prefix, do not accept untrusted strings
      without first authenticating the server response. */
   int p=hxp_append(message,0,sizeof(message),"HXP2 ");
   p=hxp_append(message,p,sizeof(message),fields[1]);
   p=hxp_append(message,p,sizeof(message)," ");
   p=hxp_append(message,p,sizeof(message),fields[2]);
   p=hxp_append(message,p,sizeof(message)," ");
   hxp_append(message,p,sizeof(message),fields[3]);
   if(hxp_hmac(provider,key,message,mac) && remote_ct_equal(mac,fields[4],64)){
    hxp_discovery_verified++;
    hxp_discovery_windows_error=0;
    /* Host registry only changes after this authenticated acknowledgement. */
    p=hxp_append(ack,0,sizeof(ack),"HXP3 ");
    p=hxp_append(ack,p,sizeof(ack),id);
    p=hxp_append(ack,p,sizeof(ack)," ");
    p=hxp_append(ack,p,sizeof(ack),nonce);
    p=hxp_append(ack,p,sizeof(ack)," ");
    hxp_append(ack,p,sizeof(ack),fields[2]);
    if(hxp_hmac(provider,key,ack,mac)){
     p=hxp_append(ack,strlen0(ack),sizeof(ack)," ");
     hxp_append(ack,p,sizeof(ack),mac);
     sendto(sock,ack,strlen0(ack),0,&from,sizeof(from));
     p=0;while(fields[3][p]&&p<15){host[p]=fields[3][p];p++;}host[p]=0;
     hxp_apply_verified_host(host);
    }
   }
  }
  closesocket(sock);
  Sleep(HXP_DISCOVERY_INTERVAL_MS);
 }
 return 0;
}
#endif
