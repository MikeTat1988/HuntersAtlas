// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cmath>
namespace BbMap {
struct MapDirection { float x, y; };
// Character transform yaw points backwards; screen Y also reverses world Z.
inline MapDirection FacingOnMap(float yaw) { return {-std::sin(yaw), std::cos(yaw)}; }
}
