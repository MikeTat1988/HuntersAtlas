/* Standalone menu-sound integration test. Includes the runtime so that the
 * real audio port and mixer can be exercised without booting the game. */
#include "../src/runtime_audio.c"
#include <assert.h>

static const char *bank_path;
int runtime_file_translate(const char *guest, char *out, size_t size) {
    assert(strcmp(guest,"/app0/dvdroot_ps4/sound/sprj_main.fsb")==0);
    if(strlen(bank_path)+1>size)return -1;
    strcpy(out,bank_path);
    return 0;
}
void compat_sleep_ns(uint64_t ns) { (void)ns; }
uintptr_t runtime_lookup(const RuntimeExport *table, size_t count, const char *nid) {
    (void)table;(void)count;(void)nid;return 0;
}

static long file_size(FILE *f) { assert(fseek(f,0,SEEK_END)==0);long n=ftell(f);assert(n>=0);return n; }
static int segment_peak(FILE *f,long begin,long end) {
    assert(fseek(f,begin,SEEK_SET)==0);
    int peak=0;
    for(long pos=begin;pos<end;pos+=2){int16_t sample;assert(fread(&sample,2,1,f)==1);
        int magnitude=sample<0?-(int)sample:(int)sample;if(magnitude>peak)peak=magnitude;}
    return peak;
}

int main(int argc,char **argv) {
    assert(argc==3);bank_path=argv[1];
    /* SDL_AUDIODRIVER is SDL's actual environment variable. Neither this test
     * nor its captured output can reach a physical playback device. */
    assert(_putenv_s("SDL_AUDIODRIVER","dummy")==0);
    assert(_putenv_s("BB_AUDIO","")==0);
    assert(_putenv_s("BB_AUDIO_DUMP",argv[2])==0);
    assert(audio_init()==0);
    int32_t port=audio_open(1,0,0,256,48000,1);
    assert(port>=0 && ports[port&0xff].stream);
    int16_t silence[256*2]={0};
    BbMenuSoundStats stats;
    runtime_audio_menu_event(0);
    for(int i=0;i<12;++i)assert(output_port(port,silence,0)==512);
    runtime_audio_menu_stats(&stats);
    assert(stats.decoded_move==3072 && stats.decoded_select==4096);
    assert(stats.queued_move==1 && stats.mixed_move==1);
    runtime_audio_menu_event(1);
    for(int i=0;i<16;++i)assert(output_port(port,silence,0)==512);
    runtime_audio_menu_stats(&stats);
    assert(stats.queued_select==1 && stats.mixed_select==1);
    const int32_t zero_volume[8]={0};
    assert(audio_volume(port,3,zero_volume)==0);
    runtime_audio_menu_event(0);
    for(int i=0;i<12;++i)assert(output_port(port,silence,0)==512);
    runtime_audio_menu_stats(&stats);
    assert(stats.queued_move==2 && stats.mixed_move==2);
    assert(audio_close(port)==0);

    char dump_path[4096];
    assert(snprintf(dump_path,sizeof(dump_path),"%s.port0.2ch.s16",argv[2])<(int)sizeof(dump_path));
    FILE *dump=fopen(dump_path,"rb");assert(dump);
    const long move_bytes=12L*256*2*2, select_bytes=16L*256*2*2;
    assert(file_size(dump)==move_bytes*2+select_bytes);
    int move_peak=segment_peak(dump,0,move_bytes);
    int select_peak=segment_peak(dump,move_bytes,move_bytes+select_bytes);
    int muted_peak=segment_peak(dump,move_bytes+select_bytes,move_bytes*2+select_bytes);
    fclose(dump);
    assert(move_peak>0 && select_peak>0 && muted_peak==0);
    assert(_putenv_s("BB_AUDIO","none")==0);
    runtime_audio_menu_event(0);
    runtime_audio_menu_stats(&stats);
    assert(stats.muted==1 && stats.queued_move==2);
    printf("MENU_MIX_DUMMY_PASS decoded=%u/%u queued=%u/%u mixed=%u/%u peaks=%d/%d muted_peak=%d silent_requests=%u\n",
        stats.decoded_move,stats.decoded_select,stats.queued_move,stats.queued_select,
        stats.mixed_move,stats.mixed_select,move_peak,select_peak,muted_peak,stats.muted);
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
    return 0;
}
