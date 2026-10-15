// SPDX-License-Identifier: GPL-2.0-or-later
#include "../gpu/shim/bbport_map_art.h"
#include "../gpu/shim/bbport_atlas_style.h"
#include "imgui_internal.h"
#include <cassert>
#include <cmath>
#include <cstdio>
static double Cross(ImVec2 a,ImVec2 b,ImVec2 p){return double(b.x-a.x)*(p.y-a.y)-double(b.y-a.y)*(p.x-a.x);}
static void Check(float width,float height,float ox,float oy){
    const BbAtlasStyle::Layout layout(width,height,ox,oy);const auto box=layout.Canvas();
    const ImVec2 full_min{ox,oy},full_max{ox+width,oy+height},lo{box.x,box.y},hi{box.x+box.w,box.y+box.h};
    const float fade=BbAtlasStyle::Layout::edge_fade*layout.scale;
    ImDrawList list(ImGui::GetDrawListSharedData());list._ResetForNewFrame();list.PushClipRectFullScreen();
    // An existing enormous triangle remains untouched. The fade restores the
    // background after it, independent of how coarse the floor geometry is.
    list.AddTriangleFilled({ox-1000,oy-1000},{ox+5000,oy-1000},{ox,oy+5000},IM_COL32_WHITE);
    const int prior=list.VtxBuffer.Size;const ImDrawVert first=list.VtxBuffer[0];
    const int first_index=list.IdxBuffer.Size;
    BbMapArt::DrawBackgroundFade(&list,full_min,full_max,lo,hi,fade);
    assert(list.VtxBuffer.Size-prior==16&&list.IdxBuffer.Size-first_index==24);
    assert(list.VtxBuffer[0].pos.x==first.pos.x&&list.VtxBuffer[0].col==first.col);
    for(int i=prior;i<list.VtxBuffer.Size;++i){const auto& v=list.VtxBuffer[i];
        assert(v.pos.x>=lo.x&&v.pos.x<=hi.x&&v.pos.y>=lo.y&&v.pos.y<=hi.y);
        assert(std::abs(v.uv.x-(v.pos.x-ox)/width)<1e-6&&std::abs(v.uv.y-(v.pos.y-oy)/height)<1e-6);
        const int alpha=(v.col>>IM_COL32_A_SHIFT)&255;
        const float edge=std::min({v.pos.x-lo.x,hi.x-v.pos.x,v.pos.y-lo.y,hi.y-v.pos.y});
        assert((edge<.001f&&alpha==255)||(std::abs(edge-fade)<.001f&&alpha==0));
        assert((v.col&IM_COL32(255,255,255,0))==IM_COL32(255,255,255,0));
    }
    double area=0;for(int i=first_index;i<list.IdxBuffer.Size;i+=3){const auto a=list.VtxBuffer[list.IdxBuffer[i]].pos,b=list.VtxBuffer[list.IdxBuffer[i+1]].pos,c=list.VtxBuffer[list.IdxBuffer[i+2]].pos;area+=std::abs(Cross(a,b,c))*.5;}
    const double expected=double(box.w)*box.h-double(box.w-2*fade)*(box.h-2*fade);assert(std::abs(area-expected)<.1);
    // Independent interior sampling verifies every edge/corner has precisely
    // the intended alpha and no overlapping wedge (no accumulated darkening).
    for(int y=0;y<37;++y)for(int x=0;x<61;++x){const ImVec2 p{lo.x+box.w*(x+.317f)/61,lo.y+box.h*(y+.419f)/37};int count=0;double alpha=0;
        for(int i=first_index;i<list.IdxBuffer.Size;i+=3){const auto& a=list.VtxBuffer[list.IdxBuffer[i]];const auto& b=list.VtxBuffer[list.IdxBuffer[i+1]];const auto& c=list.VtxBuffer[list.IdxBuffer[i+2]];const double denom=Cross(a.pos,b.pos,c.pos),u=Cross(b.pos,c.pos,p)/denom,v=Cross(c.pos,a.pos,p)/denom,w=1-u-v;
            if(u>=0&&v>=0&&w>=0){++count;alpha=u*((a.col>>IM_COL32_A_SHIFT)&255)+v*((b.col>>IM_COL32_A_SHIFT)&255)+w*((c.col>>IM_COL32_A_SHIFT)&255);}}
        const float dist=std::min({p.x-lo.x,hi.x-p.x,p.y-lo.y,hi.y-p.y});
        if(dist>=fade)assert(count==0);else {assert(count==1);assert(std::abs(alpha-255*(1-dist/fade))<.002);}
    }
    list.PopClipRect();
}
int main(){
    ImGui::CreateContext();assert(BbMapArt::Init());
    for(auto size:{ImVec2(1280,720),ImVec2(1920,1080),ImVec2(3440,1440),ImVec2(640,360)})Check(size.x,size.y,17,29);
    BbMapArt::Shutdown();ImGui::DestroyContext();std::puts("ATLAS_BACKGROUND_FADE_UV_ALPHA_CORNERS_PASS");
}
