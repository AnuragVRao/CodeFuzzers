// Tape arena + TapeEntry pool stress test (roadmap Step 2c T3). For each strategy (default rwlock and
// sharded), T threads run for S seconds; each iteration either admits (random tape of 1..2000 words
// with words/2 draws, hashed; a sparse random coverage map; novel() -> Arena::store() -> report()) or
// picks an entry and re-hashes its tape and draw log from the arena, which must equal the recorded
// input_hash. A small arena (default 64 MiB) also exercises arena_full. Built plain and with TSan.
// Usage: build/tests/arena_test [seconds=10] [threads=20] [arena_mb=64] [strategies=rwlock,sharded]
// Prints one line per strategy; exit code 1 on any hash mismatch or if nothing was admitted/picked.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include "../arena.hpp"

static uint64_t mix(uint64_t h, uint64_t x) {  // splitmix64-style combine
    h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    h ^= h >> 31, h *= 0xbf58476d1ce4e5b9ULL, h ^= h >> 29;
    return h;
}
static uint64_t tape_hash(const uint64_t* w, uint32_t nw, const TapeDraw* d, uint32_t nd) {
    uint64_t h = mix(nw, nd);
    for (uint32_t i = 0; i < nw; i++) h = mix(h, w[i]);
    for (uint32_t i = 0; i < nd; i++) h = mix(mix(h, d[i].index), d[i].upper);
    return h;
}

struct Counts { std::atomic<long long> admitted{0}, lost{0}, full{0}, picked{0}, bad{0}, touched{0}; };

static void worker(BasicPool<TapeEntry>& pool, Arena& arena, Counts& c, uint64_t seed, double seconds) {
    std::mt19937_64 rng(seed);
    std::vector<uint8_t> cov(pool_impl::MAP_SIZE);
    std::vector<uint64_t> words;
    std::vector<TapeDraw> draws;
    auto end = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
    while (std::chrono::steady_clock::now() < end) {
        uint64_t r = rng() % 100;
        if (r < 30) {  // admit
            std::fill(cov.begin(), cov.end(), 0);
            for (int k = 0; k < 4; k++) cov[rng() % cov.size()] |= uint8_t(1 << (rng() % 8));
            if (!pool.novel(cov.data())) continue;
            uint32_t nw = 1 + rng() % 2000, nd = nw / 2;
            words.resize(nw), draws.resize(nd);
            for (auto& w : words) w = rng();
            for (uint32_t i = 0; i < nd; i++) draws[i] = {2 * i + 1, rng()};
            TapeEntry e{uint8_t(rng() % 2), uint16_t(1 + rng() % 200), rng(), 0, {}};
            if (!arena.store(words.data(), nw, draws.data(), nd, tape_hash(words.data(), nw, draws.data(), nd), e.tape)) {
                c.full++;
                continue;
            }
            (pool.report(cov.data(), e) ? c.admitted : c.lost)++;  // lost: another thread merged cov first
        } else if (r < 35) {
            pool.touch(rng), c.touched++;
        } else {
            TapeEntry e;
            if (!pool.pick(rng, e)) continue;
            c.picked++;
            if (tape_hash(arena.words(e.tape), e.tape.words, arena.draws(e.tape), e.tape.draws) != e.tape.input_hash) c.bad++;
        }
    }
}

int main(int argc, char* argv[]) {
    double seconds = argc > 1 ? atof(argv[1]) : 10;
    int threads = argc > 2 ? atoi(argv[2]) : 20;
    size_t arena_mb = argc > 3 ? atoll(argv[3]) : 64;
    std::string list = argc > 4 ? argv[4] : "rwlock,sharded";
    int failures = 0;
    std::stringstream ss(list);
    for (std::string strategy; std::getline(ss, strategy, ',');) {
        auto pool = make_pool<TapeEntry>(strategy);
        if (!pool) return fprintf(stderr, "unknown strategy %s\n", strategy.c_str()), 2;
        Arena arena(arena_mb << 20);
        Counts c;
        std::vector<std::thread> ts;
        for (int t = 0; t < threads; t++) ts.emplace_back(worker, std::ref(*pool), std::ref(arena), std::ref(c), 1000 + t, seconds);
        for (auto& t : ts) t.join();
        std::vector<uint8_t> map;
        size_t entries = 0;
        pool_dump(*pool, map, entries);
        bool ok = c.bad == 0 && c.admitted > 0 && c.picked > 0;
        failures += !ok;
        ok = ok && c.full == (long long)arena.arena_full();
        printf("%s  %-8s %d threads %.0f s, arena %zu MiB: admitted %lld, lost race %lld, arena_full %lld, arena bytes %zu; "
               "picked %lld (hash mismatches %lld), touched %lld, pool entries %zu\n",
               ok ? "PASS" : "FAIL", strategy.c_str(), threads, seconds, arena_mb, c.admitted.load(), c.lost.load(),
               (long long)arena.arena_full(), arena.bytes(), c.picked.load(), c.bad.load(), c.touched.load(), entries);
    }
    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
