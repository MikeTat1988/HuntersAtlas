// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>

// Logical PS4 buttons after input.ini mapping. No native menu mutation.
class BbAtlasMenuState {
public:
    enum : uint32_t { Right=0x20,Up=0x10,Down=0x40,Left=0x80,Cross=0x4000,Circle=0x2000 };
    struct Result {uint32_t buttons;bool open=false,close=false,move=false;};
    bool focused=false;
    int anchor=2;
    uint32_t previous=0,blocked=0;
    uint64_t visible_since=0;
    bool was_visible=false;
    void Reset(){focused=false;anchor=2;blocked|=previous;was_visible=false;visible_since=0;}
    bool Settled(bool visible,uint64_t now) {
        if(!visible){was_visible=false;visible_since=0;return false;}
        if(!was_visible){was_visible=true;visible_since=now;}
        return now-visible_since>=180;
    }
    Result Route(bool visible,int index,bool map_open,uint32_t buttons,uint32_t confirm,uint64_t now) {
        blocked&=buttons;
        const uint32_t rising=buttons&~previous;previous=buttons;
        const bool ready=Settled(visible,now);
        Result out{buttons&~blocked};
        if(map_open){
            blocked|=buttons;
            if(rising&(confirm==Cross?Circle:Cross)){out.close=true;blocked|=buttons;}
            out.buttons=0;return out;
        }
        if(!ready){focused=false;return out;}
        if(focused&&index!=anchor)focused=false;
        if(!focused&&((index==2&&(rising&Right))||(index==0&&(rising&Left)))){
            focused=true;anchor=index;blocked|=index==2?Right:Left;out.move=true;
        }
        else if(focused){
            if(rising&confirm){out.open=true;blocked|=buttons;}
            else if(rising&(Left|Right)){
                const uint32_t edge=rising&(Left|Right);
                // Revealing the underlying tile uses the local cursor sound.
                // Moving to the opposite end uses the game's own native wrap.
                const bool reveal=(anchor==2&&edge==Left)||(anchor==0&&edge==Right);
                focused=false;
                if(reveal){blocked|=edge;out.move=true;}
            }
            // Up/down and Back retain the game's own menu behavior.
            else if(rising&(Up|Down|(confirm==Cross?Circle:Cross)))focused=false;
        }
        out.buttons=buttons&~blocked;return out;
    }
};
