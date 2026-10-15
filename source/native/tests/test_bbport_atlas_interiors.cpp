// SPDX-License-Identifier: GPL-2.0-or-later
#include "../gpu/shim/bbport_atlas_interiors.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <chrono>
#include <nlohmann/json.hpp>
using namespace BbAtlasInteriors;
static Ring square(float a,float b,float c,float d){return {{a,b},{c,b},{c,d},{a,d},{a,b}};}
static Triangle tri(Point a,Point b,Point c){return {{a,b,c}};}
static double Sum(const Cache& cache){double a=0;for(auto& layer:cache.layers)for(auto t:layer)a+=std::abs(Turn(t.p[0],t.p[1],t.p[2]))*.5;return a;}
static void Verify(Cache& cache,std::vector<BbAtlasStyle::FloorIndex>& layer_floors){
    for(size_t li=0;li<cache.layers.size();++li){auto& floors=layer_floors.at(li);assert(cache.layers[li].size()<=Cache::max_layer_triangles);
        for(const auto& t:cache.layers[li]){for(auto p:t.p)assert(std::isfinite(p.x)&&std::isfinite(p.z));Ring polygon(t.p.begin(),t.p.end());const auto b=Box(polygon);floors.Query({b.x0,b.z0},{b.x1,b.z1},[&](Triangle f){if(Turn(f.p[0],f.p[1],f.p[2])<0)std::swap(f.p[1],f.p[2]);if(std::abs(Turn(f.p[0],f.p[1],f.p[2]))<1.e-10)return;auto intersection=polygon;for(int k=0;k<3;++k)intersection=Half(intersection,f.p[k],f.p[(k+1)%3],true,0);assert(intersection.size()<3||std::abs(Area(intersection))<1.e-8);});}
        const int lod=BbAtlasStyle::CutCache::Level(9,1);const auto& lines=cache.Get(li,lod);for(auto line:lines)floors.Query(line.a,line.b,[&](const Triangle& f){float lo,hi;assert(!BbAtlasStyle::Clip(f.p,line.a,line.b,lo,hi));});const auto* data=lines.data();assert(cache.Get(li,lod).data()==data);
    }
}
static void Synthetic(){
    std::vector<BbAtlasStyle::FloorIndex> empty(1);empty[0].Build({});Cache c;const auto outer=square(0,0,10,10),hole=square(2,2,8,8);
    c.Build({{outer,hole}},empty);assert(c.holes==1&&std::abs(Sum(c)-36)<1.e-5);Verify(c,empty);
    auto reversed=hole;std::reverse(reversed.begin(),reversed.end());c.Build({{outer,reversed}},empty);assert(std::abs(Sum(c)-36)<1.e-5);
    std::vector<BbAtlasStyle::FloorIndex> island(2);island[0].Build({tri({4,4},{6,4},{4,6}),tri({6,4},{6,6},{4,6})});c.Build({{outer,hole},{}},island);assert(Sum(c)>31&&Sum(c)<32);Verify(c,island);
    // A different-level island does not erase this layer's void. The renderer
    // must draw it afterward as faded context, keeping its floor visible.
    std::swap(island[0],island[1]);c.Build({{outer,hole},{}},island);assert(std::abs(Sum(c)-36)<1.e-5);Verify(c,island);
    Ring concave={{2,2},{8,2},{8,4},{4,4},{4,8},{2,8},{2,2}};c.Build({{outer,concave}},empty);assert(std::abs(Sum(c)-20)<1.e-5);
    c.Build({{outer,square(20,20,30,30)}},empty);assert(Sum(c)==0); // Exterior air never filled.
    Ring open={{2,2},{8,2},{8,8},{2,8}};c.Build({{outer,open}},empty);assert(Sum(c)==0);
    Ring crossed={{2,2},{8,8},{2,8},{8,2},{2,2}};c.Build({{outer,crossed}},empty);assert(Sum(c)==0);
    Ring touch={{2,2},{8,2},{8,8},{5,5},{2,8},{5,5},{2,2}};c.Build({{outer,touch}},empty);assert(Sum(c)==0);
    c.Build({{outer,square(0,2,8,8)}},empty);assert(Sum(c)==0);
    // Exact narrow same-layer floors must be excluded, not sampled away.
    std::vector<BbAtlasStyle::FloorIndex> narrow(1);narrow[0].Build({tri({4,0},{4.001f,10},{4,10}),tri({4,0},{4.001f,0},{4.001f,10})});c.Build({{outer,hole}},narrow);Verify(c,narrow);assert(Sum(c)<36);
    std::puts("ATLAS_INTERIORS_SYNTHETIC_PASS");
}
int main(int argc,char** argv){Synthetic();if(argc<2)return 0;const std::string root=argv[1];std::ifstream in(root+"/atlas.json");nlohmann::json atlas;in>>atlas;size_t maps=0,total=0;double max_build=0;
    for(const auto& entry:atlas.at("maps")){const auto id=entry.at("id").get<std::string>();std::ifstream f(root+"/"+id+".json");nlohmann::json area;f>>area;std::vector<std::vector<Ring>> outlines;std::vector<std::vector<Triangle>> floor;
        for(const auto& layer:area.at("layers")){outlines.emplace_back();floor.emplace_back();for(const auto& r:layer.at("outlines")){Ring ring;for(const auto& p:r)ring.push_back({p[0],p[1]});outlines.back().push_back(std::move(ring));}for(const auto& t:layer.at("triangles"))floor.back().push_back(tri({t[0],t[1]},{t[2],t[3]},{t[4],t[5]}));}
        std::vector<BbAtlasStyle::FloorIndex> index(floor.size());for(size_t i=0;i<floor.size();++i)index[i].Build(std::move(floor[i]));Cache c;auto start=std::chrono::steady_clock::now();c.Build(outlines,index);const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();max_build=std::max(max_build,ms);Verify(c,index);size_t count=0,lines=0;for(size_t li=0;li<c.layers.size();++li){count+=c.layers[li].size();lines+=c.Get(li,BbAtlasStyle::CutCache::Level(9,1)).size();}total+=count;++maps;
        std::printf("%s layers=%zu holes=%zu rejected=%zu budget_skips=%zu triangles=%zu strokes=%zu build_ms=%.3f area_m2=%.3f\n",id.c_str(),outlines.size(),c.holes,c.rejected,c.budget_skips,count,lines,ms,Sum(c));std::fflush(stdout);
        if(argc>2){nlohmann::json out;out["layers"]=nlohmann::json::array();for(const auto& layer:c.layers){nlohmann::json triangles=nlohmann::json::array();for(const auto& t:layer)triangles.push_back({t.p[0].x,t.p[0].z,t.p[1].x,t.p[1].z,t.p[2].x,t.p[2].z});out["layers"].push_back(triangles);}std::ofstream result(std::string(argv[2])+"/"+id+".interiors.json");result<<out.dump();}
    }assert(maps==16);std::printf("ATLAS_INTERIORS_16_MAP_PASS triangles=%zu maximum_build_ms=%.3f\n",total,max_build);
}
