// Multi-threaded differential fuzzer. W worker threads each own fork servers for gen(/gen_alt),
// ref, fast (with coverage) and optionally the checker; they share one Pool of recipes (or, for
// noshare, each has its own; random has none and never mutates). Coverage = edge hit-count
// buckets: raw counts become one bit per (edge, bucket) before pool.report(). Mode "scale" runs
// exactly --tests tests in total; "hunt" stops all workers at the first bug (or --time-limit).
// --recipes random: tests use random recipes but pool traffic (pick/report/extra ops) is unchanged,
// so every strategy does equal work per test. Timed region: start barrier -> last worker done.
// JSON summary to --out, first bug to --bug-dir.
#include <pthread.h>
#include <sched.h>
#include <sys/stat.h>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <thread>
#include "compare.hpp"
#include "pool.hpp"
#include "server.hpp"

using Clock = std::chrono::steady_clock;

struct Config {
    std::string build, checker = "exact", fast = "sol", mode = "scale", strategy = "global", cpus, out = "fuzz.json", bug_dir = "bug";
    std::string gen_template = "{seed} {size}";  // generator argv after the program name
    std::string size_dist = "uniform";  // sizes of random recipes: uniform on 1..max_size, or log-uniform
    std::string recipes = "guided";  // guided: use picked/mutated recipes; random: pick but ignore
    int max_size = 200, variants = 1, workers = 1, timeout_ms = 2000, extra_ops = 0;
    long long tests = 1000, seed = 1;
    double time_limit = 60, write_frac = 0;
};

struct alignas(64) Stats {
    long long tests = 0, ok = 0, WA = 0, RE = 0, TLE = 0, invalid = 0, gen_skip = 0, news = 0, size_sum = 0;
    Clock::time_point end;
};

struct FirstBug {
    bool found = false;
    double time_s = 0;
    long long tests_before = 0;
    int worker = 0, variant = 0, size = 0;
    uint64_t seed = 0;
    std::string kind;
};

static Config cfg;
static std::vector<std::unique_ptr<Pool>> pools;  // 1 shared, 1 per worker (noshare), none (random)
static std::vector<std::vector<uint8_t>> seen;      // random only: per-worker OR of class maps
static std::vector<Stats> stats;
static std::atomic<long long> started{0}, completed{0};
static std::atomic<bool> stop_flag{false}, failed{false};
static std::mutex bar_m, bug_m;
static std::condition_variable bar_cv;
static int arrived = 0;
static bool go = false;
static Clock::time_point t0;
static FirstBug first_bug;

// AFL-style hit-count buckets {1},{2},{3},{4-7},{8-15},{16-31},{32-127},{128+} -> bits 0..7.
static const struct Buckets {
    uint8_t lut[256];
    Buckets() {
        const int lo[] = {1, 2, 3, 4, 8, 16, 32, 128, 256};
        lut[0] = 0;
        for (int b = 0; b < 8; b++)
            for (int c = lo[b]; c < lo[b + 1]; c++) lut[c] = uint8_t(1 << b);
    }
} buckets;

// raw counts -> class map. Zero words (almost all of them) are just cleared.
static void to_classes(const uint8_t* raw, uint8_t* cls) {
    for (size_t i = 0; i < pool_impl::MAP_SIZE; i += 8) {
        uint64_t w;
        memcpy(&w, raw + i, 8);
        if (!w) { memset(cls + i, 0, 8); continue; }
        for (size_t j = i; j < i + 8; j++) cls[j] = buckets.lut[raw[j]];
    }
}

static void record_bug(int w, const Entry& r, const std::string& kind, const std::string& input) {
    std::lock_guard<std::mutex> g(bug_m);
    if (first_bug.found) return;
    first_bug = {true, std::chrono::duration<double>(Clock::now() - t0).count(), completed.load(), w,
                 r.variant, r.size, r.seed, kind};
    mkdir(cfg.bug_dir.c_str(), 0755);
    std::ifstream src(input, std::ios::binary);
    std::ofstream(cfg.bug_dir + "/input.txt", std::ios::binary) << src.rdbuf();
    std::ofstream(cfg.bug_dir + "/recipe.txt") << "variant " << int(r.variant) << "\nsize " << r.size << "\nseed "
                                               << r.seed << "\nkind " << kind << "\nworker " << w << "\n";
}

