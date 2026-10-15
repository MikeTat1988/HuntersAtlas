// SPDX-License-Identifier: GPL-2.0-or-later
#include "bbport_map_controller.h"

namespace {
constexpr uint8_t kLeftShoulder = 1u << 0;
constexpr uint8_t kRightShoulder = 1u << 1;
constexpr uint8_t kStart = 1u << 2;
constexpr uint8_t kAllButtons = kLeftShoulder | kRightShoulder | kStart;

uint8_t ChordBit(SDL_GamepadButton button) {
    switch (button) {
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return kLeftShoulder;
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return kRightShoulder;
    case SDL_GAMEPAD_BUTTON_START: return kStart;
    default: return 0;
    }
}
}

bool BbMapControllerChord::IsComplete() const {
    return held_ == kAllButtons;
}

void BbMapControllerChord::RefreshCapture() {
    capture_.store(enabled_ && (IsComplete() || capture_latched_), std::memory_order_release);
}

bool BbMapControllerChord::HandleEvent(const SDL_Event& event) {
    if (event.type == SDL_EVENT_WINDOW_FOCUS_LOST) {
        Reset();
        return false;
    }

    if (event.type == SDL_EVENT_GAMEPAD_REMOVED) {
        if (controller_ != 0 && event.gdevice.which == controller_) Reset();
        return false;
    }

    if (event.type != SDL_EVENT_GAMEPAD_BUTTON_DOWN &&
        event.type != SDL_EVENT_GAMEPAD_BUTTON_UP) return false;

    const uint8_t bit = ChordBit(static_cast<SDL_GamepadButton>(event.gbutton.button));
    if (bit == 0 || !enabled_) return false;
    const bool down = event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN;
    const SDL_JoystickID id = event.gbutton.which;

    if (down) {
        // The first chord button claims the sequence. Buttons from another pad
        // cannot complete or disturb it.
        if (controller_ == 0) controller_ = id;
        if (id != controller_) return false;
        const bool was_complete = IsComplete();
        held_ |= bit;
        if (IsComplete()) capture_latched_ = true;
        if (!blocked_until_release_ && !started_ && IsComplete()) {
            // SDL3 event timestamps and SDL_GetTicks share the SDL monotonic
            // clock; conversion retains sub-second timing without wall clock.
            started_ms_ = event.common.timestamp / 1'000'000;
            started_ = true;
        }
        RefreshCapture();
        return was_complete || IsComplete() || capture_latched_;
    }

    if (controller_ != 0 && id != controller_) return false;
    const bool was_complete = IsComplete() || capture_latched_;
    held_ &= static_cast<uint8_t>(~bit);
    if (!IsComplete() && !fired_ && was_complete) {
        // Once all three were down, a short/aborted attempt cannot re-arm until
        // every chord button has been released. Keep capture latched meanwhile.
        blocked_until_release_ = true;
        started_ = false;
        started_ms_ = 0;
    }
    if (held_ == 0) {
        controller_ = 0;
        started_ = false;
        started_ms_ = 0;
        fired_ = false;
        capture_latched_ = false;
        blocked_until_release_ = false;
    }
    RefreshCapture();
    return was_complete;
}

bool BbMapControllerChord::Tick(uint64_t now_ms) {
    if (!enabled_ || !started_ || fired_ || !IsComplete()) return false;
    if (now_ms < started_ms_ || now_ms - started_ms_ < HoldDurationMs) return false;
    fired_ = true;
    return true;
}

void BbMapControllerChord::Reset() {
    held_ = 0;
    controller_ = 0;
    started_ms_ = 0;
    started_ = false;
    fired_ = false;
    capture_latched_ = false;
    blocked_until_release_ = false;
    capture_.store(false, std::memory_order_release);
}

void BbMapControllerChord::SetEnabled(bool enabled) {
    enabled_ = enabled;
    if (!enabled_) Reset();
    else RefreshCapture();
}

bool BbMapControllerChord::IsArming() const {
    return enabled_ && started_ && IsComplete() && !fired_;
}

bool BbMapControllerChord::WantsCapture() const {
    return capture_.load(std::memory_order_acquire);
}
