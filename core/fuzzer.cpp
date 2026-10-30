// Multi-threaded differential fuzzer. W worker threads each own fork servers for gen(/gen_alt),
// ref, fast (with coverage) and optionally the checker; they share one Pool of recipes (or, for
// noshare, each has its own; random has none and never mutates). Coverage = edge hit-count
// buckets: raw counts become one bit per (edge, bucket) before pool.report(). Mode "scale" runs
// exactly --tests tests in total; "hunt" stops all workers at the first bug (or --time-limit).
// --recipes random: tests use random recipes but pool traffic (pick/report/extra ops) is unchanged,
// so every strategy does equal work per test. Timed region: start barrier -> last worker done.
// JSON summary to --out, first bug to --bug-dir. A custom checker exiting with _fail ("ref_fail") or
// abnormally ("checker_error", see compare.hpp) is counted, with its first recipe, but is never a bug.
//
// v2 (docs/tape_design.md): --recipes tape (noshare or rwlock only) keeps TapeEntry recipes whose
// generator tape lives in the process-wide Arena. Every test runs the generator in a tape session
// (budget 1,000,000 words): a child copies its parent's tape and applies 1..8 draw-level operators
// (--tape-span 1: span ablation; --tape-mut byte: diagnostic byte flips), a test without a parent
// starts from an empty tape (= v1 output). Outputs equal to the parent's or to one of the worker's
// last 1024 outputs are skipped (dup_skip: generated, not executed). Admission: status OK, COMPLETE,
// no OVERFLOW, new coverage. --tape-capture 1 (random strategy only) runs every test through an
// empty tape session and never admits anything: the v2 random arm.
// --op-log FILE (diagnostics, Step 2e Part 2): one line per child (a test with a parent) listing every
// applied operator; logging reads values only and never changes RNG calls, operator choice or admission.
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
#include <type_traits>
#include <unordered_set>
#include "arena.hpp"
#include "compare.hpp"
#include "pool.hpp"
#include "server.hpp"

using Clock = std::chrono::steady_clock;

struct Config {
    std::string build, checker = "exact", fast = "sol", mode = "scale", strategy = "global", cpus, out = "fuzz.json", bug_dir = "bug";
    std::string gen_template = "{seed} {size}";  // generator argv after the program name
    std::string size_dist = "uniform";  // sizes of random recipes: uniform on 1..max_size, or log-uniform
    std::string recipes = "guided";  // guided: use picked/mutated recipes; random: pick but ignore; tape: v2
    std::string tape_mut = "draw";   // --recipes tape: draw-level operators, or "byte" (diagnostic only)
    std::string dump_tapes;          // --recipes tape: write every admitted entry (recipe + tape) here
    std::string op_log;              // write one line per child with its applied operators here
    int max_size = 200, variants = 1, workers = 1, timeout_ms = 2000, extra_ops = 0;
    int tape_span = 0, tape_capture = 0;  // span ablation (tape recipes); empty-tape capture (random strategy)
    long long arena_mb = 1024;  // tape arena size (--recipes tape only; no arena is created otherwise)
    long long tests = 1000, seed = 1;
    double time_limit = 60, write_frac = 0;
};
constexpr uint64_t TAPE_BUDGET = 1000000;  // words per generator run (docs/tape_design.md)

enum Op { VALUE, NUDGE, COPY, SIZE, SPAN, BYTE, OPS };
static const char* const OP_NAMES[OPS] = {"value", "nudge", "copy", "size", "span", "byte"};

struct alignas(64) Stats {
    long long tests = 0, ok = 0, WA = 0, RE = 0, TLE = 0, invalid = 0, gen_skip = 0, news = 0, size_sum = 0;
    long long ref_fail = 0, checker_error = 0;
    long long dup_skip = 0, budget = 0, overflow = 0, mutated = 0, mut_changed = 0;  // tape sessions
    long long op_applied[OPS] = {}, op_children[OPS] = {}, op_changed[OPS] = {};      // per operator
    std::atomic<long long> executed{0};  // tests that ran ref; summed by record_bug() (other threads)
    Clock::time_point end;
};

