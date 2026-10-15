/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "../src/runtime_map.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include "../src/map_build_guard.inc"
static void ptr(unsigned char* memory,size_t off,void* value){memcpy(memory+off,&value,sizeof(value));}
int main(void) {
    BbMapLocation l;
    unsigned char *image=calloc(1,0x5570000),*world=calloc(1,0x100),*chr=calloc(1,0x600),*modules=calloc(1,0x100),*transform=calloc(1,0x300),*menu=calloc(1,0x100);
    assert(image && world && chr && modules && transform);
    runtime_map_bind(image,0x5570000);assert(!runtime_map_location(&l) && !l.valid && !runtime_map_menu_open());
    memcpy(image+BB_MAP_GUARD_OFFSET,bb_map_guard,sizeof(bb_map_guard));
    const unsigned char menu_guard[]={0x48,0x8b,0x05,0xd6,0x6f,0xdf,0x03,0x83,0x78,0x3c,0x00};
    const unsigned char focus_guard[]={0x8b,0x8b,0xe8,0x0a,0,0,0x85,0xc9,0x79,0x06,0x8b,0x8b,0xe4,0x0a,0,0};
    memcpy(image+0x1bdf835,focus_guard,sizeof(focus_guard));
    memcpy(image+0x176b89b,menu_guard,sizeof(menu_guard));ptr(image,0x5562878,menu);
    runtime_map_bind(image,0x5570000);assert(!runtime_map_menu_open());
    assert(runtime_map_confirm_button()==0); /* Missing native predicate: fail closed. */
    const unsigned char cross[]={0x31,0xc0,0xc3,0x90,0x90,0x90};
    const unsigned char circle[]={0xb8,0x01,0x00,0x00,0x00,0xc3};
    memcpy(image+0x1fb8730,cross,sizeof(cross));
    _putenv_s("BB_ENTER_BUTTON","0");
    assert(runtime_map_confirm_button()==0x4000u); /* Conflicting environment cannot override game. */
    memcpy(image+0x1fb8730,circle,sizeof(circle));
    _putenv_s("BB_ENTER_BUTTON","1");
    assert(runtime_map_confirm_button()==0x2000u);
    image[0x1fb8730+1]=2;assert(runtime_map_confirm_button()==0);
    BbMapMenu native_menu;assert(!runtime_map_menu_state(&native_menu)&&!native_menu.supported);
    memcpy(image+0x1fb8730,cross,sizeof(cross));
    _putenv_s("BB_ENTER_BUTTON","");
#include "../src/map_confirm_guard.inc"
    memcpy(image+0x1fb8730,bb_map_cross_region_guard,sizeof(bb_map_cross_region_guard));
    assert(runtime_map_confirm_button()==0x4000u);
    image[0x1fb8730+24]^=1;assert(runtime_map_confirm_button()==0);
    memcpy(image+0x1fb8730,cross,sizeof(cross));
    int state=2;memcpy(menu+0x54,&state,4);assert(runtime_map_menu_open());
    state=1;memcpy(menu+0x54,&state,4);assert(!runtime_map_menu_open());
    state=0;memcpy(menu+0x54,&state,4);assert(!runtime_map_menu_open());
    ptr(image,0x5562878,(void*)0x12345678);assert(!runtime_map_menu_open());
    ptr(image,0x5562878,menu);
    ptr(image,0x553e878,world);ptr(world,0x60,chr);ptr(chr,0x3b0,modules);ptr(modules,0x68,transform);
    ptr(chr,0x288,world);uint32_t block=0x18010000;memcpy(chr+0x3f8,&block,4);
    float pos[3]={-196.75f,-28.65f,65.39f},yaw=1.0f;memcpy(transform+0x1e0,pos,12);memcpy(transform+0x1d4,&yaw,4);
    assert(runtime_map_location(&l) && l.valid && l.x==pos[0] && l.block==block);
    pos[0]=NAN;memcpy(transform+0x1e0,pos,12);assert(!runtime_map_location(&l) && !l.valid);
    ptr(modules,0x68,(void*)0x12345);assert(!runtime_map_location(&l));
    ptr(world,0x60,NULL);assert(!runtime_map_location(&l));
    runtime_map_bind(NULL,0);assert(runtime_map_confirm_button()==0);
    free(menu);free(transform);free(modules);free(chr);free(world);free(image);
    puts("MAP_LOCATION_READ_ONLY_PASS");return 0;
}
