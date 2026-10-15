#include "../src/runtime_menu_sound.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc,char **argv){
    assert(argc==3);
    BbMenuSounds sounds={0};
    assert(runtime_menu_sound_load(argv[1],&sounds));
    assert(sounds.move.frames==3072 && sounds.select.frames==4096);
    int move_peak=0,select_peak=0;
    for(uint32_t i=0;i<sounds.move.frames;++i){
        int sample=sounds.move.pcm[i];if(sample<0)sample=-sample;
        if(sample>move_peak)move_peak=sample;
    }
    for(uint32_t i=0;i<sounds.select.frames;++i){
        int sample=sounds.select.pcm[i];if(sample<0)sample=-sample;
        if(sample>select_peak)select_peak=sample;
    }
    assert(move_peak>0 && select_peak>0);
    printf("MENU_SOUND_DECODE_PASS move=%u peak=%d select=%u peak=%d\n",
           sounds.move.frames,move_peak,sounds.select.frames,select_peak);
    runtime_menu_sound_free(&sounds);
    FILE *bad=fopen(argv[2],"wb");assert(bad);
    unsigned char truncated[64]={0};
    truncated[0]='F';truncated[1]='S';truncated[2]='B';truncated[3]='5';
    assert(fwrite(truncated,1,sizeof(truncated),bad)==sizeof(truncated));
    assert(fclose(bad)==0);
    BbMenuSounds rejected={0};
    assert(!runtime_menu_sound_load(argv[2],&rejected));
    runtime_menu_sound_free(&rejected);
    assert(remove(argv[2])==0);
    puts("MENU_SOUND_MALFORMED_REJECTED");
    return 0;
}
