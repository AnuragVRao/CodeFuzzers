// Exercises the Server branches that the smoke test never reaches: CRASH (signal and non-zero
// exit), TIMEOUT (with elapsed-time bounds), a server surviving killed children, and
// SERVER_DEAD after the server process itself is killed.
// Usage: build/tests/server_test   (run from the repo root; uses build/tests/{crash,hang,exit3})
// Prints PASS/FAIL per check; exit code 1 on any FAIL.
#include <csignal>
#include <cstdio>
#include <string>
#include "../server.hpp"

static int failures = 0;

static void check(bool ok, const char* what, const Server::Result& r) {
    printf("%s  %-48s (kind=%d exit_code=%d us=%d)\n", ok ? "PASS" : "FAIL", what, r.kind, r.exit_code, r.us);
    failures += !ok;
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

    printf("%s\n", failures ? "SOME CHECKS FAILED" : "ALL CHECKS PASSED");
    return failures ? 1 : 0;
}
