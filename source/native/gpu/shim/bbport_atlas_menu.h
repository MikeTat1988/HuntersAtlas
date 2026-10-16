// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdint>
union SDL_Event;
namespace BbAtlasMenu {
bool Visible();
bool Interacting();
bool UsesControllerGlyphs();
bool UsesPlayStationGlyphs();
bool Focused();
void Suppress(bool value);
void Tick();
void Draw();
bool HandleMouse(const SDL_Event& e);
uint32_t RoutePad(uint32_t buttons,uint8_t lx,uint8_t ly,uint8_t rx,uint8_t ry);
void Reset();
}
