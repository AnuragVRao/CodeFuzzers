// Step 2e Part 2 (docs/v2_pilot_plan.md): mutation diagnostics on a fixed parent set. Parents come from a
// --dump-tapes file (variant size seed input_hash words w0 ...); each is regenerated with its tape (output hash
// must equal the stored input_hash, else exit 1), which also gives its draw log. Then, per mode, N children:
// parent i = uniform draw from a parent stream seeded --seed (the SAME parent sequence in every mode); the child
// is made with a mutation stream seeded --seed * 1000003 + mode index:
//   guided: v1 guided child: the parent's variant, size x factor (v1 size-factor op), fresh seed, plain run
//   byte:   tape child, --tape-mut byte (one random byte of one random word), fresh seed, tape session
//   draw:   tape child, draw-level operators (core/mutate.hpp), fresh seed, tape session
// Children use the same budget as the fuzzer (1,000,000 words). No ref/fast runs, no pool, no admission.
// Output in --out DIR (all text):
//   parents.tsv              idx variant size seed input_hash words draws
//   parents.out              per parent: "idx bytes\n" then its generator output
//   <mode>.tsv               i parent variant size seed status complete hash changed ops n op:a:b:c ... (op-log format)
//   <mode>.out               per child with status OK: "i bytes\n" then its generator output
// status: 0 OK, 1 crash/exit != 0, 2 timeout, 4 budget exceeded; complete/hash/changed are "-" when not OK.
// Usage: build/part2 --build DIR [--variants 1] [--max-size 200] --parents FILE [--modes guided,byte,draw]
//                    [--children 2000] --seed S --out DIR
#include <sys/stat.h>
#include <cstdio>
#include <fstream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>
#include "compare.hpp"
#include "mutate.hpp"
#include "server.hpp"

struct Parent {
    int variant, size;
    uint64_t seed, hash;
    std::vector<uint64_t> words;
    std::vector<TapeDraw> draws;
    std::string out;
};

static void framed(FILE* f, size_t i, const std::string& s) {
    fprintf(f, "%zu %zu\n", i, s.size());
    fwrite(s.data(), 1, s.size(), f);
}

