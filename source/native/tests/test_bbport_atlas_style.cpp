// SPDX-License-Identifier: GPL-2.0-or-later
#include "../gpu/shim/bbport_atlas_style.h"
#include <cassert>
#include <cstdio>
#include <chrono>
#include <fstream>
#include <nlohmann/json.hpp>
using namespace BbAtlasStyle;
static Triangle tri(Point a,Point b,Point c){return {{a,b,c}};}
static void VerifyOutside(const std::vector<Line>& lines,FloorIndex& floors){
    for(const auto& line:lines){
        bool inside=false;floors.Query(line.a,line.b,[&](const Triangle& t){float lo,hi;if(Clip(t.p,line.a,line.b,lo,hi))inside=true;});
        assert(!inside);assert(std::isfinite(line.a.x)&&std::isfinite(line.b.z));
    }
}
static void Synthetic(){
    Layout normal(1280,720);assert(normal.scale==1);assert(normal.At(77,105).x==77);
    assert(normal.Canvas().y>=Layout::subtitle_top+Layout::subtitle_region_h+6);
    assert(normal.Canvas().y+normal.Canvas().h<Layout::footer_rule);
    assert(normal.Canvas().x==230&&normal.Canvas().w==835);
    assert(normal.Canvas().x+normal.Canvas().w==1065);
    assert(Layout::key_y>Layout::legend_y+Layout::legend_h);
    assert(Layout::key_x>Layout::footer_x+Layout::footer_w);
    assert(Layout::key_y+Layout::key_h<Layout::frame_bottom);
    Layout hd(1920,1080);assert(hd.scale==1.5f);assert(hd.At(1163,524).x==1744.5f);
    Layout wide(3440,1440);assert(wide.scale==2);assert(wide.x==440);assert(wide.At(640,360).x==1720);
    Layout small(640,360);assert(small.scale==.5f);
    for(auto size:{Point{1280,720},Point{1920,1080},Point{2560,1440},Point{3840,2160},Point{3440,1440}}){
        Layout l(size.x,size.z);const auto d=l.TravelDialog();
        assert(std::abs(d.w/l.scale-350)<.01f&&std::abs(d.h/l.scale-168)<.01f);
        assert(std::abs(d.x+d.w*.5f-size.x*.5f)<.01f&&std::abs(d.y+d.h*.5f-size.z*.5f)<.01f);
        for(int count:{4,6,7})for(int i=0;i<count;++i){const auto slot=l.FooterSlot(i,count);
            assert(slot.y>l.At(0,Layout::footer_rule).z&&slot.x+slot.w<=l.At(Layout::footer_x+Layout::footer_w+.01f,0).x);
            if(i){const auto previous=l.FooterSlot(i-1,count);assert(std::abs(previous.x+previous.w-slot.x)<.01f);}}
    }
    // A lit Tomb of Oedon remains visible twelve metres below Central Yharnam.
    assert(Layout::LampOnMap(true,true));assert(!Layout::LampOnMap(true,false));assert(!Layout::LampOnMap(false,true));
    CutCache cache;cache.Build({tri({0,0},{8,0},{0,8}),tri({8,0},{8,8},{0,8})},1);
    // Adjacent floor supports two wall segments with a real 2m opening.
    const std::vector<Line> walls={{{0,0},{3,0}},{{5,0},{8,0}},{{30,30},{35,30}}};
    for(float zoom:{.15f,.2f,.5f,1.f,3.f,9.f,25.f}){const float pitch=CutCache::Spacing(CutCache::Level(zoom,1))*zoom/1.41421356237f;assert(pitch>4.f&&pitch<7.f);}
    for(int lod=0;lod<CutCache::lod_count;++lod){const auto& strokes=cache.Get(0,lod,walls);VerifyOutside(strokes,cache.floors);
        for(const auto& l:strokes){assert(l.a.x<9&&l.b.x<9);assert(std::min(l.a.x,l.b.x)<=3.001f||std::max(l.a.x,l.b.x)>=4.999f);}
    }
    const auto before=cache.Get(0,1,walls);const auto& cached=cache.Get(0,1,{});assert(cached.size()==before.size());assert(!cached.empty());
    for(size_t i=0;i<cached.size();++i){assert(cached[i].a.x==before[i].a.x);assert(cached[i].wear==before[i].wear);}
    // Opposite winding and a thin floor crossing must be excluded exactly,
    // even when no probe/sample would land in the thin obstruction.
    FloorIndex floor;floor.Build({tri({1,.001f},{1.001f,-.001f},{1,-.001f})});
    const auto fragments=floor.Outside({0,0},{2,0},1);assert(fragments.size()==2);VerifyOutside(fragments,floor);
    CutCache unsupported;unsupported.Build({},1);assert(unsupported.Get(0,0,{{{0,0},{8,0}}}).empty());
}
int main(int argc,char** argv){
    Synthetic();
    if(argc>1){const std::string root=argv[1];std::ifstream input(root+"/atlas.json");nlohmann::json atlas;input>>atlas;
        size_t count=0,strokes=0,maximum=0;double milliseconds=0;
        for(const auto& item:atlas.at("maps")){const auto id=item.at("id").get<std::string>();std::ifstream f(root+"/"+id+".json");nlohmann::json area;f>>area;
            std::vector<Triangle> geometry;std::vector<std::vector<Line>> walls;
            for(const auto& layer:area.at("layers")){walls.emplace_back();for(const auto& t:layer.at("triangles"))geometry.push_back(tri({t[0],t[1]},{t[2],t[3]},{t[4],t[5]}));for(const auto& w:layer.at("walls"))walls.back().push_back({{w[0],w[1]},{w[2],w[3]}});}
            const auto start=std::chrono::steady_clock::now();CutCache cache;cache.Build(std::move(geometry),walls.size());
            for(size_t i=0;i<walls.size();++i){const auto& lines=cache.Get(i,CutCache::Level(9,1),walls[i]);VerifyOutside(lines,cache.floors);strokes+=lines.size();maximum=std::max(maximum,lines.size());}
            const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();milliseconds+=ms;++count;
            std::printf("%s layers=%zu build+verify_ms=%.2f\n",id.c_str(),walls.size(),ms);
        }
        assert(count==16);std::printf("ATLAS_CUT_16_MAP_PASS strokes=%zu maximum_layer=%zu build+verify_ms=%.2f\n",strokes,maximum,milliseconds);
    }
    std::puts("ATLAS_STYLE_SYNTHETIC_PASS");
}
