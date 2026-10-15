// SPDX-License-Identifier: GPL-2.0-or-later
#include "bbport_map_art.h"
#include "bbport_atlas_paths.h"
#include "imgui_internal.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <vector>

namespace BbMapArt {
namespace {
constexpr uint32_t kMaxDimension = 4096;
constexpr uint64_t kMaxAssetBytes = 64ull * 1024ull * 1024ull;
constexpr int kIconCell = 384;
constexpr int kIconAtlasSize = 1536;

struct Texture {
    ImTextureData* data = nullptr;
    int width = 0;
    int height = 0;
};

Texture background, icons, parchment, menu_icon;
bool ready = false;
int next_texture_id = 1000000;

uint32_t ReadLE32(const unsigned char* p) {
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) |
           (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}

bool LoadTexture(const std::filesystem::path& path, Texture& out) {
    try {
        std::error_code ec;
        const auto file_size = std::filesystem::file_size(path, ec);
        if (ec || file_size < 12 || file_size > kMaxAssetBytes + 12) return false;
        std::ifstream file(path, std::ios::binary);
        if (!file) return false;
        unsigned char header[12]{};
        file.read(reinterpret_cast<char*>(header), sizeof(header));
        if (!file || std::memcmp(header, "BBRA", 4) != 0) return false;
        const uint32_t width = ReadLE32(header + 4);
        const uint32_t height = ReadLE32(header + 8);
        if (!width || !height || width > kMaxDimension || height > kMaxDimension) return false;
        const uint64_t pixel_bytes = uint64_t(width) * uint64_t(height) * 4ull;
        if (pixel_bytes > kMaxAssetBytes || file_size != pixel_bytes + sizeof(header)) return false;

        auto texture = std::unique_ptr<ImTextureData>(new (std::nothrow) ImTextureData());
        if (!texture) return false;
        texture->Create(ImTextureFormat_RGBA32, int(width), int(height));
        file.read(reinterpret_cast<char*>(texture->GetPixels()), std::streamsize(pixel_bytes));
        if (!file || file.peek() != std::char_traits<char>::eof()) return false;
        texture->UseColors = true;
        texture->UniqueID = next_texture_id++;
        ImGui::RegisterUserTexture(texture.get());
        out.data = texture.release();
        out.width = int(width);
        out.height = int(height);
        return true;
    } catch (const std::exception& e) {
        std::printf("Map art: cannot load %s: %s\n", path.string().c_str(), e.what());
        return false;
    }
}

std::filesystem::path ArtDirectory() {
    const auto maps=BbAtlasPath("BB_MAP_DIR","navigation-map/maps");
    return BbAtlasPath("BB_MAP_ART_DIR",maps.parent_path()/"art");
}

void ForgetTexture(Texture& texture) {
    if (!texture.data) return;
    // Vulkan owns the descriptor/image. Deleting ImTextureData before the
    // renderer destroyed that resource would leave a live descriptor behind.
    if (texture.data->GetTexID() != ImTextureID_Invalid ||
        texture.data->BackendUserData != nullptr) {
        std::printf("Map art: Shutdown must run after the renderer releases its textures\n");
        return;
    }
    ImGui::UnregisterUserTexture(texture.data);
    delete texture.data;
    texture = {};
}

int IconIndex(const char* name) {
    static constexpr const char* names[] = {
        "lamp", "ladder", "talk", "gate", "player", "compass",
        "X", "Y", "B", "LS", "LB", "RB"
    };
    if (!name) return -1;
    for (int i = 0; i < int(std::size(names)); ++i)
        if (std::strcmp(name, names[i]) == 0) return i;
    return -1;
}

ImVec2 Rotate(ImVec2 p, ImVec2 center, float c, float s) {
    const float x = p.x - center.x, y = p.y - center.y;
    return ImVec2(center.x + x * c - y * s, center.y + x * s + y * c);
}

} // namespace

bool Init() {
    if (!ImGui::GetCurrentContext()) return false;
    if (ready) return true;
    const auto dir = ArtDirectory();
    if (!LoadTexture(dir / "background.bbra", background) ||
        !LoadTexture(dir / "icons.bbra", icons) ||
        !LoadTexture(dir / "parchment.bbra", parchment) ||
        icons.width != kIconAtlasSize || icons.height != kIconAtlasSize) {
        Shutdown();
        std::printf("Map art: expected background.bbra, 1536x1536 icons.bbra, and parchment.bbra in %s\n", dir.string().c_str());
        return false;
    }
    ready = true;
    LoadTexture(dir/"menu.bbra",menu_icon);
    return true;
}

void Shutdown() {
    if (!ImGui::GetCurrentContext()) return;
    ForgetTexture(background);
    ForgetTexture(icons);
    ForgetTexture(parchment);
    ForgetTexture(menu_icon);
    ready = background.data && icons.data && parchment.data;
}

bool IsReady() { return ready; }
void DrawMenuIcon(ImDrawList* draw,ImVec2 center,float size,ImU32 tint) {
    if(!draw)return;
    const ImVec2 a(center.x-size*.5f,center.y-size*.5f),b(center.x+size*.5f,center.y+size*.5f);
    if(menu_icon.data)draw->AddImage(menu_icon.data->GetTexRef(),a,b,ImVec2(0,0),ImVec2(1,1),tint);
    else {draw->AddRectFilled(a,b,IM_COL32(26,25,22,255));draw->AddText(ImVec2(a.x+size*.15f,a.y+size*.3f),IM_COL32(215,204,177,255),"Map");}
}

void DrawBackground(ImDrawList* draw, ImVec2 min, ImVec2 max, ImU32 tint) {
    if (!draw || !background.data) return;
    draw->AddImage(background.data->GetTexRef(), min, max, ImVec2(0, 0), ImVec2(1, 1), tint);
}

void DrawBackgroundFade(ImDrawList* draw, ImVec2 background_min,
                        ImVec2 background_max, ImVec2 map_min,
                        ImVec2 map_max, float fade_width) {
    if(!draw||!background.data||background_max.x<=background_min.x||
       background_max.y<=background_min.y||map_max.x<=map_min.x||
       map_max.y<=map_min.y||!std::isfinite(fade_width)||fade_width<=0)return;
    const float width=std::min({fade_width,(map_max.x-map_min.x)*.5f,(map_max.y-map_min.y)*.5f});
    const ImVec2 outer[4]={{map_min.x,map_min.y},{map_max.x,map_min.y},
                          {map_max.x,map_max.y},{map_min.x,map_max.y}};
    const ImVec2 inner[4]={{map_min.x+width,map_min.y+width},{map_max.x-width,map_min.y+width},
                          {map_max.x-width,map_max.y-width},{map_min.x+width,map_max.y-width}};
    draw->PushTexture(background.data->GetTexRef());
    for(int side=0;side<4;++side){
        const int next=(side+1)%4;
        const ImVec2 positions[4]={outer[side],outer[next],inner[next],inner[side]};
        draw->PrimReserve(6,4);const ImDrawIdx base=static_cast<ImDrawIdx>(draw->_VtxCurrentIdx);
        for(int index:{0,1,2,0,2,3})draw->PrimWriteIdx(base+index);
        for(int corner=0;corner<4;++corner){const auto p=positions[corner];
            const ImVec2 uv((p.x-background_min.x)/(background_max.x-background_min.x),
                            (p.y-background_min.y)/(background_max.y-background_min.y));
            draw->PrimWriteVtx(p,uv,IM_COL32(255,255,255,corner<2?255:0));
        }
    }
    draw->PopTexture();
}

void DrawIcon(ImDrawList* draw, const char* name, ImVec2 center, float size,
              float rotation_radians, ImU32 tint) {
    const int index = IconIndex(name);
    if (!draw || !icons.data || index < 0 || size <= 0.0f) return;
    const int col = index % 4, row = index / 4;
    // Keep linear sampling inside this icon cell so adjacent atlas cells do
    // not bleed into the glyph edges.
    constexpr float inset = 3.0f;
    const float w = float(icons.width), h = float(icons.height);
    const ImVec2 uv0((col * kIconCell + inset) / w, (row * kIconCell + inset) / h);
    const ImVec2 uv1(((col + 1) * kIconCell - inset) / w, ((row + 1) * kIconCell - inset) / h);
    const float half = size * 0.5f, c = std::cos(rotation_radians), s = std::sin(rotation_radians);
    const ImVec2 p0 = Rotate(ImVec2(center.x-half, center.y-half),center,c,s);
    const ImVec2 p1 = Rotate(ImVec2(center.x+half, center.y-half),center,c,s);
    const ImVec2 p2 = Rotate(ImVec2(center.x+half, center.y+half),center,c,s);
    const ImVec2 p3 = Rotate(ImVec2(center.x-half, center.y+half),center,c,s);
    draw->AddImageQuad(icons.data->GetTexRef(),p0,p1,p2,p3,uv0,ImVec2(uv1.x,uv0.y),uv1,ImVec2(uv0.x,uv1.y),tint);
}

void DrawFloorTriangle(ImDrawList* draw, const ImVec2 screen[3],
                       const ImVec2 world_xz[3], const ImU32 tint[3],
                       float world_tile_units,ImVec2 world_origin) {
    if (!draw || !parchment.data || !screen || !world_xz || !tint ||
        !std::isfinite(world_tile_units) || world_tile_units <= 0.0f) return;
    const float reciprocal = 1.0f / world_tile_units;
    ImVec2 uv[3];
    for (int i = 0; i < 3; ++i) {
        // Center the default coordinate window at world origin. Root may pass
        // a different scale for maps with a wider or narrower coordinate span.
        uv[i] = ImVec2(std::clamp(.5f + (world_xz[i].x-world_origin.x) * reciprocal, 0.0f, 1.0f),
                       std::clamp(.5f + (world_xz[i].y-world_origin.y) * reciprocal, 0.0f, 1.0f));
    }
    draw->PushTexture(parchment.data->GetTexRef());
    draw->PrimReserve(3, 3);
    const ImDrawIdx base = static_cast<ImDrawIdx>(draw->_VtxCurrentIdx);
    draw->PrimWriteIdx(base);
    draw->PrimWriteIdx(base + 1);
    draw->PrimWriteIdx(base + 2);
    for (int i = 0; i < 3; ++i) draw->PrimWriteVtx(screen[i], uv[i], tint[i]);
    draw->PopTexture();
}

} // namespace BbMapArt
