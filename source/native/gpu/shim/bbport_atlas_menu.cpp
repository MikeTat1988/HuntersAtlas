// SPDX-License-Identifier: GPL-2.0-or-later
#include "bbport_atlas_menu.h"
#include "bbport_atlas_menu_state.h"
#include "bbport_map.h"
#include "bbport_map_art.h"
#include "../../src/runtime_map.h"
#include "imgui.h"
#include <SDL3/SDL.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace BbAtlasMenu {
namespace {
BbAtlasMenuState state;
std::atomic<bool> visible{false},focused{false},controller{false},suppressed{false};
bool mouse_held=false,mouse_up_owned=false,hovered=false;
uint32_t map_previous=0;
ImVec2 tile_min{},tile_max{};
BbMapMenu menu{};
bool Query() {
    BbMapLocation loc{};
    return !suppressed && BbMap::Enabled() && runtime_map_menu_state(&menu) && menu.top_level && runtime_map_location(&loc);
}
void Refresh() {
    const bool ready=state.Settled(Query(),SDL_GetTicks());
    visible=ready&&!BbMap::IsOpen();focused=state.focused;
}
bool Hit(float x,float y){return x>=tile_min.x&&y>=tile_min.y&&x<tile_max.x&&y<tile_max.y;}
}
bool Visible(){return visible;}
bool Interacting(){return visible || BbMap::IsOpen() || runtime_map_menu_open();}
bool UsesControllerGlyphs(){const char* qa=std::getenv("BB_ATLAS_QA_DEVICE");return std::getenv("BB_ATLAS_QA")&&qa?std::strcmp(qa,"controller")==0:bool(controller);}
bool Focused(){return focused;}
void Suppress(bool value){suppressed=value;if(value){visible=false;state.Reset();}}
void Reset(){state.Reset();focused=false;visible=false;hovered=false;mouse_held=false;map_previous=0;}
void Tick(){Refresh();if(BbMap::IsOpen()&&!runtime_map_menu_open()&&state.focused){BbMap::Close();Reset();}}
uint32_t RoutePad(uint32_t buttons,uint8_t lx,uint8_t ly,uint8_t rx,uint8_t ry) {
    const bool in_menu=Query();
    const bool was_open=BbMap::IsOpen();
    const uint32_t rising=buttons&~map_previous;
    auto result=state.Route(in_menu,menu.selected,was_open,buttons,runtime_map_confirm_button(),SDL_GetTicks());
    if(result.open)BbMap::OpenFromMenu();
    if(!was_open&&in_menu&&BbMap::ShortcutMode()==1&&(rising&0x4u)){BbMap::OpenFromMenu();state.blocked|=buttons;result.buttons=0;}
    if(was_open) {
        if(result.close)BbMap::Close();
        else BbMap::MappedPad(rising,lx,ly);
        result.buttons=0;
    }
    map_previous=buttons;
    (void)rx;(void)ry;
    Refresh();return result.buttons;
}
bool HandleMouse(const SDL_Event& e) {
    if(e.type==SDL_EVENT_WINDOW_FOCUS_LOST || e.type==SDL_EVENT_GAMEPAD_REMOVED){if(e.type==SDL_EVENT_GAMEPAD_REMOVED)BbMap::Close();Reset();return false;}
    if(e.type==SDL_EVENT_GAMEPAD_BUTTON_DOWN || (e.type==SDL_EVENT_GAMEPAD_AXIS_MOTION&&std::abs(int(e.gaxis.value))>6000))controller=true;
    if(e.type==SDL_EVENT_KEY_DOWN || e.type==SDL_EVENT_MOUSE_MOTION || e.type==SDL_EVENT_MOUSE_BUTTON_DOWN)controller=false;
    if(e.type==SDL_EVENT_MOUSE_BUTTON_UP&&e.button.button==SDL_BUTTON_LEFT&&mouse_up_owned){
        mouse_up_owned=false;const bool pressed=mouse_held;mouse_held=false;
        SDL_Window* window=SDL_GetWindowFromID(e.button.windowID);const float d=window?SDL_GetWindowPixelDensity(window):1;
        if(pressed&&Visible()&&Hit(e.button.x*d,e.button.y*d))BbMap::OpenFromMenu();return true;
    }
    if(!Visible())return false;
    if(e.type==SDL_EVENT_MOUSE_MOTION) {
        SDL_Window* window=SDL_GetWindowFromID(e.motion.windowID);const float d=window?SDL_GetWindowPixelDensity(window):1;
        hovered=Hit(e.motion.x*d,e.motion.y*d);
        ImGui::GetIO().AddMousePosEvent(e.motion.x*d,e.motion.y*d);
        return true;
    }
    if(e.type==SDL_EVENT_MOUSE_BUTTON_DOWN && e.button.button==SDL_BUTTON_LEFT){
        SDL_Window* window=SDL_GetWindowFromID(e.button.windowID);const float d=window?SDL_GetWindowPixelDensity(window):1;
        if(Hit(e.button.x*d,e.button.y*d)){mouse_held=true;mouse_up_owned=true;state.focused=true;state.anchor=menu.selected;focused=true;return true;}
    }
    return false;
}
void Draw() {
    if(!Visible())return;
    const auto* vp=ImGui::GetMainViewport();const float s=std::min(vp->Size.x/1280.0f,vp->Size.y/720.0f);
    const ImVec2 offset(vp->Pos.x+(vp->Size.x-1280*s)*.5f,vp->Pos.y+(vp->Size.y-720*s)*.5f);
    auto p=[&](float x,float y){return ImVec2(offset.x+x*s,offset.y+y*s);};
    tile_min=p(474,280);tile_max=p(530,336);
    auto* draw=ImGui::GetForegroundDrawList();
    const bool active=state.focused||hovered;
    if(active){
        // Cover only the native contextual text and focus rim. The native
        // selection remains intact, so Left/Back needs no memory patch.
        const ImU32 plate=IM_COL32(25,27,26,255),clear=IM_COL32(25,27,26,0);
        draw->AddRectFilled(p(185,321),p(276,343),plate);
        draw->AddRectFilledMultiColor(p(180,321),p(185,343),clear,plate,plate,clear);
        draw->AddRectFilledMultiColor(p(276,321),p(281,343),plate,clear,clear,plate);
        const char* language=std::getenv("BB_LANGUAGE");const char* label=language&&std::atoi(language)==8?"Карта":"Map";
        ImFont* font=language&&std::atoi(language)==8?ImGui::GetFont():BbMap::TitleFont();const float size=20*s;const auto extent=font->CalcTextSizeA(size,1000,0,label);
        draw->AddText(font,size,ImVec2(offset.x+269*s-extent.x,offset.y+323*s),IM_COL32(196,177,125,255),label);
        if(state.anchor==2){
            draw->AddRect(p(414,280),p(470,336),IM_COL32(38,34,28,255),0,0,5.5f*s);
            draw->AddRectFilled(p(416,282),p(468,334),IM_COL32(20,18,15,64));
            draw->AddRect(p(414,280),p(470,336),IM_COL32(131,123,103,255),0,0,.8f*s);
        }
    }
    BbMapArt::DrawMenuIcon(draw,ImVec2((tile_min.x+tile_max.x)*.5f,(tile_min.y+tile_max.y)*.5f),56*s,mouse_held?IM_COL32(180,170,145,255):IM_COL32_WHITE);
    draw->AddRect(tile_min,tile_max,active?IM_COL32(235,233,220,255):IM_COL32(131,123,103,255),0,0,(active?1.7f:.8f)*s);
    if(hovered)ImGui::SetTooltip("Map");
}
}
