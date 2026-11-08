// catest.c - diagnose the CA install: run each CryptoAPI step, log result + GetLastError to C:\catest.txt
typedef void *HANDLE; typedef void *HINSTANCE; typedef void *HWND;
typedef unsigned long DWORD; typedef unsigned int UINT; typedef long LONG;
typedef int BOOL; typedef unsigned short WORD; typedef unsigned char BYTE;
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
#define NULL ((void*)0)
#define GENERIC_READ 0x80000000
#define GENERIC_WRITE 0x40000000
#define FILE_SHARE_READ 1
#define OPEN_EXISTING 3
#define CREATE_ALWAYS 2
#define INVALID_HANDLE_VALUE ((void*)-1)
#define CRYPT_STRING_BASE64HEADER 0
#define X509_ASN_ENCODING 1
#define CERT_STORE_PROV_SYSTEM 10
#define CERT_SYSTEM_STORE_LOCAL_MACHINE 0x00020000
#define CERT_SYSTEM_STORE_CURRENT_USER 0x00010000
#define CERT_STORE_ADD_REPLACE_EXISTING 3
#define MB_OK 0
typedef const char *LPCSTR;
typedef char *LPSTR;
IMPORT HANDLE WINAPI GetModuleHandleA(LPCSTR);
IMPORT void WINAPI ExitProcess(UINT);
IMPORT DWORD WINAPI GetLastError(void);
IMPORT HANDLE WINAPI CreateFileA(LPCSTR,DWORD,DWORD,void*,DWORD,DWORD,HANDLE);
IMPORT BOOL WINAPI ReadFile(HANDLE,void*,DWORD,DWORD*,void*);
IMPORT BOOL WINAPI WriteFile(HANDLE,const void*,DWORD,DWORD*,void*);
IMPORT BOOL WINAPI CloseHandle(HANDLE);
IMPORT int WINAPI MessageBoxA(HWND,LPCSTR,LPCSTR,DWORD);
IMPORT BOOL WINAPI CryptStringToBinaryA(const char *,DWORD,DWORD,void *,DWORD *,DWORD *,DWORD *);
IMPORT void *WINAPI CertCreateCertificateContext(DWORD,const unsigned char *,DWORD);
IMPORT void *WINAPI CertOpenStore(DWORD,DWORD,DWORD,DWORD,const void *);
IMPORT BOOL WINAPI CertAddCertificateContextToStore(void *,const void *,DWORD,void *);
IMPORT BOOL WINAPI CertCloseStore(void *,DWORD);
IMPORT BOOL WINAPI CertFreeCertificateContext(const void *);

static HANDLE out;
static void w(const char *s){ DWORD n=0; while(s[n]) n++; WriteFile(out,s,n,&n,NULL); }
static void wnum(DWORD v){ char b[12]; int i=0,j; if(!v){w("0");return;} while(v){b[i++]='0'+(v%10);v/=10;} for(j=i-1;j>=0;j--){char c[2];c[0]=b[j];c[1]=0;w(c);} }
static void wline(const char *s,DWORD v){ w(s); w("="); wnum(v); w(" err="); wnum(GetLastError()); w("\r\n"); }

int WINAPI WinMain(HINSTANCE h, HINSTANCE p, LPSTR c, int s){
 static char pem[8192]; static unsigned char der[8192];
 DWORD pemLen=0, derLen=0, got=0;
 HANDLE f; void *ctx=NULL, *store=NULL; int ok=0;
 out=CreateFileA("C:\\catest.txt",GENERIC_WRITE,0,NULL,CREATE_ALWAYS,0,NULL);
 if(out==INVALID_HANDLE_VALUE){ MessageBoxA(NULL,"cannot write catest.txt","ca-test",MB_OK); return 0; }
 f=CreateFileA("C:\\HermesXP\\ca.pem",GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
 wline("open-ca-pem", f!=INVALID_HANDLE_VALUE);
 if(f==INVALID_HANDLE_VALUE){ CloseHandle(out); MessageBoxA(NULL,"ca.pem not found","ca-test",MB_OK); return 0; }
 ReadFile(f,pem,sizeof(pem)-1,&got,NULL); CloseHandle(f); pemLen=got; pem[pemLen]=0;
 wline("pem-len", pemLen);
 ok=CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,NULL,&derLen,NULL,NULL);
 wline("b64-size-query", ok); wline("der-len", derLen);
 if(ok && derLen<=sizeof(der)){
  ok=CryptStringToBinaryA(pem,pemLen,CRYPT_STRING_BASE64HEADER,der,&derLen,NULL,NULL);
  wline("b64-decode", ok);
  if(ok){
   ctx=CertCreateCertificateContext(X509_ASN_ENCODING,der,derLen);
   wline("cert-context", ctx!=NULL);
   if(ctx){
    store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_LOCAL_MACHINE,"ROOT");
    wline("open-store-LM", store!=NULL);
    if(!store){ store=CertOpenStore(CERT_STORE_PROV_SYSTEM,0,0,CERT_SYSTEM_STORE_CURRENT_USER,"ROOT"); wline("open-store-CU", store!=NULL); }
    if(store){
     ok=CertAddCertificateContextToStore(store,ctx,CERT_STORE_ADD_REPLACE_EXISTING,NULL);
     wline("add-to-store", ok);
     CertCloseStore(store,0);
    }
    CertFreeCertificateContext(ctx);
   }
  }
 }
 CloseHandle(out);
 MessageBoxA(NULL,"ca-test done, see C:\\catest.txt","ca-test",MB_OK);
 return 0;
}
void WINAPI WinMainCRTStartup(void){ WinMain(GetModuleHandleA(NULL),NULL,NULL,0); ExitProcess(0); }
