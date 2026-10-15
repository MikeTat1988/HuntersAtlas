// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "imgui.h"

namespace BbMapArt {

// Loads BBRA RGBA assets from BB_MAP_ART_DIR, or <BB_MAP_DIR parent>/art.
// Call after creating the ImGui context and Vulkan backend.
bool Init();

// Call after ImGui_ImplVulkan_Shutdown() and before ImGui::DestroyContext().
void Shutdown();

bool IsReady();
void DrawBackground(ImDrawList* draw, ImVec2 min, ImVec2 max,
                    ImU32 tint = IM_COL32_WHITE);
// Restore the original background beneath the map's edge, with matching UVs.
// Four nonoverlapping trapezoids include the corners without double blending.
void DrawBackgroundFade(ImDrawList* draw, ImVec2 background_min,
                        ImVec2 background_max, ImVec2 map_min,
                        ImVec2 map_max, float fade_width);
void DrawIcon(ImDrawList* draw, const char* name, ImVec2 center, float size,
              float rotation_radians = 0.0f,
              ImU32 tint = IM_COL32_WHITE);
void DrawMenuIcon(ImDrawList* draw,ImVec2 center,float size,ImU32 tint=IM_COL32_WHITE);

// Textures floor geometry with world-anchored UVs. Pass the active map bounds'
// center as world_origin and its larger X/Z span as world_tile_units to map the
// asset across the area without clamping distant coordinates to an edge.
void DrawFloorTriangle(ImDrawList* draw, const ImVec2 screen[3],
                       const ImVec2 world_xz[3], const ImU32 tint[3],
                       float world_tile_units = 512.0f,
                       ImVec2 world_origin = ImVec2(0.0f, 0.0f));

} // namespace BbMapArt
