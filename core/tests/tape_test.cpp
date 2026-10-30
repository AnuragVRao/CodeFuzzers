// Tape session tests for Dataset/common/random.h (roadmap Step 2a, docs/tape_design.md).
// Built by tools/build.py once per real generator (CF_GEN_SRC = its generator.cpp, whose main() is
// renamed cf_gen_main and linked in here) as build/tests/tape_test_<group>. Every generator run is a
// forked child (this is a test binary, not a fuzzer worker) with the session in shared memory:
//   T2 capture == v1: empty input tape gives the same output as no session (5 seeds, size 200)
//   T3 replay: the captured tape with another seed reproduces the output, consuming exactly the tape
//   T4 local mutation (toy, 20 x uniform(0, 1000)): rewriting draw 7's accepted word changes only line 7
//   T5 no shift through rejection: as T4 for a seed where draw 7 needed >= 1 rejected word
//   T6 budget: all-zero tape + fallback_zero, uniform_pair(0, 5) never ends -> budget exit within 1 s
// Usage: build/tests/tape_test_<group>   Prints PASS/FAIL per check; exit code 1 on any FAIL.
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include "random.h"

cf_tape_session* cf_session = nullptr;  // strong definition: this test links no runtime

#define main cf_gen_main
#include CF_GEN_SRC
#undef main

namespace tt {
constexpr size_t CAP = 97930, LOGCAP = 79446;  // docs/tape_design.md
struct Shared { cf_tape_session s; uint64_t in[CAP], out[CAP]; cf_draw log[LOGCAP]; };
Shared* sh;
int failures = 0;

using Tape = std::vector<uint64_t>;
struct Run {
    std::string out;
    int status;  // exit code, or -signal
    Tape tape;
    std::vector<cf_draw> log;
    uint64_t in_pos, out_len, log_len;
    uint32_t flags;
    double secs;
};

// Runs gen(seed, size) in a child; in == nullptr: no session, else a session with that input tape.
Run run(int (*gen)(int, char**), const std::string& seed, const std::string& size, const Tape* in,
        bool fallback_zero = false, uint64_t budget = 0) {
    sh->s = {sh->in, 0, 0, sh->out, CAP, 0, sh->log, LOGCAP, 0, budget, 0, fallback_zero};
    if (in) std::copy(in->begin(), in->end(), sh->in), sh->s.in_len = in->size();
    FILE* f = tmpfile();
    fflush(stdout);
    auto t0 = std::chrono::steady_clock::now();
    pid_t pid = fork();
    if (pid == 0) {
        alarm(10);  // a broken budget must not hang the test
        dup2(fileno(f), 1);
        cf_session = in ? &sh->s : nullptr;
        std::string a0 = "gen", a1 = seed, a2 = size;
        char* argv[] = {a0.data(), a1.data(), a2.data(), nullptr};
        int rc = gen(3, argv);
        fflush(stdout);
        _exit(rc);
    }
    int st = 0;
    waitpid(pid, &st, 0);
    Run r{};
    r.secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    r.status = WIFSIGNALED(st) ? -WTERMSIG(st) : WEXITSTATUS(st);
    rewind(f);
    for (int c; (c = fgetc(f)) != EOF;) r.out += char(c);
    fclose(f);
    r.in_pos = sh->s.in_pos, r.out_len = sh->s.out_len, r.log_len = sh->s.log_len, r.flags = sh->s.flags;
    if (in) {
        r.tape.assign(sh->out, sh->out + std::min<uint64_t>(r.out_len, CAP));
        r.log.assign(sh->log, sh->log + std::min<uint64_t>(r.log_len, LOGCAP));
    }
    return r;
}

void check(bool ok, const std::string& what) {
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what.c_str());
    failures += !ok;
}

std::vector<std::string> lines(const std::string& s) {
    std::vector<std::string> v;
    size_t i = 0;
    for (size_t j; (j = s.find('\n', i)) != std::string::npos; i = j + 1) v.push_back(s.substr(i, j - i));
    return v;
}

int toy20(int, char** argv) {  // 20 lines, each uniform(0, 1000): one draw per line
    Random gen(atoll(argv[1]));
    for (int i = 0; i < 20; i++) printf("%d\n", gen.uniform(0, 1000));
    return 0;
}

