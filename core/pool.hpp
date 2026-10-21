// Shared fuzzing pool: a global 64 KiB coverage bitmap (bytes 0/1) plus a list of Entry recipes
// that reached new coverage. Pool has three virtual operations (pick = read, report = novelty
// check + merge + append, touch = write) and five locking strategies, built by make_pool():
// global, sharded, rwlock, snapshot, noshare. Entries are capped at 4096; once full, a random
// slot is overwritten. Each strategy also has a non-virtual dump() used only by pool_bench --check.
#pragma once
#include <atomic>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <random>
#include <shared_mutex>
#include <string>
#include <vector>

struct Entry {
    uint8_t variant;
    uint16_t size;
    uint64_t seed;
    uint32_t hits;
};

class Pool {
public:
    virtual ~Pool() = default;
    virtual bool pick(std::mt19937_64& rng, Entry& out) = 0;      // READ: uniform random entry
    virtual bool report(const uint8_t* cov, const Entry& e) = 0;  // true if cov had a new edge
    virtual void touch(std::mt19937_64& rng) = 0;                 // WRITE: ++hits of a random entry
};

namespace pool_impl {
constexpr size_t MAP_SIZE = 1 << 16, MAX_ENTRIES = 4096;

inline uint64_t word(const uint8_t* p, size_t i) {
    uint64_t w;
    memcpy(&w, p + 8 * i, 8);
    return w;
}
// Bytes [lo, hi) of cov contain an edge not yet in g. lo and hi are multiples of 8.
inline bool is_new(const uint8_t* cov, const uint8_t* g, size_t lo, size_t hi) {
    for (size_t i = lo / 8; i < hi / 8; i++)
        if (word(cov, i) & ~word(g, i)) return true;
    return false;
}
inline bool any(const uint8_t* cov, size_t lo, size_t hi) {
    for (size_t i = lo / 8; i < hi / 8; i++)
        if (word(cov, i)) return true;
    return false;
}
inline void merge(const uint8_t* cov, uint8_t* g, size_t lo, size_t hi) {
    for (size_t i = lo; i < hi; i++) g[i] |= cov[i];
}
inline size_t below(std::mt19937_64& rng, size_t n) { return std::uniform_int_distribution<size_t>(0, n - 1)(rng); }
// report() has no rng parameter; overwriting a random slot uses a per-thread generator.
inline std::mt19937_64& local_rng() {
    static thread_local std::mt19937_64 r(std::random_device{}());
    return r;
}
inline void append(std::vector<Entry>& v, const Entry& e, size_t cap = MAX_ENTRIES) {
    if (v.size() < cap) v.push_back(e);
    else v[below(local_rng(), v.size())] = e;
}

// Unsynchronised state shared by GlobalLock, RWLock and NoShare (each adds its own locking).
struct State {
    std::vector<uint8_t> map = std::vector<uint8_t>(MAP_SIZE, 0);
    std::vector<Entry> entries;
    bool pick(std::mt19937_64& rng, Entry& out) const {
        if (entries.empty()) return false;
        out = entries[below(rng, entries.size())];
        return true;
    }
    bool report(const uint8_t* cov, const Entry& e) {
        if (!is_new(cov, map.data(), 0, MAP_SIZE)) return false;
        merge(cov, map.data(), 0, MAP_SIZE);
        append(entries, e);
        return true;
    }
    void touch(std::mt19937_64& rng) {
        if (!entries.empty()) entries[below(rng, entries.size())].hits++;
    }
};
}  // namespace pool_impl

class GlobalLock : public Pool {
    std::mutex m;
    pool_impl::State s;
public:
    bool pick(std::mt19937_64& rng, Entry& out) override { std::lock_guard<std::mutex> g(m); return s.pick(rng, out); }
    bool report(const uint8_t* cov, const Entry& e) override { std::lock_guard<std::mutex> g(m); return s.report(cov, e); }
    void touch(std::mt19937_64& rng) override { std::lock_guard<std::mutex> g(m); s.touch(rng); }
    void dump(std::vector<uint8_t>& map, size_t& n) { std::lock_guard<std::mutex> g(m); map = s.map, n = s.entries.size(); }
};

class Sharded : public Pool {
    static constexpr size_t SHARDS = 16, SLICE = pool_impl::MAP_SIZE / SHARDS;
    struct alignas(64) Shard {
        std::mutex m;
        uint8_t map[SLICE] = {};
        std::vector<Entry> entries;
    };
    Shard shards[SHARDS];
    std::atomic<size_t> total{0};  // entries over all shards, kept <= MAX_ENTRIES

