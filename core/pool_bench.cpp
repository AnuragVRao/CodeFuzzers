// Benchmarks the shared pool alone (no processes). Each thread loops: build a synthetic coverage
// map (140 edges from a fixed "common" set of 200 indices + 10 from 20000 "rare" indices),
// report() it with a random Entry, then do K extra ops (touch() with probability F, else pick()).
// Usage: build/pool_bench --strategy S --threads 1,2,4 --seconds 2 --extra-ops K --write-frac F
//        build/pool_bench --check   (4 threads x 1 s per sharing strategy; verifies bitmap + entries)
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <thread>
#include "pool.hpp"

using pool_impl::MAP_SIZE;

struct Synthetic {  // the fixed index sets, identical for every thread and run
    std::vector<uint32_t> common, rare;
    Synthetic() {
        std::mt19937_64 r(12345);
        for (int i = 0; i < 200; i++) common.push_back(r() % MAP_SIZE);
        for (int i = 0; i < 20000; i++) rare.push_back(r() % MAP_SIZE);
    }
};

struct alignas(64) Counters { uint64_t tests = 0, news = 0; };

// One worker. If `seen` is given, ORs every reported map into it (for --check).
// If news_limit > 0, a thread stops once the shared new-report counter reaches it (--check phase 1).
static void worker(Pool& pool, const Synthetic& syn, uint64_t seed, int extra_ops, double write_frac,
                   const std::atomic<bool>& stop, Counters& c, std::vector<uint8_t>* seen,
                   std::atomic<size_t>* news_total, size_t news_limit) {
    std::mt19937_64 rng(seed);
    std::vector<uint8_t> cov(MAP_SIZE, 0);
    std::vector<uint32_t> set;
    std::bernoulli_distribution is_write(write_frac);
    Entry e;
    while (!stop.load(std::memory_order_relaxed) && !(news_limit && *news_total >= news_limit)) {
        set.clear();
        for (int i = 0; i < 140; i++) set.push_back(syn.common[rng() % syn.common.size()]);
        for (int i = 0; i < 10; i++) set.push_back(syn.rare[rng() % syn.rare.size()]);
        for (uint32_t i : set) cov[i] = 1;
        Entry r{uint8_t(rng() % 2), uint16_t(1 + rng() % 200), rng(), 0};
        if (pool.report(cov.data(), r)) c.news++, ++*news_total;
        if (seen)
            for (uint32_t i : set) (*seen)[i] = 1;
        for (uint32_t i : set) cov[i] = 0;
        for (int k = 0; k < extra_ops; k++) {
            if (is_write(rng)) pool.touch(rng);
            else pool.pick(rng, e);
        }
        c.tests++;
    }
}

// Runs `threads` workers for `seconds`; returns elapsed seconds.
static double run(std::vector<Pool*> pools, const Synthetic& syn, int threads, double seconds, int extra_ops,
                  double write_frac, std::vector<Counters>& cnt, std::vector<std::vector<uint8_t>>* seen,
                  size_t news_limit = 0) {
    std::atomic<bool> stop{false};
    std::atomic<size_t> news_total{0};
    std::vector<std::thread> ts;
    auto t0 = std::chrono::steady_clock::now();
    for (int t = 0; t < threads; t++)
        ts.emplace_back(worker, std::ref(*pools[t]), std::cref(syn), 1000 + t, extra_ops, write_frac,
                        std::cref(stop), std::ref(cnt[t]), seen ? &(*seen)[t] : nullptr, &news_total, news_limit);
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
    stop = true;
    for (auto& t : ts) t.join();
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

// Phase "below cap": stop at 3000 new reports, so entries must equal new reports exactly.
// Phase "full 1 s": runs past the 4096 cap, so entries must equal the cap.
template <class P> static bool check(const char* name, const char* phase, const Synthetic& syn, size_t limit) {
    const int T = 4;
    P pool;
    std::vector<Counters> cnt(T);
    std::vector<std::vector<uint8_t>> seen(T, std::vector<uint8_t>(MAP_SIZE, 0));
    run(std::vector<Pool*>(T, &pool), syn, T, 1.0, 5, 0.3, cnt, &seen, limit);
    std::vector<uint8_t> want(MAP_SIZE, 0), got;
    for (auto& s : seen)
        for (size_t i = 0; i < MAP_SIZE; i++) want[i] |= s[i];
    size_t entries = 0, news = 0, tests = 0;
    for (auto& c : cnt) news += c.news, tests += c.tests;
    pool.dump(got, entries);
    bool map_ok = got == want, entries_ok = entries == std::min(news, pool_impl::MAX_ENTRIES);
    printf("%-8s %-10s %s  bitmap==OR(reported): %s  entries=%zu new_reports=%zu (cap %zu): %s  [%zu tests]\n", name,
           phase, map_ok && entries_ok ? "PASS" : "FAIL", map_ok ? "yes" : "NO", entries, news, pool_impl::MAX_ENTRIES,
           entries_ok ? "ok" : "MISMATCH", tests);
    return map_ok && entries_ok;
}

int main(int argc, char** argv) {
    std::string strategy = "global", threads_arg = "1";
    double seconds = 2, write_frac = 0;
    int extra_ops = 0;
    bool do_check = false;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
        if (a == "--strategy") strategy = val();
        else if (a == "--threads") threads_arg = val();
        else if (a == "--seconds") seconds = atof(val().c_str());
        else if (a == "--extra-ops") extra_ops = atoi(val().c_str());
        else if (a == "--write-frac") write_frac = atof(val().c_str());
        else if (a == "--check") do_check = true;
        else { fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
    }
    Synthetic syn;
    if (do_check) {
        bool ok = true;
        for (auto [phase, limit] : {std::pair<const char*, size_t>{"below-cap", 3000}, {"full-1s", 0}}) {
            ok = check<GlobalLock>("global", phase, syn, limit) && ok;
            ok = check<Sharded>("sharded", phase, syn, limit) && ok;
            ok = check<RWLock>("rwlock", phase, syn, limit) && ok;
            ok = check<Snapshot>("snapshot", phase, syn, limit) && ok;
        }
        printf("%s\n", ok ? "ALL PASS" : "SOME FAILED");
        return ok ? 0 : 1;
    }
    if (!make_pool(strategy)) { fprintf(stderr, "unknown strategy %s\n", strategy.c_str()); return 2; }
    std::stringstream ss(threads_arg);
    for (std::string tok; std::getline(ss, tok, ',');) {
        int threads = atoi(tok.c_str());
        std::vector<std::unique_ptr<Pool>> owned;  // one shared pool, or one per thread for noshare
        std::vector<Pool*> pools;
        for (int t = 0; t < threads; t++) {
            if (t == 0 || strategy == "noshare") owned.push_back(make_pool(strategy));
            pools.push_back(owned.back().get());
        }
        std::vector<Counters> cnt(threads);
        double el = run(pools, syn, threads, seconds, extra_ops, write_frac, cnt, nullptr);
        uint64_t tests = 0, news = 0;
        for (auto& c : cnt) tests += c.tests, news += c.news;
        printf("%s,%d,%d,%g,%.0f,%llu\n", strategy.c_str(), threads, extra_ops, write_frac, tests / el,
               (unsigned long long)news);
        fflush(stdout);
    }
    return 0;
}
