#include "../gpu/shim/bbport_map_controller.h"
#include <cassert>
#include <cstdio>

namespace {
SDL_Event button(SDL_GamepadButton which, SDL_JoystickID pad, uint64_t ms, bool down = true) {
    SDL_Event e{};
    e.type = down ? SDL_EVENT_GAMEPAD_BUTTON_DOWN : SDL_EVENT_GAMEPAD_BUTTON_UP;
    e.common.timestamp = ms * 1'000'000;
    e.gbutton.which = pad;
    e.gbutton.button = which;
    return e;
}
void chord(BbMapControllerChord& c, uint64_t start, SDL_JoystickID pad = 1) {
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, pad, start)));
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, pad, start + 1)));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, pad, start + 2)));
}
}

int main() {
    BbMapControllerChord c;
    chord(c, 100);
    assert(c.IsArming() && c.WantsCapture());
    assert(!c.Tick(751)); // 649 ms
    assert(c.Tick(752));
    assert(!c.Tick(900)); // one activation per hold
    assert(c.WantsCapture());
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 1, 901, false)));
    assert(c.WantsCapture() && !c.IsArming()); // capture remains until full release
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 902, false)));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 1, 903, false)));
    assert(!c.WantsCapture());
    chord(c, 1000);
    assert(c.Tick(1652));

    // A release before timeout cancels the hold; the remaining buttons cannot
    // complete a fresh chord until all have been released.
    c.Reset(); chord(c, 100);
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 200, false)));
    assert(c.WantsCapture());
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 1000)));
    assert(!c.Tick(10000)); // blocked until every chord button is released
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 1, 1001, false)));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 1, 1002, false)));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 1003, false)));
    assert(!c.WantsCapture());

    chord(c, 2000);
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 1, 2100, false)));
    assert(!c.Tick(3000));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 1, 2101, false)));
    assert(c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 2102, false)));
    chord(c, 3000);
    assert(!c.Tick(3651));
    assert(c.Tick(3652));
    c.Reset();

    // Buttons from distinct controller identities cannot make a chord.
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 7, 4000)));
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 8, 4001)));
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 7, 4002)));
    assert(!c.WantsCapture() && !c.Tick(5000));
    c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 7, 5001, false));
    c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 7, 5002, false));
    c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 7, 5003, false));

    // Focus loss and device removal both clear pending state.
    chord(c, 6000, 9);
    SDL_Event focus{}; focus.type = SDL_EVENT_WINDOW_FOCUS_LOST;
    c.HandleEvent(focus);
    assert(!c.WantsCapture() && !c.Tick(7000));
    chord(c, 8000, 9);
    SDL_Event removed{}; removed.type = SDL_EVENT_GAMEPAD_REMOVED; removed.gdevice.which = 9;
    c.HandleEvent(removed);
    assert(!c.WantsCapture() && !c.Tick(9000));

    // Disabled shortcut has no capture or activation.
    c.SetEnabled(false);
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, 1, 10000)));
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, 1, 10001)));
    assert(!c.HandleEvent(button(SDL_GAMEPAD_BUTTON_START, 1, 10002)));
    assert(!c.WantsCapture() && !c.Tick(11000));
    c.SetEnabled(true);
    chord(c, 12000);
    assert(c.Tick(12652));
    std::puts("MAP_CONTROLLER_CHORD_PASS");
}
