// Test binary for core/tests/server_test.cpp: spins forever (volatile, so the loop has a side
// effect and is not undefined behaviour). Linked with fs_runtime.o by tools/build.py.
// Expected Server result: TIMEOUT once the request's timeout fires (SIGALRM).
int main() {
    volatile unsigned x = 0;
    for (;;) x = x + 1;
}
