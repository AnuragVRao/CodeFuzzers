// Test binary for core/tests/checker_test.cpp: exits with the code given as argv[1] (a fake checker).
// Linked with fs_runtime.o by tools/build.py so it can run under a fork server.
#include <cstdlib>
int main(int argc, char* argv[]) { return argc > 1 ? atoi(argv[1]) : 0; }