    template <class F> bool on_random_nonempty(std::mt19937_64& rng, F f) {
        size_t start = pool_impl::below(rng, SHARDS);
        for (size_t k = 0; k < SHARDS; k++) {
            Shard& sh = shards[(start + k) % SHARDS];
            std::lock_guard<std::mutex> g(sh.m);
            if (!sh.entries.empty()) return f(sh), true;
        }
        return false;
    }
public:
    bool pick(std::mt19937_64& rng, Entry& out) override {
        return on_random_nonempty(rng, [&](Shard& sh) { out = sh.entries[pool_impl::below(rng, sh.entries.size())]; });
    }
    bool report(const uint8_t* cov, const Entry& e) override {
        bool appended = false;
        for (size_t i = 0; i < SHARDS; i++) {
            const uint8_t* slice = cov + i * SLICE;
            if (!pool_impl::any(slice, 0, SLICE)) continue;  // lock only shards this cov touches
            Shard& sh = shards[i];
            std::lock_guard<std::mutex> g(sh.m);
            if (!pool_impl::is_new(slice, sh.map, 0, SLICE)) continue;
            pool_impl::merge(slice, sh.map, 0, SLICE);
            if (appended) continue;
            appended = true;  // e goes to the shard of its first new edge
            if (total.fetch_add(1) < pool_impl::MAX_ENTRIES) sh.entries.push_back(e);
            else {
                total.fetch_sub(1);  // full: overwrite a random slot of this shard (if it has one)
                if (!sh.entries.empty()) sh.entries[pool_impl::below(pool_impl::local_rng(), sh.entries.size())] = e;
            }
        }
        return appended;
    }
    void touch(std::mt19937_64& rng) override {
        on_random_nonempty(rng, [&](Shard& sh) { sh.entries[pool_impl::below(rng, sh.entries.size())].hits++; });
    }
    void dump(std::vector<uint8_t>& map, size_t& n) {
        map.assign(pool_impl::MAP_SIZE, 0), n = 0;
        for (size_t i = 0; i < SHARDS; i++) {
            std::lock_guard<std::mutex> g(shards[i].m);
            memcpy(map.data() + i * SLICE, shards[i].map, SLICE), n += shards[i].entries.size();
        }
    }
};

class RWLock : public Pool {
    std::shared_mutex m;
    pool_impl::State s;
public:
    bool pick(std::mt19937_64& rng, Entry& out) override { std::shared_lock<std::shared_mutex> g(m); return s.pick(rng, out); }
    bool report(const uint8_t* cov, const Entry& e) override {
        {
            std::shared_lock<std::shared_mutex> g(m);
            if (!pool_impl::is_new(cov, s.map.data(), 0, pool_impl::MAP_SIZE)) return false;
        }
        std::unique_lock<std::shared_mutex> g(m);
        return s.report(cov, e);  // checks again: another writer may have merged meanwhile
    }
    void touch(std::mt19937_64& rng) override { std::unique_lock<std::shared_mutex> g(m); s.touch(rng); }
    void dump(std::vector<uint8_t>& map, size_t& n) { std::unique_lock<std::shared_mutex> g(m); map = s.map, n = s.entries.size(); }
};

class Snapshot : public Pool {
    // Copy-on-write snapshot. Not lock-free: libstdc++ implements atomic_load/store on shared_ptr
    // with an internal spinlock table.
    using State = pool_impl::State;
    std::shared_ptr<const State> cur = std::make_shared<const State>();
    std::mutex writer;
public:
    bool pick(std::mt19937_64& rng, Entry& out) override { return std::atomic_load(&cur)->pick(rng, out); }
    bool report(const uint8_t* cov, const Entry& e) override {
        if (!pool_impl::is_new(cov, std::atomic_load(&cur)->map.data(), 0, pool_impl::MAP_SIZE)) return false;
        std::lock_guard<std::mutex> g(writer);
        auto next = std::make_shared<State>(*std::atomic_load(&cur));
        if (!next->report(cov, e)) return false;  // another writer got there first
        std::atomic_store(&cur, std::shared_ptr<const State>(std::move(next)));
        return true;
    }
    void touch(std::mt19937_64& rng) override {
        std::lock_guard<std::mutex> g(writer);
        auto snap = std::atomic_load(&cur);
        if (snap->entries.empty()) return;
        auto next = std::make_shared<State>(*snap);
        next->touch(rng);
        std::atomic_store(&cur, std::shared_ptr<const State>(std::move(next)));
    }
    void dump(std::vector<uint8_t>& map, size_t& n) {
        auto snap = std::atomic_load(&cur);
        map = snap->map, n = snap->entries.size();
    }
};

// Baseline: no locks at all; the fuzzer gives every worker its own instance.
class NoShare : public Pool {
    pool_impl::State s;
public:
    bool pick(std::mt19937_64& rng, Entry& out) override { return s.pick(rng, out); }
    bool report(const uint8_t* cov, const Entry& e) override { return s.report(cov, e); }
    void touch(std::mt19937_64& rng) override { s.touch(rng); }
    void dump(std::vector<uint8_t>& map, size_t& n) { map = s.map, n = s.entries.size(); }
};

// Non-virtual read-out of any pool's bitmap and entry count (call only after workers have joined).
inline void pool_dump(Pool& p, std::vector<uint8_t>& map, size_t& n) {
    if (auto* q = dynamic_cast<GlobalLock*>(&p)) return q->dump(map, n);
    if (auto* q = dynamic_cast<Sharded*>(&p)) return q->dump(map, n);
    if (auto* q = dynamic_cast<RWLock*>(&p)) return q->dump(map, n);
    if (auto* q = dynamic_cast<Snapshot*>(&p)) return q->dump(map, n);
    if (auto* q = dynamic_cast<NoShare*>(&p)) return q->dump(map, n);
}

inline std::unique_ptr<Pool> make_pool(const std::string& name) {
    if (name == "global") return std::make_unique<GlobalLock>();
    if (name == "sharded") return std::make_unique<Sharded>();
    if (name == "rwlock") return std::make_unique<RWLock>();
    if (name == "snapshot") return std::make_unique<Snapshot>();
    if (name == "noshare") return std::make_unique<NoShare>();
    return nullptr;
}