// {seed}/{size} tokens -> @SEED@/@SIZE@ (see fs_runtime.cpp); false if a token only contains one.
static bool gen_argv(const std::string& tmpl, std::vector<std::string>& argv) {
    argv = {"gen"};
    std::stringstream ss(tmpl);
    for (std::string t; ss >> t;) {
        if (t == "{seed}") t = "@SEED@";
        else if (t == "{size}") t = "@SIZE@";
        else if (t.find("{seed}") != std::string::npos || t.find("{size}") != std::string::npos) {
            fprintf(stderr, "--gen-template: token '%s' must be exactly {seed} or {size}, not contain it\n", t.c_str());
            return false;
        }
        argv.push_back(t);
    }
    return true;
}

static void worker(int w, std::vector<int> cpus) {
    if (!cpus.empty()) {  // pin BEFORE spawning servers so they inherit this CPU
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(cpus[w % cpus.size()], &set);
        pthread_setaffinity_np(pthread_self(), sizeof set, &set);
    }
    std::string dir = "/dev/shm/cf_" + std::to_string(getpid()) + "/w" + std::to_string(w) + "/";
    mkdir(dir.c_str(), 0700);
    std::string in = dir + "in", out_ref = dir + "out_ref", out_fast = dir + "out_fast";
    bool custom = cfg.checker == "custom";
    Server gen[2], ref, fast, checker;
    std::vector<std::string> gargv;
    gen_argv(cfg.gen_template, gargv);  // validated in main
    bool ok = gen[0].start(cfg.build + "/gen", gargv, "/dev/null", in, false) &&
              (cfg.variants < 2 || gen[1].start(cfg.build + "/gen_alt", gargv, "/dev/null", in, false)) &&
              ref.start(cfg.build + "/ref", {"ref"}, in, out_ref, false) &&
              fast.start(cfg.build + (cfg.fast == "sol" ? "/fast_sol" : "/fast_bug"), {"fast"}, in, out_fast, true) &&
              (!custom || checker.start(cfg.build + "/checker", {"checker", in, out_fast, out_ref}, "/dev/null", "/dev/null", false));
    if (!ok) fprintf(stderr, "worker %d: failed to start servers\n", w), failed = true;

    {  // start barrier; main records t0 once everyone has arrived
        std::unique_lock<std::mutex> lk(bar_m);
        arrived++;
        bar_cv.notify_all();
        bar_cv.wait(lk, [] { return go; });
    }
    Pool* pool = cfg.strategy == "random" ? nullptr : pools[cfg.strategy == "noshare" ? w : 0].get();
    std::vector<uint8_t> cls(pool_impl::MAP_SIZE);
    Stats& st = stats[w];
    std::mt19937_64 rng(cfg.seed * 1000003ULL + w);
    const double factors[] = {0.5, 0.8, 1, 1, 1.25, 2};
    const int T = cfg.timeout_ms;
    auto dead = [&](const Server::Result& r) {
        if (r.kind != Server::Result::SERVER_DEAD) return false;
        fprintf(stderr, "worker %d: server died\n", w), failed = stop_flag = true;
        return true;
    };
    while (ok && !stop_flag) {
        if (cfg.mode == "scale" && started.fetch_add(1) >= cfg.tests) break;
        if (cfg.mode == "hunt" && std::chrono::duration<double>(Clock::now() - t0).count() > cfg.time_limit) break;
        Entry r{}, picked{};  // a. recipe (random mode still picks, so pool traffic is identical)
        bool use = pool && std::bernoulli_distribution(0.9)(rng) && pool->pick(rng, picked);
        if (use && cfg.recipes == "guided") {
            r = picked;
            double s = std::llround(r.size * factors[rng() % 6]);
            r.size = uint16_t(std::min<double>(std::max<double>(s, 1), cfg.max_size));
        } else {
            r.variant = uint8_t(rng() % cfg.variants);
            if (cfg.size_dist == "log") {  // size = clamp(round(exp(U ln max)), 1, max), U in [0, 1)
                double u = (rng() >> 11) * (1.0 / 9007199254740992.0);
                r.size = uint16_t(std::min<double>(std::max<double>(std::llround(std::exp(u * std::log(double(cfg.max_size)))), 1), cfg.max_size));
            } else {
                r.size = uint16_t(1 + rng() % cfg.max_size);
            }
        }
        r.seed = rng() >> 1, r.hits = 0;
        st.tests++, st.size_sum += r.size;
        std::string kind;
        auto g = gen[r.variant].run(std::to_string(r.seed), std::to_string(r.size), T);  // b
        if (dead(g)) break;
        if (g.kind != Server::Result::OK) kind = "gen_skip";
        else {
            auto rr = ref.run("", "", T);  // c
            if (dead(rr)) break;
            if (rr.kind != Server::Result::OK) kind = "invalid";
            else {
                auto fr = fast.run("", "", T);  // d
                if (dead(fr)) break;
                if (fr.kind == Server::Result::TIMEOUT) kind = "TLE";
                else if (fr.kind == Server::Result::CRASH) kind = "RE";
                else if (custom) {
                    auto cr = checker.run("", "", T);
                    if (dead(cr)) break;
                    kind = cr.kind == Server::Result::OK ? "ok" : "WA";
                } else kind = same_tokens(out_fast, out_ref) ? "ok" : "WA";
                to_classes(fast.cov_map, cls.data());
                if (!pool) {  // random: no guidance, just remember what was covered
                    for (size_t i = 0; i < cls.size(); i++) seen[w][i] |= cls[i];
                } else {
                    if (pool->report(cls.data(), r)) st.news++;  // e
                    Entry scratch;                                // f (must not clobber r)
                    for (int k = 0; k < cfg.extra_ops; k++) {
                        if (std::bernoulli_distribution(cfg.write_frac)(rng)) pool->touch(rng);
                        else pool->pick(rng, scratch);
                    }
                }
            }
        }
        if (kind == "WA" || kind == "RE" || kind == "TLE") {  // g
            record_bug(w, r, kind, in);
            if (cfg.mode == "hunt") stop_flag = true;
        }
        (kind == "ok" ? st.ok : kind == "WA" ? st.WA : kind == "RE" ? st.RE : kind == "TLE" ? st.TLE
                       : kind == "invalid" ? st.invalid : st.gen_skip)++;
        completed++;
    }
    st.end = Clock::now();  // timed region ends here; servers stop below (destructors)
    for (Server* s : {&gen[0], &gen[1], &ref, &fast, &checker}) s->stop();
    for (auto f : {in, out_ref, out_fast}) unlink(f.c_str());
    rmdir(dir.c_str());
}

