// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <SDL3/SDL.h>
#include <atomic>
#include <cstdint>

// Deliberate shared Xbox / PlayStation shortcut for the navigation map.
// Call HandleEvent for each SDL event and Tick(SDL_GetTicks()) every frame.
class BbMapControllerChord {
public:
    static constexpr uint64_t HoldDurationMs = 650;

    // Returns true when this event belongs to the active controller chord and
    // should be consumed by the overlay. Partial chords are left to the game.
    bool HandleEvent(const SDL_Event& event);

    // Returns true exactly once when the complete chord has remained held long
    // enough. `now_ms` must use the same clock as SDL_GetTicks().
    bool Tick(uint64_t now_ms);

    void Reset();
    void SetEnabled(bool enabled);
    bool IsArming() const;
    bool WantsCapture() const;

private:
    bool IsComplete() const;
    void RefreshCapture();

    SDL_JoystickID controller_ = 0;
    uint8_t held_ = 0;
    uint64_t started_ms_ = 0;
    bool started_ = false;
    bool enabled_ = true;
    bool fired_ = false;
    bool capture_latched_ = false;
    bool blocked_until_release_ = false;
    std::atomic<bool> capture_{false};
};
