// Tape arena (docs/tape_design.md, roadmap Step 2c): one process-wide, append-only region holding the
// tape words + draw logs of admitted v2 entries. Pool entries (TapeEntry) carry only a TapeHandle.
// Protocol: store() bump-allocates with fetch_add and copies the tape; only then does the caller
// publish the handle with pool->report() (under the pool's lock, so picking it later sees the bytes).
// Stored bytes are never freed or modified during a run, so readers use them without locks.
// The first allocation that does not fit closes the arena: store() fails from then on (arena_full).
// The region is reserved with mmap(MAP_NORESERVE): untouched pages cost nothing.
#pragma once
#include <sys/mman.h>
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include "pool.hpp"
#include "server.hpp"

struct TapeHandle {
    uint64_t offset;      // byte offset in the arena: words, then draws
    uint32_t words, draws;
    uint64_t input_hash;  // hash of the generator output this tape produced
};
struct TapeEntry {  // Entry's fields (the pool code uses .hits) + the arena handle
    uint8_t variant;
    uint16_t size;
    uint64_t seed;
    uint32_t hits;
    TapeHandle tape;
};
static_assert(sizeof(TapeHandle) == 24 && sizeof(TapeEntry) == 48, "tape entry layout");

class Arena {
public:
    static constexpr size_t DEFAULT_BYTES = size_t(1) << 30;

    explicit Arena(size_t bytes = DEFAULT_BYTES) : cap(bytes) {
        void* p = mmap(nullptr, cap, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
        if (p == MAP_FAILED) cap = 0;
        else base = (char*)p;
    }
    ~Arena() { if (base) munmap(base, cap); }
    Arena(const Arena&) = delete;
    Arena& operator=(const Arena&) = delete;

    // Copies a tape and its draw log; false (and arena_full + 1) if it does not fit.
    bool store(const uint64_t* words, uint32_t n_words, const TapeDraw* log, uint32_t n_draws, uint64_t input_hash,
               TapeHandle& h) {
        size_t bytes = 8 * size_t(n_words) + sizeof(TapeDraw) * n_draws;
        size_t off = used.fetch_add(bytes, std::memory_order_relaxed);
        if (off + bytes > cap) return full.fetch_add(1, std::memory_order_relaxed), false;
        memcpy(base + off, words, 8 * size_t(n_words));
        memcpy(base + off + 8 * size_t(n_words), log, sizeof(TapeDraw) * n_draws);
        h = {off, n_words, n_draws, input_hash};
        return true;
    }
    const uint64_t* words(const TapeHandle& h) const { return (const uint64_t*)(base + h.offset); }
    const TapeDraw* draws(const TapeHandle& h) const { return (const TapeDraw*)(base + h.offset + 8 * size_t(h.words)); }
    size_t bytes() const { return std::min(used.load(std::memory_order_relaxed), cap); }  // append-only: = peak
    uint64_t arena_full() const { return full.load(std::memory_order_relaxed); }
    size_t capacity() const { return cap; }

private:
    char* base = nullptr;
    size_t cap;
    std::atomic<size_t> used{0};
    std::atomic<uint64_t> full{0};
};
