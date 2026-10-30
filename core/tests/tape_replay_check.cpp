// Determinism of admitted tape entries (roadmap Step 2d T2): every entry written by
// `fuzzer --recipes tape --dump-tapes FILE` (variant size seed input_hash words w0 w1 ...) is regenerated
// through the real fork-server (gen / gen_alt of BUILD_DIR, tape session with the stored words) and the
// output must hash (compare.hpp hash_bytes) to the stored input_hash, with COMPLETE set.
// Usage: build/tests/tape_replay_check BUILD_DIR DUMP_FILE [max_entries=50]   (from the repo root)
// Prints one summary line (and each mismatch); exit code 1 on any mismatch or if nothing was checked.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "../compare.hpp"
#include "../server.hpp"

int main(int argc, char* argv[]) {
    if (argc < 3) return fprintf(stderr, "usage: %s BUILD_DIR DUMP_FILE [max_entries=50]\n", argv[0]), 2;
    std::string build = argv[1];
    size_t max = argc > 3 ? atoll(argv[3]) : 50;
    const std::string out = "/dev/shm/cf_tape_replay_check_" + std::to_string(getpid());
    const std::vector<std::string> args = {"gen", "@SEED@", "@SIZE@"};
    Server gen[2];
    bool alt = std::ifstream(build + "/gen_alt").good();
    if (!gen[0].start(build + "/gen", args, "/dev/null", out, false, true) ||
        (alt && !gen[1].start(build + "/gen_alt", args, "/dev/null", out, false, true)))
        return fprintf(stderr, "could not start generator servers in %s\n", build.c_str()), 1;
    std::ifstream in(argv[2]);
    size_t checked = 0, bad = 0, words_max = 0;
    for (std::string line; checked < max && std::getline(in, line);) {
        std::istringstream ls(line);
        int variant, size;
        unsigned long long seed, hash;
        size_t n;
        ls >> variant >> size >> seed >> hash >> n;
        std::vector<uint64_t> tape(n);
        for (auto& w : tape) ls >> w;
        if (!ls || variant < 0 || variant > int(alt)) { printf("FAIL  unreadable entry %zu\n", checked); bad++, checked++; continue; }
        GenTapeRun r = run_gen_with_tape(gen, variant, size, seed, tape.data(), n, false, 1000000);
        bool ok = r.tape.res.kind == Server::Result::OK && r.tape.complete && hash_bytes(r.out) == hash && r.tape.consumed == n;
        if (!ok)
            printf("FAIL  entry %zu (variant %d, size %d, seed %llu, %zu words): status %d, complete %d, hash %s, consumed %llu\n",
                   checked, variant, size, seed, n, r.tape.res.kind, r.tape.complete, hash_bytes(r.out) == hash ? "same" : "DIFFERENT",
                   (unsigned long long)r.tape.consumed);
        bad += !ok, checked++, words_max = std::max(words_max, n);
    }
    unlink(out.c_str());
    printf("%s  %zu admitted entries regenerated from (variant, size, seed, tape): %zu reproduce the stored input hash "
           "(longest tape %zu words)\n", bad == 0 && checked > 0 ? "PASS" : "FAIL", checked, checked - bad, words_max);
    return bad == 0 && checked > 0 ? 0 : 1;
}
