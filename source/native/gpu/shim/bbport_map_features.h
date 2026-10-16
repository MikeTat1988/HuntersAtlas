// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../../src/runtime_atlas_state.h"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <string>
#include <vector>

namespace BbMapFeatures {
struct Destination {
    std::string id, area, name;
    float x=0,y=0,z=0;
    BbAtlasTravelDestination native{};
    bool available=false;
    bool discovered=false;
};
struct Pickup {
    float x=0,y=0,z=0;
    std::string category,label;
};
void Init(const std::filesystem::path& directory);
void Refresh(bool location_valid);
const std::vector<Destination>& Destinations();
std::vector<int> Available();
bool TravelEnabled();
bool ItemsEnabled();
bool ItemCategoryEnabled(const char* category);
bool FogEnabled();
const std::string& Error();
bool Revealed(const std::string& area,float x,float y,float z);
bool NpcVisible(const std::string& area,int entity);
std::vector<Pickup> Pickups(const std::string& area);
}
