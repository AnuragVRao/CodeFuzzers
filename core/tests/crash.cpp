// Test binary for core/tests/server_test.cpp: dies with SIGABRT.
// Linked with fs_runtime.o by tools/build.py so it can run under a fork server.
// Expected Server result: CRASH.
#include <cstdlib>
int main() { abort(); }