struct FirstBug {
    bool found = false;
    double time_s = 0;
    long long tests_before = 0, executed_before = 0;
    int worker = 0, variant = 0, size = 0;
    uint64_t seed = 0;
    std::string kind;
};

struct FirstNote {  // first ref_fail / checker_error: recorded for inspection, never stops a run
    bool found = false;
    int worker = 0, variant = 0, size = 0;
    uint64_t seed = 0;
};

// Per-worker set of the last N generator-output hashes: hash set + ring buffer, FIFO eviction.
// Only hashes not already present are inserted, so the ring holds no duplicates.
struct RecentHashes {
    static constexpr size_t N = 1024;
    std::unordered_set<uint64_t> set;
    std::vector<uint64_t> ring = std::vector<uint64_t>(N);
    size_t next = 0;
    bool contains(uint64_t h) const { return set.count(h) > 0; }
    void insert(uint64_t h) {
        if (set.size() == N) set.erase(ring[next]);
        ring[next] = h, next = (next + 1) % N;
        set.insert(h);
    }
};

static Config cfg;
static std::vector<std::unique_ptr<Pool>> pools;  // 1 shared, 1 per worker (noshare), none (random)
static std::vector<std::unique_ptr<BasicPool<TapeEntry>>> tape_pools;  // the same, for --recipes tape
static std::unique_ptr<Arena> arena;               // tape words + draw logs (--recipes tape); null otherwise
static std::vector<std::vector<TapeEntry>> admitted;  // per worker, only with --dump-tapes
static std::vector<std::string> op_lines;            // per worker, only with --op-log
static std::vector<std::vector<uint8_t>> seen;      // random only: per-worker OR of class maps
static std::unique_ptr<Stats[]> stats;
static std::atomic<long long> started{0}, completed{0};
static std::atomic<bool> stop_flag{false}, failed{false};
static std::mutex bar_m, bug_m;
static std::condition_variable bar_cv;
static int arrived = 0;
static bool go = false;
static Clock::time_point t0;
static FirstBug first_bug;
static FirstNote first_ref_fail, first_checker_error;

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

// tape: the generator's input tape (--recipes tape), saved as tape.bin (raw uint64 words).
template <class E>
static void record_bug(int w, const E& r, const std::string& kind, const std::string& input, const std::vector<uint64_t>* tape) {
    std::lock_guard<std::mutex> g(bug_m);
    if (first_bug.found) return;
    long long executed = 0;
    for (int i = 0; i < cfg.workers; i++) executed += stats[i].executed.load(std::memory_order_relaxed);
    first_bug = {true, std::chrono::duration<double>(Clock::now() - t0).count(), completed.load(), executed, w,
                 r.variant, r.size, r.seed, kind};
    mkdir(cfg.bug_dir.c_str(), 0755);
    std::ifstream src(input, std::ios::binary);
    std::ofstream(cfg.bug_dir + "/input.txt", std::ios::binary) << src.rdbuf();
    std::ofstream rec(cfg.bug_dir + "/recipe.txt");
    rec << "variant " << int(r.variant) << "\nsize " << r.size << "\nseed " << r.seed << "\nkind " << kind << "\nworker " << w << "\n";
    if (tape) {
        rec << "tape_words " << tape->size() << "\n";
        std::ofstream(cfg.bug_dir + "/tape.bin", std::ios::binary).write((const char*)tape->data(), 8 * tape->size());
    }
}

