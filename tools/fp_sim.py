#!/usr/bin/env python3
"""False-PROCEED rate of the Step 2e pilot's criterion (b) under a no-effect null (simulation; runs no fuzzer).
3 problems x 3 arms (random-capture, tape-noshare, tape-rwlock), n runs per arm, every group drawing generated
tests-to-bug from the same distribution. (b) passes if, for any problem, median(tape arm) / median(random-capture)
<= 0.70: 6 ratios, the 2 of a problem share their denominator. Nulls: exponential (rate 1) and geometric with
median ~300 tests. Prints, per null and n, P(any of the 6 ratios <= 0.70) and the per-comparison rate.
Usage: python3 tools/fp_sim.py [--n 50 200] [--sims 200000] [--seed 20261030]
"""
import argparse
import numpy as np


def rate(draw, n, sims, thr=0.70, chunk=10_000):
    hit = []
    for _ in range(sims // chunk):
        med = np.median(draw((chunk, 3, 3, n)), axis=3)  # chunk x problems x arms
        hit.append(med[:, :, 1:] / med[:, :, :1] <= thr)  # tape arms / random-capture
    hit = np.concatenate(hit)
    return hit.any(axis=(1, 2)).mean(), hit.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[50, 200], help="runs per arm per problem")
    ap.add_argument("--sims", type=int, default=200_000, help="replicates (multiple of 10,000)")
    ap.add_argument("--seed", type=int, default=20261030)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    nulls = {"exponential": lambda s: rng.exponential(1.0, s),
             "geometric (median ~300)": lambda s: rng.geometric(np.log(2) / 300, s)}
    for n in a.n:
        for name, draw in nulls.items():
            p, c = rate(draw, n, a.sims)
            print(f"n = {n:3}, {name:24}: P(false PROCEED by (b)) = {p:.4f}  (per comparison {c:.4f}, {a.sims:,} replicates)")


if __name__ == "__main__":
    main()
