// Tape sessions through the real fork-server (roadmap Step 2b): server.hpp run_tape() /
// run_gen_with_tape(), fs_runtime.cpp fd 196. Run from the repo root after tools/build.py.
//   T2 connected_components_of_complement_graph, size 200, seeds 1..1000: capture (empty tape) ==
//      run() output, replay with another seed == capture, consuming exactly the tape; fd counts of
//      this process and the server unchanged after the 1000 rounds
//   T3 all-zero tape + fallback_zero on a never-ending uniform_pair: status BUDGET (not CRASH)
//   T5 CAP + 1000 words: run completes, overflow flag set, stdout == no-session stdout, out_len <= CAP
//   T6 one server, in order: clean, crash (100 words then abort), clean, budget, clean, overflow, clean;
//      incomplete runs show COMPLETE = 0 and none of the previous run's counters, clean runs match
//      their own no-session output
//   plus: run() on a tape server leaves the child's session null; run_tape() arms it
// Prints PASS/FAIL per check; exit code 1 on any FAIL.
#include <dirent.h>
#include <cstdio>
#include <string>
#include <vector>
#include "../server.hpp"

static int failures = 0;

static void check(bool ok, const std::string& what) {
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what.c_str());
    failures += !ok;
}

static int fd_count(pid_t pid) {
    DIR* d = opendir(("/proc/" + std::to_string(pid) + "/fd").c_str());
    int n = 0;
    if (!d) return -1;
    while (readdir(d)) n++;
    closedir(d);
    return n - 2;  // . and ..
}

static std::string slurp(const std::string& path) {
    std::string s;
    if (FILE* f = fopen(path.c_str(), "rb")) {
        char buf[1 << 16];
        for (size_t n; (n = fread(buf, 1, sizeof buf, f)) > 0;) s.append(buf, n);
        fclose(f);
    }
    return s;
}

