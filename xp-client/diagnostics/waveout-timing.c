/*
 * XP sound-device timing check: 12 seconds of DIGITAL SILENCE, no audio
 * recording and no user speech. Poll waveOut playback completion timing
 * using a prequeued 160ms ring. Never touches Messenger or system settings.
 *
 * This is a hardware/driver capacity test, not an MSN audio capture.
 */
#define WINAPI __attribute__((stdcall))
#define IMPORT __declspec(dllimport)
typedef unsigned int DWORD;
typedef unsigned short WORD;
typedef unsigned int UINT;
typedef int BOOL;
typedef void *HANDLE;
typedef struct { DWORD low; int high; } QPC;
typedef struct { WORD tag, channels; DWORD rate, bytes; WORD align, bits, size; } FORMAT;
typedef struct {
 char *data; DWORD len,recorded; DWORD user,flags,loops;
 void *next; DWORD reserved;
} WAVEHDR;
#define MMSYSERR_NOERROR 0
#define WAVE_MAPPER ((UINT)0xFFFFFFFF)
#define WAVE_FORMAT_PCM 1
#define WHDR_DONE 0x00000001
#define CALLBACK_NULL 0
#define STD_OUTPUT_HANDLE 0xFFFFFFF5u
#define SLOTS 8
#define FRAME_SAMPLES 160
#define FRAME_BYTES (FRAME_SAMPLES*2)
#define TEST_MS 12000u
IMPORT HANDLE WINAPI GetStdHandle(DWORD);
IMPORT BOOL WINAPI WriteFile(HANDLE,const void *,DWORD,DWORD *,void *);
IMPORT BOOL WINAPI QueryPerformanceCounter(QPC *);
IMPORT BOOL WINAPI QueryPerformanceFrequency(QPC *);
IMPORT DWORD WINAPI GetTickCount(void);
IMPORT void WINAPI Sleep(DWORD);
IMPORT void WINAPI ExitProcess(DWORD);
IMPORT char *WINAPI GetCommandLineA(void);
IMPORT UINT WINAPI waveOutGetNumDevs(void);
IMPORT UINT WINAPI waveOutOpen(void **,UINT,const FORMAT *,DWORD,DWORD,DWORD);
IMPORT UINT WINAPI waveOutPrepareHeader(void *,WAVEHDR *,UINT);
IMPORT UINT WINAPI waveOutWrite(void *,WAVEHDR *,UINT);
IMPORT UINT WINAPI waveOutUnprepareHeader(void *,WAVEHDR *,UINT);
IMPORT UINT WINAPI waveOutReset(void *);
IMPORT UINT WINAPI waveOutClose(void *);

static HANDLE output;
static char b[310];
static int n;
static void lit(const char *str){while(*str&&n<300)b[n++]=*str++;}
static void number(DWORD v){
 char tmp[12];int k=0;
 do{tmp[k++]=(char)('0'+v%10);v/=10;}while(v&&k<11);
 while(k&&n<300)b[n++]=tmp[--k];
}
static void field(const char *label,DWORD value){lit(label);number(value);lit(" ");}
static void flush(){DWORD written=0;lit("\r\n");WriteFile(output,b,(DWORD)n,&written,0);n=0;}
static void error(const char *step,UINT rc){lit("ERROR ");lit(step);lit(" code=");number(rc);flush();}

