// Opt-in diagnostic: BB_FLIP_TRACE=1 records a bounded history, dumped on flip failure.
#pragma once
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>

namespace BbFlipTrace {
inline bool Enabled() {
    static const bool enabled = [] { const char* e = std::getenv("BB_FLIP_TRACE"); return e && e[0] == '1'; }();
    return enabled;
}
struct Entry { const char* event; std::uint64_t a, b, c, d; };
inline std::array<Entry, 1024> entries{};
inline std::uint64_t head{};
inline std::mutex mutex;
inline std::atomic<std::uint64_t> label_base{};
inline void Record(const char* event, std::uint64_t a = 0, std::uint64_t b = 0,
                   std::uint64_t c = 0, std::uint64_t d = 0) {
    if (!Enabled()) return;
    std::scoped_lock lock{mutex};
    entries[head++ % entries.size()] = {event, a, b, c, d};
}
inline bool IsLabel(std::uint64_t address) {
    if (!Enabled()) return false;
    const auto base = label_base.load(std::memory_order_relaxed);
    return base && address >= base && address < base + 16 * sizeof(std::uint64_t);
}
inline void Dump() {
    if (!Enabled()) return;
    std::scoped_lock lock{mutex};
    std::fprintf(stderr, "BB_FLIP_TRACE begin total=%llu fields=a,b,c,d(hex)\n", (unsigned long long)head);
    const auto first = head > entries.size() ? head - entries.size() : 0;
    for (auto i = first; i < head; ++i) {
        const auto& e = entries[i % entries.size()];
        std::fprintf(stderr, "BB_FLIP_TRACE %llu %s %llx %llx %llx %llx\n",
                     (unsigned long long)i, e.event, (unsigned long long)e.a,
                     (unsigned long long)e.b, (unsigned long long)e.c, (unsigned long long)e.d);
    }
    std::fflush(stderr);
}
} // namespace BbFlipTrace