static std::string esc(const std::string& s) {
    std::string o;
    for (char c : s) o += (c == '"' || c == '\\') ? std::string("\\") + c : std::string(1, c);
    return o;
}

int main(int argc, char** argv) {
    std::map<std::string, std::string> raw;
    for (int i = 1; i + 1 < argc; i += 2) raw[argv[i]] = argv[i + 1];
    if (argc % 2 == 0 || !raw.count("--build")) {
        fprintf(stderr, "usage: %s --build DIR [--flag value]... (see core/fuzzer.cpp)\n", argv[0]);
        return 2;
    }
    auto S = [&](const char* k, std::string& v) { if (raw.count(k)) v = raw[k]; };
    auto I = [&](const char* k, auto& v) { if (raw.count(k)) v = std::stoll(raw[k]); };
    auto D = [&](const char* k, double& v) { if (raw.count(k)) v = std::stod(raw[k]); };
    S("--build", cfg.build), S("--checker", cfg.checker), S("--fast", cfg.fast), S("--mode", cfg.mode);
    S("--recipes", cfg.recipes), S("--strategy", cfg.strategy), S("--cpus", cfg.cpus), S("--out", cfg.out), S("--bug-dir", cfg.bug_dir);
    S("--gen-template", cfg.gen_template), S("--size-dist", cfg.size_dist);
    {
        std::vector<std::string> tmp;
        if (!gen_argv(cfg.gen_template, tmp)) return 2;
    }
    I("--max-size", cfg.max_size), I("--variants", cfg.variants), I("--workers", cfg.workers), I("--tests", cfg.tests);
    I("--seed", cfg.seed), I("--extra-ops", cfg.extra_ops), I("--timeout-ms", cfg.timeout_ms);
    D("--time-limit", cfg.time_limit), D("--write-frac", cfg.write_frac);
    if (cfg.size_dist != "uniform" && cfg.size_dist != "log") { fprintf(stderr, "--size-dist uniform|log\n"); return 2; }
    if (cfg.recipes != "guided" && cfg.recipes != "random") { fprintf(stderr, "--recipes guided|random\n"); return 2; }
    if (cfg.strategy != "random" && !make_pool(cfg.strategy)) { fprintf(stderr, "unknown strategy %s\n", cfg.strategy.c_str()); return 2; }
    std::vector<int> cpus;
    std::stringstream cs(cfg.cpus);
    for (std::string t; std::getline(cs, t, ',');) if (!t.empty()) cpus.push_back(std::stoi(t));

    mkdir(("/dev/shm/cf_" + std::to_string(getpid())).c_str(), 0700);
    if (cfg.strategy == "random") seen.assign(cfg.workers, std::vector<uint8_t>(pool_impl::MAP_SIZE, 0));
    else
        for (int i = 0; i < (cfg.strategy == "noshare" ? cfg.workers : 1); i++) pools.push_back(make_pool(cfg.strategy));
    stats.resize(cfg.workers);
    std::vector<std::thread> ts;
    for (int w = 0; w < cfg.workers; w++) ts.emplace_back(worker, w, cpus);
    {
        std::unique_lock<std::mutex> lk(bar_m);
        bar_cv.wait(lk, [] { return arrived == cfg.workers; });
        t0 = Clock::now(), go = true;
    }
    bar_cv.notify_all();
    for (auto& t : ts) t.join();
    rmdir(("/dev/shm/cf_" + std::to_string(getpid())).c_str());

    Clock::time_point t1 = t0;
    Stats tot;
    for (auto& s : stats) {
        t1 = std::max(t1, s.end);
        tot.tests += s.tests, tot.size_sum += s.size_sum, tot.ok += s.ok, tot.WA += s.WA, tot.RE += s.RE, tot.TLE += s.TLE;
        tot.invalid += s.invalid, tot.gen_skip += s.gen_skip, tot.news += s.news;
    }
    double wall = std::chrono::duration<double>(t1 - t0).count();
    std::vector<uint8_t> all(pool_impl::MAP_SIZE, 0), m;
    size_t entries = 0, n;
    for (auto& p : pools) {
        pool_dump(*p, m, n), entries += n;
        for (size_t i = 0; i < m.size(); i++) all[i] |= m[i];
    }
    for (auto& s : seen)
        for (size_t i = 0; i < s.size(); i++) all[i] |= s[i];
    int cov_features = 0;  // distinct (edge, hit-bucket) pairs
    for (uint8_t b : all) cov_features += __builtin_popcount(b);

    FILE* f = fopen(cfg.out.c_str(), "w");
    if (!f) { perror(cfg.out.c_str()); return 1; }
    fprintf(f, "{\n  \"config\": {\"build\": \"%s\", \"checker\": \"%s\", \"max_size\": %d, \"variants\": %d, "
               "\"fast\": \"%s\", \"mode\": \"%s\", \"strategy\": \"%s\", \"workers\": %d, \"tests\": %lld, "
               "\"time_limit\": %g, \"seed\": %lld, \"extra_ops\": %d, \"write_frac\": %g, \"cpus\": \"%s\", "
               "\"timeout_ms\": %d, \"recipes\": \"%s\", \"out\": \"%s\", \"bug_dir\": \"%s\", \"gen_template\": \"%s\", \"size_dist\": \"%s\"},\n",
            esc(cfg.build).c_str(), cfg.checker.c_str(), cfg.max_size, cfg.variants, cfg.fast.c_str(), cfg.mode.c_str(),
            cfg.strategy.c_str(), cfg.workers, cfg.tests, cfg.time_limit, cfg.seed, cfg.extra_ops, cfg.write_frac,
            cfg.cpus.c_str(), cfg.timeout_ms, cfg.recipes.c_str(), esc(cfg.out).c_str(), esc(cfg.bug_dir).c_str(), esc(cfg.gen_template).c_str(), cfg.size_dist.c_str());
    fprintf(f, "  \"wall_s\": %.4f, \"tests\": %lld, \"tests_per_sec\": %.1f, \"mean_size\": %.2f,\n", wall,
            tot.tests, tot.tests / wall, tot.tests ? double(tot.size_sum) / tot.tests : 0.0);
    fprintf(f, "  \"outcomes\": {\"ok\": %lld, \"WA\": %lld, \"RE\": %lld, \"TLE\": %lld, \"invalid\": %lld, \"gen_skip\": %lld},\n",
            tot.ok, tot.WA, tot.RE, tot.TLE, tot.invalid, tot.gen_skip);
    fprintf(f, "  \"new_cov_reports\": %lld, \"cov_features\": %d, \"pool_entries\": %zu,\n  \"per_worker_tests\": [",
            tot.news, cov_features, entries);
    for (int w = 0; w < cfg.workers; w++) fprintf(f, "%s%lld", w ? ", " : "", stats[w].tests);
    fprintf(f, "],\n  \"first_bug\": ");
    if (!first_bug.found) fprintf(f, "null");
    else
        fprintf(f, "{\"time_s\": %.4f, \"tests_before\": %lld, \"worker\": %d, \"kind\": \"%s\", \"variant\": %d, "
                   "\"size\": %d, \"seed\": %llu}",
                first_bug.time_s, first_bug.tests_before, first_bug.worker, first_bug.kind.c_str(), first_bug.variant,
                first_bug.size, (unsigned long long)first_bug.seed);
    fprintf(f, "\n}\n");
    fclose(f);
    return failed ? 1 : 0;
}
