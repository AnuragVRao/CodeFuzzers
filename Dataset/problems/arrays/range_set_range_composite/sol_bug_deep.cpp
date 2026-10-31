// v3 deep bug (docs/v3_roadmap.md, Step V1): sol.cpp + one guarded perturbation (core/deep_bug.hpp).
// g1 = n, g2 = a[0] (first element of the a_i array), g3 = sum of the a_i. Constants written by tools/deep_calib.py.
#define CF_C1 158
#define CF_C2 975574925
#define CF_M 38
#define CF_C3 32
#include "deep_bug.hpp"
#include <cstdio>
#include <vector>
#include "range_set_range_product.hpp"

using namespace std;
const int MOD = 998244353;
using i64 = long long;

struct Elem {
    int a;
    int b;
};

Elem operator*(Elem x, Elem f){
    int a = i64(f.a) * i64(x.a) % MOD;
    int b = (i64(f.b) + i64(f.a) * i64(x.b)) % MOD;
    return { a, b };
}

int main() {
    cf_deep::begin();
    int n; scanf("%d", &n);
    int q; scanf("%d", &q);
    nachia::RangeSetRangeProduct<Elem> ds(n, {1,0});
    long long cf_a0 = 0, cf_sum = 0;
    for(int i=0; i<n; i++){
        int a; scanf("%d", &a);
        int b; scanf("%d", &b);
        ds.assign(i, i+1, {a,b});
        if(i == 0) cf_a0 = a;
        cf_sum += a;
    }
    cf_deep::guard(n, cf_a0, cf_sum);
    for(int ph=0; ph<q; ph++){
        int t; scanf("%d", &t);
        if(t == 0){
            int l; scanf("%d", &l);
            int r; scanf("%d", &r);
            int c; scanf("%d", &c);
            int d; scanf("%d", &d);
            if(l != r){ // my code don't support updating on empty ranges
                ds.assign(l, r, {c,d});
            }
        }
        else if(t == 1){
            int l; scanf("%d", &l);
            int r; scanf("%d", &r);
            int x; scanf("%d", &x);
            if(l == r){ // my code don't support folding empty ranges
                printf("%d\n", x);
            } else {
                Elem e = ds.fold(l, r);
                int ans = (i64(e.a) * i64(x) + i64(e.b)) % MOD;
                printf("%d\n", ans);
            }
        }
    }
    return 0;
}