void WINAPI mainCRTStartup(void){
 void *wave=0;
 FORMAT format={1,1,8000,16000,2,16,0};
 WAVEHDR headers[SLOTS];
 static char silence[SLOTS][FRAME_BYTES];
 DWORD previous[SLOTS],start;
 QPC frequency,now;
 DWORD ticksPerMs=0,frames=0,long25=0,long40=0,long100=0,maxGap=0;
 DWORD outstanding=0,starved=0;
 UINT rc,idx,active_slots=SLOTS;
 output=GetStdHandle(STD_OUTPUT_HANDLE);
 /* /2 tests a 40ms queue; /4 tests 80ms; default tests 160ms. */
 {char *args=GetCommandLineA();int i=0;
  while(args&&args[i]){
   if(args[i]=='/'&&args[i+1]=='2')active_slots=2;
   if(args[i]=='/'&&args[i+1]=='4')active_slots=4;
   i++;
  }}
 lit("BEGIN xp_waveout_timing");flush();
 field("waveOut_devices=",waveOutGetNumDevs());flush();
 lit("OPENING waveOut");flush();
 rc=waveOutOpen(&wave,WAVE_MAPPER,&format,0,0,CALLBACK_NULL);
 if(rc!=MMSYSERR_NOERROR){error("waveOutOpen_8k_pcm16",rc);ExitProcess(2);}
 if(!QueryPerformanceFrequency(&frequency)||!QueryPerformanceCounter(&now)||
    frequency.high!=0||frequency.low<1000){
  error("QPC",0);waveOutClose(wave);ExitProcess(3);
 }
 ticksPerMs=frequency.low/1000;
 for(idx=0;idx<active_slots;idx++){
  WAVEHDR *hdr=&headers[idx];
  hdr->data=silence[idx];hdr->len=FRAME_BYTES;hdr->recorded=0;
  hdr->user=0;hdr->flags=0;hdr->loops=0;hdr->next=0;hdr->reserved=0;
  rc=waveOutPrepareHeader(wave,hdr,sizeof(*hdr));
  if(rc!=0){error("prepare",rc);waveOutReset(wave);waveOutClose(wave);ExitProcess(4);}
  previous[idx]=0;
  rc=waveOutWrite(wave,hdr,sizeof(*hdr));
  if(rc!=0){error("initial_write",rc);waveOutReset(wave);waveOutClose(wave);ExitProcess(5);}
  outstanding++;
 }
 start=GetTickCount();
 lit("READY xp_waveOut_8k_pcm16 silent_ms=12000 buffers=");number(active_slots);flush();
 while((DWORD)(GetTickCount()-start)<TEST_MS){
  int completed=0;
  QueryPerformanceCounter(&now);
  for(idx=0;idx<active_slots;idx++){
   WAVEHDR *hdr=&headers[idx];
   if(hdr->flags&WHDR_DONE){
    DWORD nowms=now.low/ticksPerMs;
    /* Completion timing on the same header has 160ms of audio between
       callbacks; compare against that interval, not 20ms. */
    if(previous[idx] && frames>=active_slots){
      DWORD delta=nowms-previous[idx];
     DWORD nominal=20*active_slots;
     DWORD deviation=delta>nominal?delta-nominal:nominal-delta;
     if(deviation>25)long25++;
     if(deviation>40)long40++;
     if(deviation>100)long100++;
     if(delta>maxGap)maxGap=delta;
    }
    previous[idx]=nowms;
    frames++;completed++;
    if(outstanding)outstanding--;
    if(outstanding==0)starved++;
    if((DWORD)(GetTickCount()-start)<TEST_MS){
     rc=waveOutWrite(wave,hdr,sizeof(*hdr));
     if(rc){error("refill_write",rc);break;}
     outstanding++;
    }
   }
  }
  Sleep(completed?1:3);
 }
 waveOutReset(wave);
 for(idx=0;idx<active_slots;idx++)waveOutUnprepareHeader(wave,&headers[idx],sizeof(headers[idx]));
 waveOutClose(wave);
 field("frames_played=",frames);
 field("expected_approx=",TEST_MS/20);
 field("driver_ring_emptied=",starved);
 field("per_slot_deviation_gt25=",long25);
 field("per_slot_deviation_gt40=",long40);
 field("per_slot_deviation_gt100=",long100);
 field("max_per_slot_interval_ms=",maxGap);flush();
 ExitProcess(0);
}
