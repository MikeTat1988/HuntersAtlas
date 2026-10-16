// SPDX-License-Identifier: GPL-2.0-or-later
#include "../gpu/shim/bbport_map_features.h"
#include <SDL3/SDL.h>
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <unordered_map>
#include <cstdio>
static std::unordered_map<unsigned,int> values;
extern "C" int runtime_atlas_flag(uint32_t id){auto i=values.find(id);return i==values.end()?-1:i->second;}
extern "C" uintptr_t runtime_atlas_player_token(){return 1;}
int main(int argc,char** argv) {
    assert(argc==2);SDL_Init(0);
    _putenv_s("BB_MAP_ITEMS_ENABLED","1");_putenv_s("BB_MAP_FOG_ENABLED","1");_putenv_s("BB_MAP_NPC_MODE","new_dialogue");
    _putenv_s("BB_MAP_ITEM_CATEGORIES","healing");
    const std::filesystem::path root=argv[1];std::filesystem::create_directories(root);
    using J=nlohmann::json;
    J area={{"lamps",J::array({{{"id","open"},{"name","Open"},{"pos",{1,2,3}},{"return_point",2412950},{"unlock_flag",100}},
                              {{"id","locked"},{"name","Locked"},{"pos",{4,5,6}},{"return_point",2412951},{"unlock_flag",101},{"available_on",{200}}}})},
            {"reveal_regions",J::array({{{"boss_flags",{200}}}})},
            {"npc_rules",{{"42",J::array({"and",J::array({"==",J::array({"flag",300}),1}),J::array({"==",J::array({"flag",301}),0})})}}},
            {"pickups",J::array({{{"pos",{1,2,3}},{"contents",J::array({{{"category","healing"},{"name","Blood Vial"},{"quantity",2},{"collected_flag",400}}})}}})}};
    J data={{"schema",1},{"game_eboot_sha256","d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9"},{"areas",{{"m24_01_00_00",area}}}};
    {std::ofstream f(root/"features.json");f<<data;}
    values={{100,1},{101,0},{200,0},{300,1},{301,0},{400,0}};
    BbMapFeatures::Init(root);BbMapFeatures::Refresh(true);
    assert(BbMapFeatures::Error().empty());assert(BbMapFeatures::Available()==std::vector<int>{0});
    assert(BbMapFeatures::Destinations()[0].discovered&&!BbMapFeatures::Destinations()[1].discovered);
    assert(BbMapFeatures::ItemCategoryEnabled("healing"));
    assert(!BbMapFeatures::ItemCategoryEnabled("equipment")&&!BbMapFeatures::ItemCategoryEnabled("insight"));
    assert(!BbMapFeatures::Revealed("m24_01_00_00",1,2,3));assert(BbMapFeatures::Pickups("m24_01_00_00").empty());
    assert(BbMapFeatures::NpcVisible("m24_01_00_00",42));assert(!BbMapFeatures::NpcVisible("m24_01_00_00",43));
    values[200]=1;SDL_Delay(205);BbMapFeatures::Refresh(true);
    assert(BbMapFeatures::Revealed("m24_01_00_00",1,2,3));assert(BbMapFeatures::Pickups("m24_01_00_00").size()==1);
    // Defeating a boss and revealing the map must not discover its unlit lamp.
    assert(!BbMapFeatures::Destinations()[1].discovered);
    assert(BbMapFeatures::Available()==std::vector<int>{0});
    values[301]=1;values[400]=1;values[100]=0;values[101]=1;SDL_Delay(205);BbMapFeatures::Refresh(true);
    assert(!BbMapFeatures::NpcVisible("m24_01_00_00",42));assert(BbMapFeatures::Pickups("m24_01_00_00").empty());
    assert(BbMapFeatures::Available()==std::vector<int>{1});
    assert(!BbMapFeatures::Destinations()[0].discovered&&BbMapFeatures::Destinations()[1].discovered);
    // An activated lamp stays discovered when temporary travel requirements fail.
    values[200]=0;SDL_Delay(205);BbMapFeatures::Refresh(true);
    assert(BbMapFeatures::Destinations()[1].discovered&&!BbMapFeatures::Destinations()[1].available);
    assert(BbMapFeatures::Available().empty());
    // Missing activation data is hidden, never treated as an unlocked lamp.
    values.erase(101);SDL_Delay(205);BbMapFeatures::Refresh(true);
    assert(!BbMapFeatures::Destinations()[1].discovered);
    values.erase(301);values.erase(400);SDL_Delay(205);BbMapFeatures::Refresh(true);
    assert(!BbMapFeatures::NpcVisible("m24_01_00_00",42));assert(BbMapFeatures::Pickups("m24_01_00_00").empty());
    BbMapFeatures::Refresh(false);assert(BbMapFeatures::Available().empty());
    data["schema"]=99;{std::ofstream f(root/"features.json");f<<data;}
    BbMapFeatures::Init(root);assert(!BbMapFeatures::Error().empty()&&BbMapFeatures::Destinations().empty());
    std::filesystem::remove(root/"features.json");SDL_Quit();puts("ATLAS_FEATURE_STATE_PASS");
}