template <class E> static void record_note(FirstNote& n, int w, const E& r) {
    std::lock_guard<std::mutex> g(bug_m);
    if (!n.found) n = {true, w, r.variant, r.size, r.seed};
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

static const double factors[] = {0.5, 0.8, 1, 1, 1.25, 2};  // v1 size-factor op

// One applied operator for --op-log: draw ops (value, nudge, copy, span) a = draw index, b = old value, c = new
// value (span: one record per draw); byte: a = word index, b = old word, c = new word; size: a = old size,
// b = new size, factor = the size factor.
struct OpRec {
    Op op;
    uint64_t a, b, c;
    double factor;
};

static std::string op_text(const std::vector<OpRec>& recs) {
    std::string s;
    char buf[96];
    for (const OpRec& o : recs) {
        if (o.op == SIZE) snprintf(buf, sizeof buf, " size:%llu:%llu:%g", (unsigned long long)o.a, (unsigned long long)o.b, o.factor);
        else snprintf(buf, sizeof buf, " %s:%llu:%llu:%llu", OP_NAMES[o.op], (unsigned long long)o.a, (unsigned long long)o.b, (unsigned long long)o.c);
        s += buf;
    }
    return s;
}

static uint64_t mask_of(uint64_t upper) {  // as in random.h next(upper)
    if (!(upper & (upper + 1))) return upper;
    int lg = 63 - __builtin_clzll(upper);
    return lg == 63 ? ~0ULL : (1ULL << (lg + 1)) - 1;
}
static uint64_t upto(std::mt19937_64& rng, uint64_t upper) {  // uniform in [0, upper]
    return upper == ~0ULL ? rng() : std::uniform_int_distribution<uint64_t>(0, upper)(rng);
}

// Child tape t (a copy of the parent's output tape) with the parent's draw log (n draws); may change
// size. Applies m = min(8, 1 + Geometric(0.5)) operators (docs/tape_design.md, Mutation); returns the
// set of operators actually applied (bit per Op) and counts each application in st.op_applied.
// A draw write replaces the WHOLE accepted word with v; a draw's value is word & mask(upper).
// rec (--op-log only, else null) receives every write; recording never calls rng.
static unsigned mutate(std::vector<uint64_t>& t, const TapeDraw* log, size_t n, uint16_t& size, std::mt19937_64& rng,
                       Stats& st, std::vector<OpRec>* rec) {
    unsigned applied = 0;
    auto apply = [&](Op op) { st.op_applied[op]++, applied |= 1u << op; };
    if (cfg.tape_mut == "byte") {  // diagnostic: one random byte of one random word
        if (!t.empty()) {
            size_t i = rng() % t.size();
            uint64_t& x = t[i];
            uint64_t old = x;
            int b = int(rng() % 8);
            x = (x & ~(0xFFULL << (8 * b))) | ((rng() & 0xFF) << (8 * b));
            if (rec) rec->push_back({BYTE, i, old, x, 0});
        }
        apply(BYTE);
        return applied;
    }
    auto val = [&](size_t d) { return t[log[d].index] & mask_of(log[d].upper); };
    auto value_op = [&] {  // new value in [0, upper], different from the old one if upper > 0
        size_t d = rng() % n;
        uint64_t up = log[d].upper, old = val(d), v = 0;
        if (up > 0) v = upto(rng, up - 1), v += v >= old;
        t[log[d].index] = v;
        if (rec) rec->push_back({VALUE, d, old, v, 0});
        apply(VALUE);
    };
    int m = std::min(8, 1 + std::geometric_distribution<int>(0.5)(rng));
    for (int k = 0; k < m; k++) {
        int u = int(rng() % 100);
        if (n == 0 || u >= 90) {  // size (also the only possible op when the parent made no draws)
            double factor = factors[rng() % 6], s = std::llround(size * factor);
            uint16_t old = size;
            size = uint16_t(std::min<double>(std::max<double>(s, 1), cfg.max_size));
            if (rec) rec->push_back({SIZE, old, size, 0, factor});
            apply(SIZE);
        } else if (cfg.tape_span && u >= 40 && u < 50) {  // span: L = 1 + Geometric(mean 8) draws -> 0 or upper
            size_t d = rng() % n, len = 1 + std::geometric_distribution<int>(1.0 / 9)(rng);
            bool top = rng() & 1;
            for (size_t j = d; j < n && j < d + len; j++) {
                uint64_t old = val(j);
                t[log[j].index] = top ? log[j].upper : 0;
                if (rec) rec->push_back({SPAN, j, old, t[log[j].index], 0});
            }
            apply(SPAN);
        } else if (u < 50) {
            value_op();
        } else if (u < 75) {  // nudge by +-k, k in 1..16, clamped to [0, upper]
            size_t d = rng() % n;
            uint64_t up = log[d].upper, old = val(d), k1 = 1 + rng() % 16;
            t[log[d].index] = (rng() & 1) ? (old > up - std::min(up, k1) ? up : old + k1) : (old < k1 ? 0 : old - k1);
            if (rec) rec->push_back({NUDGE, d, old, t[log[d].index], 0});
            apply(NUDGE);
        } else {  // copy val(d1) into d2 if it fits; up to 4 retries of d2, then a value op
            size_t d1 = rng() % n;
            uint64_t v = val(d1);
            bool done = false;
            for (int tries = 0; tries < 5 && !done; tries++) {
                size_t d2 = rng() % n;
                if (v <= log[d2].upper) {
                    if (rec) rec->push_back({COPY, d2, val(d2), v, 0});
                    t[log[d2].index] = v, done = true;
                }
            }
            if (done) apply(COPY);
            else value_op();
        }
    }
    return applied;
}

template <class E> static BasicPool<E>* pool_of(int w) {
    auto& v = [&]() -> auto& { if constexpr (std::is_same_v<E, TapeEntry>) return tape_pools; else return pools; }();
    return cfg.strategy == "random" ? nullptr : v[cfg.strategy == "noshare" ? w : 0].get();
}

template <class E> static void worker(int w, std::vector<int> cpus) {
    constexpr bool TAPE = std::is_same_v<E, TapeEntry>;
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
    const bool session = TAPE || cfg.tape_capture;  // the generator runs in a tape session
    Server gen[2], ref, fast, checker;
    std::vector<std::string> gargv;
    gen_argv(cfg.gen_template, gargv);  // validated in main
    bool ok = gen[0].start(cfg.build + "/gen", gargv, "/dev/null", in, false, session) &&
              (cfg.variants < 2 || gen[1].start(cfg.build + "/gen_alt", gargv, "/dev/null", in, false, session)) &&
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
    BasicPool<E>* pool = pool_of<E>(w);
    std::vector<uint8_t> cls(pool_impl::MAP_SIZE);
    Stats& st = stats[w];
    std::mt19937_64 rng(cfg.seed * 1000003ULL + w);
    const int T = cfg.timeout_ms;
    std::vector<uint64_t> tape;  // the generator's input tape (empty without a parent)
    std::string output;          // generator output (tape recipes: for the dedup hash)
    RecentHashes recent;
    std::vector<OpRec> recs;  // --op-log: this child's applied operators
    const bool oplog = !cfg.op_log.empty();
    auto dead = [&](const Server::Result& r) {
        if (r.kind != Server::Result::SERVER_DEAD) return false;
        fprintf(stderr, "worker %d: server died\n", w), failed = stop_flag = true;
        return true;
    };
    auto random_recipe = [&](E& r) {
        r.variant = uint8_t(rng() % cfg.variants);
        if (cfg.size_dist == "log") {  // size = clamp(round(exp(U ln max)), 1, max), U in [0, 1)
            double u = (rng() >> 11) * (1.0 / 9007199254740992.0);
            r.size = uint16_t(std::min<double>(std::max<double>(std::llround(std::exp(u * std::log(double(cfg.max_size)))), 1), cfg.max_size));
        } else {
            r.size = uint16_t(1 + rng() % cfg.max_size);
        }
    };
    while (ok && !stop_flag) {
        if (cfg.mode == "scale" && started.fetch_add(1) >= cfg.tests) break;
        if (cfg.mode == "hunt" && std::chrono::duration<double>(Clock::now() - t0).count() > cfg.time_limit) break;
        E r{}, picked{};  // a. recipe (random mode still picks, so pool traffic is identical)
        bool use = pool && std::bernoulli_distribution(0.9)(rng) && pool->pick(rng, picked);
        unsigned ops = 0;
        recs.clear();
        if constexpr (TAPE) {
            tape.clear();
            if (use) {  // child: the parent's variant and tape, mutated
                r = picked;
                tape.assign(arena->words(picked.tape), arena->words(picked.tape) + picked.tape.words);
                ops = mutate(tape, arena->draws(picked.tape), picked.tape.draws, r.size, rng, st, oplog ? &recs : nullptr);
            } else {
                random_recipe(r);
            }
        } else if (use && cfg.recipes == "guided") {
            r = picked;
            double factor = factors[rng() % 6], s = std::llround(r.size * factor);
            uint16_t old = r.size;
            r.size = uint16_t(std::min<double>(std::max<double>(s, 1), cfg.max_size));
            if (oplog) recs.push_back({SIZE, old, r.size, 0, factor});
        } else {
            random_recipe(r);
        }
        r.seed = rng() >> 1, r.hits = 0;
        st.tests++, st.size_sum += r.size;
        std::string kind;
        Server::Result g;  // b
        Server::TapeResult tr{};
        if (session) {
            tr = gen[r.variant].run_tape(std::to_string(r.seed), std::to_string(r.size), T, tape.data(), tape.size(), false, TAPE_BUDGET);
            g = tr.res;
            st.budget += g.kind == Server::Result::BUDGET;
            st.overflow += (tr.flags & Server::TAPE_OVERFLOW) != 0;
        } else {
            g = gen[r.variant].run(std::to_string(r.seed), std::to_string(r.size), T);
        }
        if (dead(g)) break;
        uint64_t hash = 0;
        if (g.kind != Server::Result::OK) kind = "gen_skip";
        else if constexpr (TAPE) {  // dedup against the parent's output and the worker's recent outputs
            read_file(in, output);
            hash = hash_bytes(output);
            if (use) {
                bool changed = hash != picked.tape.input_hash;
                st.mutated++, st.mut_changed += changed;
                for (int op = 0; op < OPS; op++)
                    if (ops >> op & 1) st.op_children[op]++, st.op_changed[op] += changed;
            }
            if ((use && hash == picked.tape.input_hash) || recent.contains(hash)) kind = "dup_skip";
            else recent.insert(hash);
        }
        if (oplog && use && (TAPE || cfg.recipes == "guided")) {  // child line: parent, child, hashes (tape only), ops
            char head[256];
            uint64_t parent_hash = 0;
            if constexpr (TAPE) parent_hash = picked.tape.input_hash;
            bool ok_gen = g.kind == Server::Result::OK;
            snprintf(head, sizeof head, "%llu parent %d %d %llu %s child %d %llu %s %s ops %zu", (unsigned long long)st.tests,
                     picked.variant, picked.size, (unsigned long long)picked.seed,
                     TAPE ? std::to_string(parent_hash).c_str() : "-", r.size, (unsigned long long)r.seed,
                     TAPE && ok_gen ? std::to_string(hash).c_str() : "-", TAPE && ok_gen ? (hash != parent_hash ? "1" : "0") : "-",
                     recs.size());
            op_lines[w] += std::to_string(w) + " " + head + op_text(recs) + "\n";
        }
        if (kind.empty()) {
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
                    kind = checker_outcome(cr.exit_code);  // ref_fail / checker_error are not bugs
                } else kind = same_tokens(out_fast, out_ref) ? "ok" : "WA";
                to_classes(fast.cov_map, cls.data());
                if (!pool) {  // random: no guidance, just remember what was covered
                    for (size_t i = 0; i < cls.size(); i++) seen[w][i] |= cls[i];
                } else {
                    if constexpr (TAPE) {  // e: admission rule, copy into the arena only if it will be admitted
                        bool admissible = tr.complete && !(tr.flags & Server::TAPE_OVERFLOW);
                        if (admissible && pool->novel(cls.data()) &&
                            arena->store(tr.out, uint32_t(tr.out_len), tr.log, uint32_t(tr.log_len), hash, r.tape) &&
                            pool->report(cls.data(), r)) {
                            st.news++;
                            if (!cfg.dump_tapes.empty()) admitted[w].push_back(r);
                        }
                    } else if (pool->report(cls.data(), r)) {
                        st.news++;  // e
                    }
                    E scratch;  // f (must not clobber r)
                    for (int k = 0; k < cfg.extra_ops; k++) {
                        if (std::bernoulli_distribution(cfg.write_frac)(rng)) pool->touch(rng);
                        else pool->pick(rng, scratch);
                    }
                }
            }
        }
        if (kind == "WA" || kind == "RE" || kind == "TLE") {  // g
            record_bug(w, r, kind, in, TAPE ? &tape : nullptr);
            if (cfg.mode == "hunt") stop_flag = true;
        }
        if (kind == "ref_fail") record_note(first_ref_fail, w, r);
        if (kind == "checker_error") record_note(first_checker_error, w, r);
        (kind == "ok" ? st.ok : kind == "WA" ? st.WA : kind == "RE" ? st.RE : kind == "TLE" ? st.TLE
                       : kind == "invalid" ? st.invalid : kind == "ref_fail" ? st.ref_fail
                       : kind == "checker_error" ? st.checker_error : kind == "dup_skip" ? st.dup_skip : st.gen_skip)++;
        if (kind != "gen_skip" && kind != "dup_skip") st.executed.fetch_add(1, std::memory_order_relaxed);
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

// --dump-tapes: one line per admitted entry: variant size seed input_hash words w0 w1 ... (decimal)
static bool dump_tapes() {
    FILE* f = fopen(cfg.dump_tapes.c_str(), "w");
    if (!f) return perror(cfg.dump_tapes.c_str()), false;
    for (auto& v : admitted)
        for (const TapeEntry& e : v) {
            fprintf(f, "%d %d %llu %llu %u", e.variant, e.size, (unsigned long long)e.seed,
                    (unsigned long long)e.tape.input_hash, e.tape.words);
            const uint64_t* words = arena->words(e.tape);
            for (uint32_t i = 0; i < e.tape.words; i++) fprintf(f, " %llu", (unsigned long long)words[i]);
            fprintf(f, "\n");
        }
    fclose(f);
    return true;
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
    S("--gen-template", cfg.gen_template), S("--size-dist", cfg.size_dist), S("--tape-mut", cfg.tape_mut), S("--dump-tapes", cfg.dump_tapes);
    S("--op-log", cfg.op_log);
    {
        std::vector<std::string> tmp;
        if (!gen_argv(cfg.gen_template, tmp)) return 2;
    }
    I("--max-size", cfg.max_size), I("--variants", cfg.variants), I("--workers", cfg.workers), I("--tests", cfg.tests);
    I("--seed", cfg.seed), I("--extra-ops", cfg.extra_ops), I("--timeout-ms", cfg.timeout_ms), I("--arena-mb", cfg.arena_mb);
    I("--tape-span", cfg.tape_span), I("--tape-capture", cfg.tape_capture);
    D("--time-limit", cfg.time_limit), D("--write-frac", cfg.write_frac);
    const bool tape = cfg.recipes == "tape";
    if (cfg.size_dist != "uniform" && cfg.size_dist != "log") { fprintf(stderr, "--size-dist uniform|log\n"); return 2; }
    if (cfg.recipes != "guided" && cfg.recipes != "random" && !tape) { fprintf(stderr, "--recipes guided|random|tape\n"); return 2; }
    if (cfg.strategy != "random" && !make_pool(cfg.strategy)) { fprintf(stderr, "unknown strategy %s\n", cfg.strategy.c_str()); return 2; }
    if (tape && cfg.strategy != "noshare" && cfg.strategy != "rwlock") {
        fprintf(stderr, "--recipes tape needs --strategy noshare or rwlock (the only strategies stress-tested with tapes), not %s\n",
                cfg.strategy.c_str());
        return 2;
    }
    if (cfg.tape_mut != "draw" && cfg.tape_mut != "byte") { fprintf(stderr, "--tape-mut draw|byte\n"); return 2; }
    if (!tape && (cfg.tape_span || cfg.tape_mut != "draw" || !cfg.dump_tapes.empty())) {
        fprintf(stderr, "--tape-span, --tape-mut and --dump-tapes need --recipes tape\n");
        return 2;
    }
    if (cfg.tape_capture && cfg.strategy != "random") { fprintf(stderr, "--tape-capture needs --strategy random\n"); return 2; }
    std::vector<int> cpus;
    std::stringstream cs(cfg.cpus);
    for (std::string t; std::getline(cs, t, ',');) if (!t.empty()) cpus.push_back(std::stoi(t));

    mkdir(("/dev/shm/cf_" + std::to_string(getpid())).c_str(), 0700);
    int n_pools = cfg.strategy == "noshare" ? cfg.workers : 1;
    if (cfg.strategy == "random") seen.assign(cfg.workers, std::vector<uint8_t>(pool_impl::MAP_SIZE, 0));
    else if (tape)
        for (int i = 0; i < n_pools; i++) tape_pools.push_back(make_pool<TapeEntry>(cfg.strategy));
    else
        for (int i = 0; i < n_pools; i++) pools.push_back(make_pool(cfg.strategy));
    if (tape) {
        arena = std::make_unique<Arena>(size_t(cfg.arena_mb) << 20);
        if (!arena->capacity()) { fprintf(stderr, "could not reserve a %lld MiB arena\n", cfg.arena_mb); return 1; }
        admitted.resize(cfg.workers);
    }
    stats = std::make_unique<Stats[]>(cfg.workers);
    op_lines.resize(cfg.workers);
    std::vector<std::thread> ts;
    for (int w = 0; w < cfg.workers; w++) ts.emplace_back(tape ? worker<TapeEntry> : worker<Entry>, w, cpus);
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
    long long executed = 0;
    for (int w = 0; w < cfg.workers; w++) {
        Stats& s = stats[w];
        t1 = std::max(t1, s.end);
        tot.tests += s.tests, tot.size_sum += s.size_sum, tot.ok += s.ok, tot.WA += s.WA, tot.RE += s.RE, tot.TLE += s.TLE;
        tot.invalid += s.invalid, tot.gen_skip += s.gen_skip, tot.news += s.news;
        tot.ref_fail += s.ref_fail, tot.checker_error += s.checker_error;
        tot.dup_skip += s.dup_skip, tot.budget += s.budget, tot.overflow += s.overflow;
        tot.mutated += s.mutated, tot.mut_changed += s.mut_changed;
        for (int op = 0; op < OPS; op++)
            tot.op_applied[op] += s.op_applied[op], tot.op_children[op] += s.op_children[op], tot.op_changed[op] += s.op_changed[op];
        executed += s.executed.load();
    }
    double wall = std::chrono::duration<double>(t1 - t0).count();
    std::vector<uint8_t> all(pool_impl::MAP_SIZE, 0), m;
    size_t entries = 0, n;
    auto add = [&](auto& p) {
        pool_dump(*p, m, n), entries += n;
        for (size_t i = 0; i < m.size(); i++) all[i] |= m[i];
    };
    for (auto& p : pools) add(p);
    for (auto& p : tape_pools) add(p);
    for (auto& s : seen)
        for (size_t i = 0; i < s.size(); i++) all[i] |= s[i];
    int cov_features = 0;  // distinct (edge, hit-bucket) pairs
    for (uint8_t b : all) cov_features += __builtin_popcount(b);
    if (!cfg.dump_tapes.empty() && !dump_tapes()) return 1;
    if (!cfg.op_log.empty()) {  // worker by worker, each in test order
        FILE* lf = fopen(cfg.op_log.c_str(), "w");
        if (!lf) return perror(cfg.op_log.c_str()), 1;
        fprintf(lf, "# worker test parent variant size seed input_hash child size seed input_hash changed ops n op:a:b:c...\n");
        for (auto& lines : op_lines) fputs(lines.c_str(), lf);
        fclose(lf);
    }

    FILE* f = fopen(cfg.out.c_str(), "w");
    if (!f) { perror(cfg.out.c_str()); return 1; }
    fprintf(f, "{\n  \"config\": {\"build\": \"%s\", \"checker\": \"%s\", \"max_size\": %d, \"variants\": %d, "
               "\"fast\": \"%s\", \"mode\": \"%s\", \"strategy\": \"%s\", \"workers\": %d, \"tests\": %lld, "
               "\"time_limit\": %g, \"seed\": %lld, \"extra_ops\": %d, \"write_frac\": %g, \"cpus\": \"%s\", "
               "\"timeout_ms\": %d, \"recipes\": \"%s\", \"out\": \"%s\", \"bug_dir\": \"%s\", \"gen_template\": \"%s\", \"size_dist\": \"%s\", "
               "\"arena_mb\": %lld, \"tape_mut\": \"%s\", \"tape_span\": %d, \"tape_capture\": %d, \"op_log\": \"%s\"},\n",
            esc(cfg.build).c_str(), cfg.checker.c_str(), cfg.max_size, cfg.variants, cfg.fast.c_str(), cfg.mode.c_str(),
            cfg.strategy.c_str(), cfg.workers, cfg.tests, cfg.time_limit, cfg.seed, cfg.extra_ops, cfg.write_frac,
            cfg.cpus.c_str(), cfg.timeout_ms, cfg.recipes.c_str(), esc(cfg.out).c_str(), esc(cfg.bug_dir).c_str(), esc(cfg.gen_template).c_str(),
            cfg.size_dist.c_str(), cfg.arena_mb, cfg.tape_mut.c_str(), cfg.tape_span, cfg.tape_capture, esc(cfg.op_log).c_str());
    fprintf(f, "  \"wall_s\": %.4f, \"tests\": %lld, \"tests_per_sec\": %.1f, \"mean_size\": %.2f,\n", wall,
            tot.tests, tot.tests / wall, tot.tests ? double(tot.size_sum) / tot.tests : 0.0);
    fprintf(f, "  \"outcomes\": {\"ok\": %lld, \"WA\": %lld, \"RE\": %lld, \"TLE\": %lld, \"invalid\": %lld, \"gen_skip\": %lld, "
               "\"ref_fail\": %lld, \"checker_error\": %lld},\n",
            tot.ok, tot.WA, tot.RE, tot.TLE, tot.invalid, tot.gen_skip, tot.ref_fail, tot.checker_error);
    fprintf(f, "  \"generated\": %lld, \"executed\": %lld, \"dup_skip\": %lld, \"gen_budget_exceeded\": %lld, \"tape_overflow\": %lld,\n",
            tot.tests, executed, tot.dup_skip, tot.budget, tot.overflow);
    fprintf(f, "  \"mutated\": %lld, \"mut_changed\": %lld, \"mut_changed_input\": ", tot.mutated, tot.mut_changed);
    if (tot.mutated) fprintf(f, "%.4f", double(tot.mut_changed) / tot.mutated);
    else fprintf(f, "null");
    fprintf(f, ",\n  \"ops\": {");
    for (int op = 0; op < OPS; op++)
        fprintf(f, "%s\"%s\": {\"applied\": %lld, \"children\": %lld, \"changed\": %lld}", op ? ", " : "", OP_NAMES[op],
                tot.op_applied[op], tot.op_children[op], tot.op_changed[op]);
    fprintf(f, "},\n  \"arena_bytes\": %zu, \"arena_full\": %llu,\n", arena ? arena->bytes() : 0,
            (unsigned long long)(arena ? arena->arena_full() : 0));  // peak (the arena is append-only)
    fprintf(f, "  \"new_cov_reports\": %lld, \"cov_features\": %d, \"pool_entries\": %zu,\n  \"per_worker_tests\": [",
            tot.news, cov_features, entries);
    for (int w = 0; w < cfg.workers; w++) fprintf(f, "%s%lld", w ? ", " : "", stats[w].tests);
    fprintf(f, "],\n  \"first_bug\": ");
    if (!first_bug.found) fprintf(f, "null");
    else
        fprintf(f, "{\"time_s\": %.4f, \"tests_before\": %lld, \"executed_before\": %lld, \"worker\": %d, \"kind\": \"%s\", "
                   "\"variant\": %d, \"size\": %d, \"seed\": %llu}",
                first_bug.time_s, first_bug.tests_before, first_bug.executed_before, first_bug.worker, first_bug.kind.c_str(),
                first_bug.variant, first_bug.size, (unsigned long long)first_bug.seed);
    for (auto [name, n] : {std::pair<const char*, FirstNote*>{"first_ref_fail", &first_ref_fail}, {"first_checker_error", &first_checker_error}}) {
        fprintf(f, ",\n  \"%s\": ", name);
        if (!n->found) fprintf(f, "null");
        else fprintf(f, "{\"worker\": %d, \"variant\": %d, \"size\": %d, \"seed\": %llu}", n->worker, n->variant, n->size,
                     (unsigned long long)n->seed);
    }
    fprintf(f, "\n}\n");
    fclose(f);
    return failed ? 1 : 0;
}
