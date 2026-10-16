// SPDX-License-Identifier: GPL-2.0-or-later
#include "bbport_map_features.h"
#include <SDL3/SDL.h>
#include <cstdlib>
#include <cmath>
#include <fstream>
#include <unordered_map>
#include <algorithm>

namespace BbMapFeatures {
namespace {
using Json=nlohmann::json;
Json areas;
std::vector<Destination> destinations;
std::unordered_map<unsigned,int> flags;
bool travel=false,items=false,fog=false,valid=false;
std::string npc_mode="all",categories,error;
uint64_t last_poll=0;
uintptr_t player=0;
bool env(const char* key){const char* v=std::getenv(key);return v&&std::string(v)=="1";}
int flag(unsigned id){auto i=flags.find(id);if(i!=flags.end())return i->second;return flags.emplace(id,valid?runtime_atlas_flag(id):-1).first->second;}
bool requirements(const Json& rule) {
    for(const auto& id:rule.value("available_on",Json::array()))if(!id.is_number_unsigned()&&!id.is_number_integer())return false;else if(flag(id.get<unsigned>())!=1)return false;
    for(const auto& id:rule.value("available_off",Json::array()))if(!id.is_number_unsigned()&&!id.is_number_integer())return false;else if(flag(id.get<unsigned>())!=0)return false;
    return true;
}
int evaluate(const Json& e,int depth=0) {
    if(depth>32)return -1;
    if(e.is_boolean())return e.get<bool>()?1:0;
    if(e.is_number_integer())return e.get<int>();
    if(!e.is_array()||e.empty()||!e[0].is_string())return -1;
    const std::string op=e[0];
    if(op=="flag"&&e.size()==2&&e[1].is_number_integer())return flag(e[1].get<unsigned>());
    if(e.size()!=3)return -1;
    int a=evaluate(e[1],depth+1),b=evaluate(e[2],depth+1);
    if(op=="and"){if(a==0||b==0)return 0;return a<0||b<0?-1:1;}
    if(op=="or"){if(a>0||b>0)return 1;return a<0||b<0?-1:0;}
    if(a<0||b<0)return -1;
    if(op=="==")return a==b;
    if(op=="!=")return a!=b;
    return -1;
}
bool inside(const Json& rule,float x,float y,float z) {
    if(y<rule.value("min_y",-1e9f)||y>rule.value("max_y",1e9f))return false;
    if(rule.contains("bounds")) {
        const auto& b=rule["bounds"];
        if(b.size()!=4||x<b[0].get<float>()||z<b[1].get<float>()||x>b[2].get<float>()||z>b[3].get<float>())return false;
    }
    if(rule.contains("centre")) {
        const auto& p=rule["centre"];
        if(p.size()!=3)return false;
        const float dx=x-p[0].get<float>(),dz=z-p[2].get<float>();
        if(dx*dx+dz*dz>std::pow(rule.value("radius",0.f),2))return false;
    }
    if(rule.contains("triangles")) {
        bool hit=false;
        for(const auto& t:rule["triangles"]) {
            if(t.size()!=6)continue;
            auto cross=[&](int a,int b){return (t[b].get<float>()-t[a].get<float>())*(z-t[a+1].get<float>())-(t[b+1].get<float>()-t[a+1].get<float>())*(x-t[a].get<float>());};
            float a=cross(0,2),b=cross(2,4),c=cross(4,0);
            if((a>=0&&b>=0&&c>=0)||(a<=0&&b<=0&&c<=0)){hit=true;break;}
        }
        if(!hit)return false;
    }
    return true;
}
}
void Init(const std::filesystem::path& directory) {
    destinations.clear();areas=Json::object();flags.clear();error.clear();
    travel=env("BB_MAP_TRAVEL_ENABLED");items=env("BB_MAP_ITEMS_ENABLED");fog=env("BB_MAP_FOG_ENABLED");
    if(const char* v=std::getenv("BB_MAP_NPC_MODE"))npc_mode=v;
    if(npc_mode!="all"&&npc_mode!="new_dialogue"&&npc_mode!="hidden")npc_mode="all";
    const char* c=std::getenv("BB_MAP_ITEM_CATEGORIES");categories=c?c:"healing,insight,equipment,echoes";
    try {
        std::ifstream f(directory/"features.json");Json data;f>>data;
        if(data.at("schema")!=1||data.at("game_eboot_sha256")!="d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9")throw std::runtime_error("Feature metadata does not match this game");
        areas=data.at("areas");if(!areas.is_object()||areas.size()>64)throw std::runtime_error("Invalid feature areas");
        for(auto it=areas.begin();it!=areas.end();++it)for(const auto& lamp:it.value().at("lamps")) {
            Destination d;d.id=lamp.at("id");d.area=it.key();d.name=lamp.at("name");const auto& p=lamp.at("pos");
            if(p.size()!=3||destinations.size()>=128)throw std::runtime_error("Invalid destination metadata");
            d.x=p[0];d.y=p[1];d.z=p[2];if(!std::isfinite(d.x)||!std::isfinite(d.y)||!std::isfinite(d.z))throw std::runtime_error("Invalid destination coordinate");
            const auto arrival=lamp.value("arrival_pos",p);for(int k=0;k<3;++k)d.native.arrival[k]=arrival[k].get<float>();
            d.native.return_point=lamp.at("return_point");d.native.unlock_flag=lamp.value("unlock_flag",0u);
            const auto on=lamp.value("available_on",Json::array()),off=lamp.value("available_off",Json::array());
            if(on.size()>8||off.size()>8||d.native.return_point<=0)throw std::runtime_error("Invalid travel conditions");
            for(const auto& id:on)d.native.on[d.native.on_count++]=id.get<unsigned>();
            for(const auto& id:off)d.native.off[d.native.off_count++]=id.get<unsigned>();
            destinations.push_back(std::move(d));
        }
        std::stable_sort(destinations.begin(),destinations.end(),[](const auto& a,const auto& b){return a.area==b.area?a.native.return_point<b.native.return_point:a.area<b.area;});
    }catch(const std::exception& e){error=std::string("Prepare Atlas maps for feature data: ")+e.what();destinations.clear();areas=Json::object();}
}
void Refresh(bool location_valid) {
    const uintptr_t token=location_valid?runtime_atlas_player_token():0;
    if(token==player&&location_valid==valid&&SDL_GetTicks()-last_poll<200)return;
    player=token;valid=location_valid&&token;last_poll=SDL_GetTicks();flags.clear();
    for(auto& d:destinations) {
        d.discovered=valid&&(!d.native.unlock_flag||flag(d.native.unlock_flag)==1);
        d.available=d.discovered;
        for(unsigned i=0;i<d.native.on_count;++i)d.available=d.available&&flag(d.native.on[i])==1;
        for(unsigned i=0;i<d.native.off_count;++i)d.available=d.available&&flag(d.native.off[i])==0;
        // Hunter's Dream has no lamp-unlock bit; its authored visit/availability
        // conditions provide the discovery state. Unknown reads remain hidden.
        if(!d.native.unlock_flag)d.discovered=d.available;
    }
}
const std::vector<Destination>& Destinations(){return destinations;}
std::vector<int> Available(){std::vector<int> result;for(size_t i=0;i<destinations.size();++i)if(destinations[i].available)result.push_back(int(i));return result;}
bool TravelEnabled(){return travel;}
bool ItemsEnabled(){return items;}
bool ItemCategoryEnabled(const char* category){return items&&(","+categories+",").find(","+std::string(category)+",")!=std::string::npos;}
bool FogEnabled(){return fog;}
const std::string& Error(){return error;}
bool Revealed(const std::string& area,float x,float y,float z) {
    if(!fog)return true;
    auto it=areas.find(area);if(it==areas.end())return false;
    if(it->value("always_visible",false))return true;
    for(const auto& rule:it->value("reveal_regions",Json::array()))if(inside(rule,x,y,z)) {
        if(!requirements(rule))return false;
        if(rule.contains("reveal_when")&&evaluate(rule["reveal_when"])!=1)return false;
        for(const auto& id:rule.value("boss_flags",Json::array()))if(flag(id.get<unsigned>())!=1)return false;
        return true;
    }
    return false;
}
bool NpcVisible(const std::string& area,int entity) {
    if(npc_mode=="hidden")return false;
    if(npc_mode=="all")return true;
    auto a=areas.find(area);if(a==areas.end()||!a->contains("npc_rules"))return false;
    auto r=(*a)["npc_rules"].find(std::to_string(entity));
    return r!=(*a)["npc_rules"].end()&&evaluate(*r)==1;
}
std::vector<Pickup> Pickups(const std::string& area) {
    std::vector<Pickup> result;if(!items||!valid)return result;
    auto a=areas.find(area);if(a==areas.end())return result;
    for(const auto& pickup:a->value("pickups",Json::array())) {
        if(!requirements(pickup))continue;
        const auto& p=pickup.at("pos");if(p.size()!=3)continue;
        if(!Revealed(area,p[0],p[1],p[2]))continue;
        Pickup out;out.x=p[0];out.y=p[1];out.z=p[2];
        for(const auto& item:pickup.at("contents")) {
            const std::string category=item.at("category");
            if(!ItemCategoryEnabled(category.c_str())||flag(item.at("collected_flag").get<unsigned>())!=0)continue;
            if(out.category.empty())out.category=category;
            if(!out.label.empty())out.label+='\n';
            out.label+=item.at("name").get<std::string>()+" x"+std::to_string(item.at("quantity").get<int>());
        }
        if(!out.category.empty())result.push_back(std::move(out));
    }
    return result;
}
}