int toy_pair(int, char** argv) {  // with all-zero words a == b forever
    Random gen(atoll(argv[1]));
    auto [a, b] = gen.uniform_pair(0, 5);
    printf("%d %d\n", a, b);
    return 0;
}

// T4/T5: rewrite draw 7's accepted word; only line 7 may change, the tape keeps its length.
void local_mutation(const std::string& seed, const char* name) {
    Tape empty;
    Run cap = run(toy20, seed, "", &empty);
    const cf_draw d = cap.log[6];
    uint64_t old = cap.tape[d.index] & 1023, v = (old + 500) % 1001;
    Tape mut = cap.tape;
    mut[d.index] = v;  // whole word replaced, high bits zero
    Run r = run(toy20, seed, "", &mut);
    auto a = lines(cap.out), b = lines(r.out);
    int diff = 0;
    for (size_t i = 0; i < 20 && a.size() == 20 && b.size() == 20; i++) diff += a[i] != b[i];
    bool line7 = b.size() == 20 && b[6] == std::to_string(v) && a[6] == std::to_string(old);
    char msg[200];
    snprintf(msg, sizeof msg, "%s seed %s: draw 7 %llu -> %llu, %d line(s) differ (only line 7: %s), tape %llu -> %llu words",
             name, seed.c_str(), (unsigned long long)old, (unsigned long long)v, diff, line7 && diff == 1 ? "yes" : "NO",
             (unsigned long long)cap.out_len, (unsigned long long)r.out_len);
    check(cap.log.size() == 20 && line7 && diff == 1 && r.out_len == cap.out_len && r.in_pos == mut.size(), msg);
}
}  // namespace tt

int main() {
    using namespace tt;
    sh = (Shared*)mmap(nullptr, sizeof(Shared), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (sh == MAP_FAILED) return perror("mmap"), 1;
    printf("generator: %s\n", CF_GEN_SRC);

    for (const char* seed : {"1", "2", "3", "12345", "987654321"}) {
        Tape empty;
        Run v1 = run(cf_gen_main, seed, "200", nullptr);
        Run cap = run(cf_gen_main, seed, "200", &empty);
        check(!v1.out.empty() && cap.out == v1.out && cap.status == v1.status && cap.flags == 0 && cap.in_pos == 0,
              "T2 seed " + std::string(seed) + ": empty tape == no session (" + std::to_string(v1.out.size()) + " bytes, " +
              std::to_string(cap.out_len) + " words, " + std::to_string(cap.log_len) + " draws)");
        Run rep = run(cf_gen_main, std::to_string(atoll(seed) + 1000), "200", &cap.tape);
        bool same_log = rep.log.size() == cap.log.size();
        for (size_t i = 0; same_log && i < rep.log.size(); i++)
            same_log = rep.log[i].index == cap.log[i].index && rep.log[i].upper == cap.log[i].upper;
        check(rep.out == cap.out && rep.status == cap.status && rep.in_pos == cap.tape.size() &&
              rep.out_len == cap.tape.size() && same_log && rep.flags == 0,
              "T3 seed " + std::string(seed) + " replayed with seed " + std::to_string(atoll(seed) + 1000) +
              ": same output and draws, consumed exactly " + std::to_string(rep.out_len) + " words");
    }

    local_mutation("1", "T4");
    std::string rej;  // T5: first seed whose draw 7 needed at least one rejected word
    for (int s = 1; s < 100000 && rej.empty(); s++) {
        Tape empty;
        Run c = run(toy20, std::to_string(s), "", &empty);
        if (c.log.size() == 20 && c.log[6].index > c.log[5].index + 1) rej = std::to_string(s);
    }
    check(!rej.empty(), "T5 found a seed where draw 7 rejected >= 1 word: " + rej);
    if (!rej.empty()) local_mutation(rej, "T5");

    Tape zeros(16, 0);
    Run b = run(toy_pair, "1", "", &zeros, true, 1000000);
    check(b.status == CF_TAPE_BUDGET_EXIT && (b.flags & CF_TAPE_BUDGET) && b.secs < 1.0 && b.out_len == 1000001,
          "T6 all-zero tape + fallback_zero: exit " + std::to_string(b.status) + " (budget code " +
          std::to_string(CF_TAPE_BUDGET_EXIT) + ") after " + std::to_string(b.out_len) + " words in " +
          std::to_string(b.secs) + " s");

    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
