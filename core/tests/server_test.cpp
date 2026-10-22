// Exercises the Server branches that the smoke test never reaches: CRASH (signal and non-zero
// exit), TIMEOUT (with elapsed-time bounds), a server surviving killed children, and
// SERVER_DEAD after the server process itself is killed, plus the @SEED@/@SIZE@ argv placeholders.
// Usage: build/tests/server_test   (run from the repo root; uses build/tests/{crash,hang,exit3,gen_named,gen_seedonly})
// Prints PASS/FAIL per check; exit code 1 on any FAIL.
#include <csignal>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include "../server.hpp"

static int failures = 0;

static void check(bool ok, const char* what, const Server::Result& r) {
    printf("%s  %-48s (kind=%d exit_code=%d us=%d)\n", ok ? "PASS" : "FAIL", what, r.kind, r.exit_code, r.us);
    failures += !ok;
}

static std::string slurp(const std::string& path) {
    std::ifstream f(path);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

static std::string plain(const std::string& cmd) {  // stdout of a plain run
    std::string out;
    FILE* p = popen(cmd.c_str(), "r");
    for (char buf[256]; p && fgets(buf, sizeof buf, p);) out += buf;
    if (p) pclose(p);
    return out;
}

// 20 (seed, size) pairs: fork-server output must equal plain execution of the same command.
static void named_check(const std::vector<std::string>& args, const char* order, const char* what) {
    const std::string dir = "build/tests/", out = "/dev/shm/cf_server_test_out";
    Server g;
    bool ok = g.start(dir + "gen_named", args, "/dev/null", out, false);
    int bad = 0;
    for (int i = 0; ok && i < 20; i++) {
        std::string seed = std::to_string(i * 7919 + 1), n = std::to_string(i * 3 + 1);
        auto r = g.run(seed, n, 2000);
        std::string want = plain(dir + "gen_named " + (order[0] == 's' ? "--seed " + seed + " --n " + n : "--n " + n + " --seed " + seed));
        bad += r.kind != Server::Result::OK || want.empty() || slurp(out) != want;
    }
    Server::Result r{Server::Result::OK, !ok || bad, 0};
    check(ok && !bad, what, r);
}

int main() {
    const std::string dir = "build/tests/";
    using R = Server::Result;

    Server crash, exit3, hang;
    if (!crash.start(dir + "crash", {"crash"}, "/dev/null", "/dev/null", false) ||
        !exit3.start(dir + "exit3", {"exit3"}, "/dev/null", "/dev/null", false) ||
        !hang.start(dir + "hang", {"hang"}, "/dev/null", "/dev/null", false)) {
        printf("FAIL  could not start test servers (run from the repo root after tools/build.py)\n");
        return 1;
    }

    R r = crash.run("", "", 2000);
    check(r.kind == R::CRASH, "crash -> CRASH", r);

    r = exit3.run("", "", 2000);
    check(r.kind == R::CRASH && r.exit_code == 3, "exit3 -> CRASH with exit_code 3", r);

    r = hang.run("", "", 200);
    check(r.kind == R::TIMEOUT && r.us >= 150000 && r.us <= 400000, "hang (200 ms) -> TIMEOUT in 150..400 ms", r);

    r = hang.run("", "", 200);
    check(r.kind == R::TIMEOUT, "same server after a TIMEOUT -> TIMEOUT again", r);

    kill(hang.server_pid(), SIGKILL);
    waitpid(hang.server_pid(), nullptr, 0);  // make sure it is gone before the next request
    r = hang.run("", "", 200);
    check(r.kind == R::SERVER_DEAD, "server killed with SIGKILL -> SERVER_DEAD", r);

    named_check({"gen_named", "--seed", "@SEED@", "--n", "@SIZE@"}, "sn", "placeholders: --seed @SEED@ --n @SIZE@");
    named_check({"gen_named", "--n", "@SIZE@", "--seed", "@SEED@"}, "ns", "placeholders: --n @SIZE@ --seed @SEED@");

    {  // seed-only template "{seed}": output must not depend on the size
        Server g;
        const std::string out = "/dev/shm/cf_server_test_out";
        bool ok = g.start(dir + "gen_seedonly", {"gen", "@SEED@"}, "/dev/null", out, false);
        R a = g.run("42", "5", 2000);
        std::string o1 = slurp(out);
        R b = g.run("42", "999", 2000);
        std::string o2 = slurp(out);
        R c = g.run("43", "5", 2000);
        check(ok && a.kind == R::OK && b.kind == R::OK && !o1.empty() && o1 == o2 && slurp(out) != o1 && c.kind == R::OK,
              "seed-only template: same seed, any size -> same output", b);
    }
    {  // legacy: no placeholders -> argv[1]/argv[2] replaced
        Server g;
        const std::string out = "/dev/shm/cf_server_test_out";
        bool ok = g.start(dir + "gen_named", {"gen_named", "--seed", "0", "--n"}, "/dev/null", out, false);
        // argv[1]="--seed" and argv[2]="0" are replaced by a1/a2: run as "gen_named --n 3 ..." style
        R r1 = g.run("--n", "4", 2000);  // -> gen_named --n 4 --n ... (n parsed from the last pair only)
        std::string o = slurp(out);
        check(ok && r1.kind == R::OK && !o.empty() && o.substr(0, 2) == "4\n" , "legacy (no placeholders): argv[1]/argv[2] replaced", r1);
    }

    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
