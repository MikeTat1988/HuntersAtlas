// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
union SDL_Event;
struct ImFont;
namespace BbMap {
void Init();
bool IsOpen();
bool CapturesInput();
bool Enabled();
int ShortcutMode();
bool UsesControllerGlyphs();
void OpenFromMenu();
void MappedPad(unsigned rising,unsigned char lx,unsigned char ly,unsigned char rx=128,unsigned char ry=128,unsigned held=0);
void Tick();
bool HandleEvent(const SDL_Event& event);
void Close();
void Back();
void Settings();
// Set to the game's existing serif body font before drawing the map.
void SetTitleFont(ImFont* font);
ImFont* TitleFont();
void Draw();
// Opt-in local test driver; inert unless BB_MAP_TEST_CONTROL is supplied.
void PollTestCommands();
namespace Testing {
// Synthetic overlapping-floor regression for vertex-interpolated floor height.
bool AutoLayerSelectsClosestSurface();
}
}