int main(int argc, char** argv) {
    std::map<std::string, std::string> a = {{"--variants", "1"}, {"--max-size", "200"}, {"--modes", "guided,byte,draw"},
                                            {"--children", "2000"}};
    for (int i = 1; i + 1 < argc; i += 2) a[argv[i]] = argv[i + 1];
    for (const char* k : {"--build", "--parents", "--seed", "--out"})
        if (!a.count(k)) return fprintf(stderr, "missing %s (usage in core/part2.cpp)\n", k), 2;
    const std::string build = a["--build"], dir = a["--out"];
    const int variants = std::stoi(a["--variants"]), max_size = std::stoi(a["--max-size"]);
    const long long children = std::stoll(a["--children"]);
    const uint64_t seed = std::stoull(a["--seed"]), budget = 1000000;
    mkdir(dir.c_str(), 0755);

    const std::string out = "/dev/shm/cf_part2_" + std::to_string(getpid());
    const std::vector<std::string> args = {"gen", "@SEED@", "@SIZE@"};
    Server gen[2];
    if (!gen[0].start(build + "/gen", args, "/dev/null", out, false, true) ||
        (variants > 1 && !gen[1].start(build + "/gen_alt", args, "/dev/null", out, false, true)))
        return fprintf(stderr, "could not start generator servers in %s\n", build.c_str()), 1;

    std::vector<Parent> parents;  // load and regenerate every parent
    std::ifstream pin(a["--parents"]);
    for (std::string line; std::getline(pin, line);) {
        std::istringstream ls(line);
        Parent p;
        size_t n;
        ls >> p.variant >> p.size >> p.seed >> p.hash >> n;
        p.words.resize(n);
        for (auto& w : p.words) ls >> w;
        if (!ls || p.variant < 0 || p.variant >= variants) return fprintf(stderr, "bad parent line %zu\n", parents.size()), 1;
        GenTapeRun r = run_gen_with_tape(gen, p.variant, p.size, p.seed, p.words.data(), n, false, budget);
        if (r.tape.res.kind != Server::Result::OK || !r.tape.complete || hash_bytes(r.out) != p.hash || r.tape.consumed != n)
            return fprintf(stderr, "parent %zu does not reproduce its stored output hash\n", parents.size()), 1;
        p.draws.assign(r.tape.log, r.tape.log + r.tape.log_len);
        p.out = r.out;
        parents.push_back(std::move(p));
    }
    if (parents.empty()) return fprintf(stderr, "no parents in %s\n", a["--parents"].c_str()), 1;
    FILE* pt = fopen((dir + "/parents.tsv").c_str(), "w");
    FILE* po = fopen((dir + "/parents.out").c_str(), "wb");
    fprintf(pt, "idx variant size seed input_hash words draws\n");
    for (size_t i = 0; i < parents.size(); i++) {
        const Parent& p = parents[i];
        fprintf(pt, "%zu %d %d %llu %llu %zu %zu\n", i, p.variant, p.size, (unsigned long long)p.seed, (unsigned long long)p.hash,
                p.words.size(), p.draws.size());
        framed(po, i, p.out);
    }
    fclose(pt), fclose(po);

    const std::vector<std::string> mode_names = {"guided", "byte", "draw"};
    std::stringstream ms(a["--modes"]);
    for (std::string mode; std::getline(ms, mode, ',');) {
        int mode_id = -1;
        for (int k = 0; k < 3; k++) if (mode == mode_names[k]) mode_id = k;
        if (mode_id < 0) return fprintf(stderr, "unknown mode %s (guided|byte|draw)\n", mode.c_str()), 2;
        std::mt19937_64 prng(seed), rng(seed * 1000003ULL + mode_id);  // parent stream: identical in every mode
        MutCfg mc;
        mc.byte = mode == "byte", mc.max_size = max_size;
        long long op_applied[OPS] = {};
        FILE* ct = fopen((dir + "/" + mode + ".tsv").c_str(), "w");
        FILE* co = fopen((dir + "/" + mode + ".out").c_str(), "wb");
        fprintf(ct, "i parent variant size seed status complete hash changed ops n op:a:b:c...\n");
        for (long long i = 0; i < children; i++) {
            size_t pi = prng() % parents.size();
            const Parent& p = parents[pi];
            uint16_t size = uint16_t(p.size);
            std::vector<OpRec> recs;
            std::string text;
            Server::Result res;
            bool complete = true;
            uint64_t child_seed;
            if (mode == "guided") {  // as core/fuzzer.cpp's guided branch: size factor, then a fresh seed
                double factor = factors[rng() % 6], s = std::llround(size * factor);
                uint16_t old = size;
                size = uint16_t(std::min<double>(std::max<double>(s, 1), max_size));
                recs.push_back({SIZE, old, size, 0, factor});
                child_seed = rng() >> 1;
                res = gen[p.variant].run(std::to_string(child_seed), std::to_string(size), 2000);
                if (res.kind == Server::Result::OK) read_file(gen[p.variant].out_path, text);
            } else {  // as core/fuzzer.cpp's tape branch: mutate the parent's tape, then a fresh seed
                std::vector<uint64_t> tape = p.words;
                mutate(tape, p.draws.data(), p.draws.size(), size, rng, mc, op_applied, &recs);
                child_seed = rng() >> 1;
                GenTapeRun r = run_gen_with_tape(gen, p.variant, size, child_seed, tape.data(), tape.size(), false, budget);
                res = r.tape.res, complete = r.tape.complete, text = r.out;
            }
            if (res.kind == Server::Result::SERVER_DEAD) return fprintf(stderr, "generator server died\n"), 1;
            bool ok = res.kind == Server::Result::OK;
            uint64_t h = ok ? hash_bytes(text) : 0;
            fprintf(ct, "%lld %zu %d %d %llu %d %s %s %s ops %zu%s\n", i, pi, p.variant, size, (unsigned long long)child_seed,
                    int(res.kind), ok ? (complete ? "1" : "0") : "-", ok ? std::to_string(h).c_str() : "-",
                    ok ? (h != p.hash ? "1" : "0") : "-", recs.size(), op_text(recs).c_str());
            if (ok) framed(co, size_t(i), text);
        }
        fclose(ct), fclose(co);
    }
    unlink(out.c_str());
    return 0;
}