int main() {
    using R = Server::Result;
    const std::string out = "/dev/shm/cf_tape_server_test_out";
    const std::vector<std::string> argv = {"gen", "@SEED@", "@SIZE@"};  // the fuzzer's default template
    Server gen[1], toy[1];
    if (!gen[0].start("build/connected_components_of_complement_graph/gen", argv, "/dev/null", out, false, true) ||
        !toy[0].start("build/tests/gen_tape_toy", argv, "/dev/null", out, false, true)) {
        printf("FAIL  could not start test servers (run from the repo root after tools/build.py)\n");
        return 1;
    }

    {  // T2
        int bad = 0;
        size_t max_words = 0, fd_self = 0, fd_server = 0;
        for (int seed = 1; seed <= 1000; seed++) {
            R plain = gen[0].run(std::to_string(seed), "200", 2000);
            std::string want = slurp(out);
            GenTapeRun cap = run_gen_with_tape(gen, 0, 200, seed, nullptr, 0, false);
            std::vector<uint64_t> tape(cap.tape.out, cap.tape.out + cap.tape.out_len);  // spans die with the next request
            GenTapeRun rep = run_gen_with_tape(gen, 0, 200, seed + 100000, tape.data(), tape.size(), false);
            bad += plain.kind != R::OK || cap.tape.res.kind != R::OK || cap.out != want || cap.tape.flags != Server::TAPE_COMPLETE ||
                   cap.tape.consumed != tape.size() || rep.tape.res.kind != R::OK || rep.out != cap.out ||
                   rep.tape.consumed != tape.size() || rep.tape.log_len != cap.tape.log_len || rep.tape.flags != Server::TAPE_COMPLETE;
            max_words = std::max(max_words, tape.size());
            if (seed == 1) fd_self = fd_count(getpid()), fd_server = fd_count(gen[0].server_pid());
        }
        int self_after = fd_count(getpid()), server_after = fd_count(gen[0].server_pid());
        check(bad == 0, "T2 1000 seeds: capture == run() output, replay (other seed) == capture, consumed == tape (" +
                            std::to_string(bad) + " bad, longest tape " + std::to_string(max_words) + " words)");
        check(self_after == int(fd_self) && server_after == int(fd_server),
              "T2 fd counts after round 1 -> after round 1000: worker " + std::to_string(fd_self) + " -> " +
                  std::to_string(self_after) + ", server " + std::to_string(fd_server) + " -> " + std::to_string(server_after));
    }

    {  // T3
        std::vector<uint64_t> zeros(16, 0);
        GenTapeRun b = run_gen_with_tape(toy, 0, 0, 1, zeros.data(), zeros.size(), true, 1000000);
        check(b.tape.res.kind == R::BUDGET && b.tape.res.exit_code == Server::TAPE_BUDGET_EXIT && (b.tape.flags & Server::TAPE_BUDGET),
              "T3 budget exceeded -> status BUDGET (kind " + std::to_string(b.tape.res.kind) + ", exit " +
                  std::to_string(b.tape.res.exit_code) + "), not CRASH");
        R plain = toy[0].run("1", "0", 2000);
        check(plain.kind == R::OK, "T3 same generator without a tape (run()) -> OK");
    }

    {  // T5
        const uint64_t n = Server::TAPE_CAP + 1000;
        R plain = toy[0].run("7", std::to_string(n), 5000);
        std::string want = slurp(out);
        GenTapeRun o = run_gen_with_tape(toy, 0, int(n), 7, nullptr, 0, false, 0, 5000);
        check(plain.kind == R::OK && o.tape.res.kind == R::OK && o.tape.complete && (o.tape.flags & Server::TAPE_OVERFLOW) && o.out == want &&
                  o.tape.out_len <= Server::TAPE_CAP && o.tape.log_len <= Server::TAPE_LOGCAP && o.tape.consumed == n,
              "T5 " + std::to_string(n) + " words: completes, overflow flag " + std::to_string(o.tape.flags & 1) +
                  ", stdout == no-session stdout (" + std::to_string(want.size()) + " bytes), out_len " +
                  std::to_string(o.tape.out_len) + " <= CAP " + std::to_string(Server::TAPE_CAP) + ", log_len " +
                  std::to_string(o.tape.log_len) + ", consumed " + std::to_string(o.tape.consumed));
    }

    {  // T6
        struct Step { const char* what; long long n; R::Kind kind; bool complete; uint64_t out_len, consumed; uint32_t flags; };
        const uint64_t big = Server::TAPE_CAP + 1000;
        const Step steps[] = {
            {"clean 50", 50, R::OK, true, 50, 50, Server::TAPE_COMPLETE},
            {"crash after 100 words", -2, R::CRASH, false, 0, 0, 0},
            {"clean 60", 60, R::OK, true, 60, 60, Server::TAPE_COMPLETE},
            {"budget", 0, R::BUDGET, false, 0, 0, Server::TAPE_BUDGET},
            {"clean 70", 70, R::OK, true, 70, 70, Server::TAPE_COMPLETE},
            {"overflow", (long long)big, R::OK, true, Server::TAPE_CAP, big, Server::TAPE_OVERFLOW | Server::TAPE_COMPLETE},
            {"clean 80", 80, R::OK, true, 80, 80, Server::TAPE_COMPLETE}};
        std::vector<uint64_t> zeros(16, 0);
        for (const Step& st : steps) {
            bool budget = st.kind == R::BUDGET;
            std::string want;
            if (st.n > 0) toy[0].run("9", std::to_string(st.n), 5000), want = slurp(out);
            GenTapeRun r = run_gen_with_tape(toy, 0, int(st.n), 9, budget ? zeros.data() : nullptr, budget ? zeros.size() : 0,
                                             budget, budget ? 1000000 : 0, 5000);
            bool ok = r.tape.res.kind == st.kind && r.tape.complete == st.complete && r.tape.out_len == st.out_len &&
                      r.tape.consumed == st.consumed && r.tape.flags == st.flags && (st.n <= 0 || r.out == want);
            char msg[256];
            snprintf(msg, sizeof msg, "T6 %-22s status %d, COMPLETE %d, out_len %llu, consumed %llu, flags %u%s", st.what,
                     r.tape.res.kind, r.tape.complete, (unsigned long long)r.tape.out_len, (unsigned long long)r.tape.consumed,
                     r.tape.flags, st.n > 0 ? (r.out == want ? ", stdout == no-session" : ", stdout DIFFERS") : "");
            check(ok, msg);
        }
    }

    {  // session pointer: null for run(), armed for run_tape()
        toy[0].run("1", "-1", 2000);
        std::string unarmed = slurp(out);
        GenTapeRun armed = run_gen_with_tape(toy, 0, -1, 1, nullptr, 0, false);
        check(unarmed == "session 0\n" && armed.out == "session 1\n",
              "run() on a tape server: child session null; run_tape(): armed");
    }

    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
