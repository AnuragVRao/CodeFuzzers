// Single-threaded end-to-end test of the fork-server pipeline (gen -> ref -> fast -> compare).
// Usage: build/smoke <problem_dir_in_build> <sol|bug> <seeds> <size> <exact|custom>
// Classifies every seed with the outcome rules in CLAUDE.md, ORs the fast binary's coverage into
// a global bitmap, and prints outcome counts, total edges, avg µs per test, and a hash of the
// coverage map of seed 1 (stable across runs only if binaries are non-PIE).
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <sys/stat.h>
#include "compare.hpp"
#include "server.hpp"

static const int TIMEOUT_MS = 5000;  // same as tools/sanity.py

int main(int argc, char** argv) {
    if (argc != 6) {
        fprintf(stderr, "usage: %s <problem_dir_in_build> <sol|bug> <seeds> <size> <exact|custom>\n", argv[0]);
        return 2;
    }
    std::string dir = argv[1], which = argv[2], size = argv[4];
    int seeds = atoi(argv[3]);
    bool custom = std::string(argv[5]) == "custom";
    std::string tmp = "/dev/shm/cf_smoke_" + std::to_string(getpid()) + "/";
    mkdir(tmp.c_str(), 0700);
    std::string in = tmp + "in", out_ref = tmp + "out_ref", out_fast = tmp + "out_fast";

    Server gen, ref, fast, checker;
    bool ok = gen.start(dir + "/gen", {"gen", "0", "0"}, "/dev/null", in, false) &&
              ref.start(dir + "/ref", {"ref"}, in, out_ref, false) &&
              fast.start(dir + (which == "sol" ? "/fast_sol" : "/fast_bug"), {"fast"}, in, out_fast, true) &&
              (!custom || checker.start(dir + "/checker", {"checker", in, out_fast, out_ref}, "/dev/null", "/dev/null", false));
    if (!ok) { fprintf(stderr, "failed to start servers in %s\n", dir.c_str()); return 1; }

    std::map<std::string, int> cnt;
    static unsigned char global_map[Server::MAP_SIZE];
    unsigned long long seed1_hash = 0;
    auto t0 = std::chrono::steady_clock::now();
    for (int seed = 1; seed <= seeds; seed++) {
        auto must = [&](Server::Result r) {
            if (r.kind == Server::Result::SERVER_DEAD) { fprintf(stderr, "server died (seed %d)\n", seed); exit(1); }
            return r;
        };
        std::string kind;
        if (must(gen.run(std::to_string(seed), size, TIMEOUT_MS)).kind != Server::Result::OK) kind = "gen_skip";
        else if (must(ref.run("", "", TIMEOUT_MS)).kind != Server::Result::OK) kind = "invalid";
        else {
            auto r = must(fast.run("", "", TIMEOUT_MS));
            for (size_t i = 0; i < Server::MAP_SIZE; i++) global_map[i] |= fast.cov_map[i];
            if (seed == 1) {  // FNV-1a over the per-run map
                seed1_hash = 1469598103934665603ULL;
                for (size_t i = 0; i < Server::MAP_SIZE; i++) seed1_hash = (seed1_hash ^ fast.cov_map[i]) * 1099511628211ULL;
            }
            if (r.kind == Server::Result::TIMEOUT) kind = "TLE";
            else if (r.kind == Server::Result::CRASH) kind = "RE";
            else if (custom) kind = must(checker.run("", "", TIMEOUT_MS)).kind == Server::Result::OK ? "ok" : "WA";
            else kind = same_tokens(out_fast, out_ref) ? "ok" : "WA";
        }
        cnt[kind]++;
    }
    double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count();
    gen.stop(), ref.stop(), fast.stop(), checker.stop();
    for (auto f : {in, out_ref, out_fast}) unlink(f.c_str());
    rmdir(tmp.c_str());

    int edges = 0;
    for (unsigned char b : global_map) edges += b != 0;
    printf("ok=%d WA=%d RE=%d TLE=%d invalid=%d gen_skip=%d  edges=%d  avg_us=%.1f  seed1_hash=%016llx\n",
           cnt["ok"], cnt["WA"], cnt["RE"], cnt["TLE"], cnt["invalid"], cnt["gen_skip"], edges, us / seeds, seed1_hash);
    return 0;
}
