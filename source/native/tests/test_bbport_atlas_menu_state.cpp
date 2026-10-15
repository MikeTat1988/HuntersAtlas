#include "../gpu/shim/bbport_atlas_menu_state.h"
#include <cassert>
#include <cstdio>

int main() {
    BbAtlasMenuState state;
    constexpr auto left=BbAtlasMenuState::Left;
    constexpr auto right=BbAtlasMenuState::Right;
    constexpr auto cross=BbAtlasMenuState::Cross;

    assert(state.Route(true,0,false,0,cross,100).buttons==0);
    assert(state.Route(true,0,false,0,cross,280).buttons==0);
    auto move=state.Route(true,0,false,left,cross,281);
    assert(state.focused && state.anchor==0 && move.move && !(move.buttons&left));
    state.Route(true,0,false,0,cross,282);
    move=state.Route(true,0,false,right,cross,283);
    assert(!state.focused && move.move && !(move.buttons&right)); // reveal first

    state.Route(true,0,false,0,cross,284);
    state.Route(true,0,false,left,cross,285);
    state.Route(true,0,false,0,cross,286);
    move=state.Route(true,0,false,left,cross,287);
    assert(!state.focused && !move.move && (move.buttons&left)); // native 0 -> 2

    state.Route(true,2,false,0,cross,288);
    move=state.Route(true,2,false,right,cross,289);
    assert(state.focused && state.anchor==2 && move.move && !(move.buttons&right));
    state.Route(true,2,false,0,cross,290);
    move=state.Route(true,2,false,left,cross,291);
    assert(!state.focused && move.move && !(move.buttons&left)); // reveal System

    state.Route(true,2,false,0,cross,292);
    state.Route(true,2,false,right,cross,293);
    state.Route(true,2,false,0,cross,294);
    move=state.Route(true,2,false,right,cross,295);
    assert(!state.focused && !move.move && (move.buttons&right)); // native 2 -> 0

    state.Route(true,0,false,0,cross,296);
    state.Route(true,0,false,left,cross,297);
    state.Route(true,0,false,0,cross,298);
    move=state.Route(true,0,false,cross,cross,299);
    assert(move.open && !(move.buttons&cross));

    std::puts("BBPORT_ATLAS_MENU_STATE_PASS");
}
