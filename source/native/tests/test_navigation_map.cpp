// SPDX-License-Identifier: GPL-2.0-or-later
#include "../gpu/shim/bbport_map.h"
#include "../gpu/shim/bbport_map_direction.h"
#include "../src/runtime_map.h"
#include "imgui.h"
#include <SDL3/SDL.h>
#include <cassert>
#include <cstdio>
#include <fstream>
#include <nlohmann/json.hpp>

static bool valid=true;
static int samples;
static bool menu_open=false;
extern "C" int runtime_map_menu_open(){return menu_open;}
static BbMapLocation fixture{-196.75f,-28.65f,65.39f,0.0f,0x18010000u,1};
extern "C" int runtime_map_location(BbMapLocation* out) {
    ++samples;*out=fixture;out->valid=valid?1:0;return valid;
}
void key(SDL_Keycode value) {SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=value;assert(BbMap::HandleEvent(e));}
void frame() {
    ImGui::NewFrame();BbMap::Draw();ImGui::Render();
    assert(ImGui::GetDrawData()->TotalVtxCount>100);
}
int main(int argc,char**) {
    assert(BbMap::Testing::AutoLayerSelectsClosestSurface());
    // Regression for the reported 180-degree error, including screen-Z reversal.
    const auto south=BbMap::FacingOnMap(0),west=BbMap::FacingOnMap(1.57079632679f);
    const auto north=BbMap::FacingOnMap(3.14159265359f),east=BbMap::FacingOnMap(-1.57079632679f);
    assert(std::abs(south.x)<.00001f && south.y>.999f);
    assert(west.x<-.999f && std::abs(west.y)<.00001f);
    assert(std::abs(north.x)<.00001f && north.y<-.999f);
    assert(east.x>.999f && std::abs(east.y)<.00001f);
    ImGui::CreateContext();auto& io=ImGui::GetIO();io.DisplaySize={1920,1080};io.DeltaTime=1.0f/60;
    io.IniFilename=nullptr;io.Fonts->AddFontDefault();unsigned char* pixels;int w,h;io.Fonts->GetTexDataAsRGBA32(&pixels,&w,&h);
    io.BackendFlags|=ImGuiBackendFlags_RendererHasVtxOffset;
    BbMap::Init();assert(!BbMap::IsOpen());BbMap::Draw();assert(samples==0);
    if(argc>1){SDL_Event e{};e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_M;assert(!BbMap::HandleEvent(e));assert(!BbMap::IsOpen());BbMap::Draw();assert(samples==0);ImGui::DestroyContext();std::puts("NAVIGATION_MAP_DISABLED_PASS");return 0;}
    key(SDLK_M);assert(BbMap::IsOpen());frame();key(SDLK_HOME);frame();
    key(SDLK_H);frame();key(SDLK_H);frame();
    key(SDLK_H);frame();
    valid=false;frame(); // Loading must remove the player marker without crashing.
    key(SDLK_ESCAPE);assert(!BbMap::IsOpen());key(SDLK_M);assert(BbMap::IsOpen());key(SDLK_M);assert(!BbMap::IsOpen());
    SDL_Event e{};e.type=SDL_EVENT_GAMEPAD_BUTTON_DOWN;e.gbutton.which=1;
    e.gbutton.button=SDL_GAMEPAD_BUTTON_RIGHT_STICK;
    assert(!BbMap::HandleEvent(e));assert(!BbMap::IsOpen()); // Normal gameplay unaffected.
    menu_open=true;assert(!BbMap::HandleEvent(e));assert(!BbMap::IsOpen()); // Loading/unavailable player is guarded.
    valid=true;assert(BbMap::HandleEvent(e));assert(BbMap::IsOpen() && BbMap::CapturesInput());
    e.gbutton.button=SDL_GAMEPAD_BUTTON_EAST;assert(BbMap::HandleEvent(e));assert(!BbMap::IsOpen());
    assert(menu_open);menu_open=false; // Closing the atlas does not alter the underlying game menu.
    valid=true;
    std::ifstream atlas_file(std::string(std::getenv("BB_MAP_DIR"))+"/atlas.json");nlohmann::json atlas;atlas_file>>atlas;
    for(const auto& a:atlas.at("maps")) {
        const auto id=a.at("id").get<std::string>();unsigned area=std::stoul(id.substr(1,2)),block=std::stoul(id.substr(4,2));
        fixture.block=(area<<24)|(block<<16);const auto bounds=a.at("bounds");fixture.x=(float(bounds[0])+float(bounds[2]))*.5f;fixture.z=(float(bounds[1])+float(bounds[3]))*.5f;
        key(SDLK_M);frame();key(SDLK_HOME);frame();key(SDLK_M);
    }
    key(SDLK_M);e.type=SDL_EVENT_GAMEPAD_BUTTON_DOWN;e.gbutton.button=SDL_GAMEPAD_BUTTON_WEST;
    assert(BbMap::HandleEvent(e));frame();
    e.gbutton.button=SDL_GAMEPAD_BUTTON_WEST;assert(BbMap::HandleEvent(e));frame();
    e.gbutton.button=SDL_GAMEPAD_BUTTON_SOUTH;assert(BbMap::HandleEvent(e));frame();
    e.gbutton.button=SDL_GAMEPAD_BUTTON_EAST;assert(BbMap::HandleEvent(e));assert(!BbMap::IsOpen());
    e.type=SDL_EVENT_KEY_DOWN;e.key.key=SDLK_A;assert(!BbMap::HandleEvent(e));
    ImGui::DestroyContext();std::puts("NAVIGATION_MAP_UI_PASS");
}
