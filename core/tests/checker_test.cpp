// Checker outcome mapping (compare.hpp checker_outcome) through the real fork-server: a fake checker
// that exits with a chosen code, one killed by a signal (crash) and one that times out (hang).
// Usage: build/tests/checker_test   (run from the repo root; uses build/tests/{exit_code,crash,hang})
// Prints PASS/FAIL per check; exit code 1 on any FAIL.
#include <cstdio>
#include <cstring>
#include <string>
#include "../compare.hpp"
#include "../server.hpp"

static int failures = 0;

static void check(const Server::Result& r, const char* want, const std::string& what) {
    const char* got = checker_outcome(r.exit_code);
    bool ok = r.kind != Server::Result::SERVER_DEAD && !strcmp(got, want);
    printf("%s  %-32s -> %-13s (kind=%d exit_code=%d)\n", ok ? "PASS" : "FAIL", what.c_str(), got, r.kind, r.exit_code);
    failures += !ok;
}

int main() {
    const std::string dir = "build/tests/";
    Server code, crash, hang;
    if (!code.start(dir + "exit_code", {"exit_code", "@SEED@"}, "/dev/null", "/dev/null", false) ||
        !crash.start(dir + "crash", {"crash"}, "/dev/null", "/dev/null", false) ||
        !hang.start(dir + "hang", {"hang"}, "/dev/null", "/dev/null", false)) {
        printf("FAIL  could not start test servers (run from the repo root after tools/build.py)\n");
        return 1;
    }
    const struct { int code; const char* want; } cases[] = {
        {0, "ok"}, {1, "WA"}, {2, "WA"}, {4, "WA"}, {8, "WA"}, {3, "ref_fail"},
        {5, "checker_error"}, {7, "checker_error"}, {16, "checker_error"}, {255, "checker_error"}};
    for (auto c : cases) check(code.run(std::to_string(c.code), "", 2000), c.want, "exit " + std::to_string(c.code));
    check(crash.run("", "", 2000), "checker_error", "killed by SIGABRT");
    check(hang.run("", "", 200), "checker_error", "timeout (SIGALRM)");

    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
