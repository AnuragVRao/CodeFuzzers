# v2 results

Results of the v2 pre-registered steps (docs/v2_pilot_plan.md). Append-only: later results and corrections are
added as new dated sections at the end; nothing above is edited.

## Step 2e Part 2: mutation diagnostics (2026-10-30)

- Run commit: 90cc267 (the plan's commit; build 99e05aa, `git diff --stat 99e05aa..90cc267 -- core/ Dataset/ tools/`
  empty). Part 2's outputs do not record a commit.
- Command: `python3 tools/part2.py` (defaults: the 6 Part 2 problems, seed base 40000, 2,000 warm-up tests,
  2,000 children per mode, output results/part2/).
- Date: 2026-10-30, about 19:40:07-19:40:51 UTC (output files written 19:40:11-19:40:51 UTC).
- Exit status: 0. No replay mismatch, no truncation abort, no crash; nothing was re-run.
- Runtime: 44.8 s wall (`time`: real 0m44.787s).
- Outputs: results/part2/summary.json and results/part2/<problem>/ for the 6 problems (warmup.json, parents.txt,
  parents.tsv, parents.out, and guided/byte/draw .tsv and .out). results/ is gitignored; the hashes below identify
  the files.
- Parents per problem: majority_voting 146, range_linear_add_range_min 91, longest_common_substring 76,
  deque_operate_all_composite 64, enumerate_palindromes 34, cartesian_tree 19. All 36,000 children ran OK.

### Criterion (a): draw-level tape mode, 3 focus problems (median and IQR over changed children)

| problem | mut_changed_input | >= 0.80 | median mut_similarity [q1, q3] | >= 0.50 |
|---|---:|---|---|---|
| majority_voting | 0.8825 | PASS | 0.9669 [0.8377, 0.9918] | PASS |
| range_linear_add_range_min | 0.9165 | PASS | 0.9583 [0.8214, 0.9849] | PASS |
| longest_common_substring | 0.8395 | PASS | 0.9773 [0.8667, 0.9894] | PASS |

Verdict for (a): PASS (recorded against plan commit 90cc267).

### Descriptive (not part of the criterion)
Other modes and problems and the all-children medians are in results/part2/summary.json; the op-log analysis
(single-operator change rates, same-value writes, size no-op split) is reproducible with the script below.
The op-log analysis script was written after the run and is kept next to the outputs as
results/part2/part2_oplog.py (sha256 f48d6a4d0f815b8f7ef0811c5b1e068569c185152d6812e8d5a0cc1aa86c9f5f); it is not
part of tools/ yet. Its size no-op categories (factor 1, clamp, same-mask-band, other) were defined after the data
and are descriptive only.

### SHA-256 of every Part 2 output file
```
db1409d1c04ce120e1dcb35ecd9bcfe6c635f6dcac1959d9dc5f622fbb0012f8  results/part2/cartesian_tree/byte.out
06dbc104fcf414db253fbd8d41c81651643e34939aa4301760f1e6f28407c27f  results/part2/cartesian_tree/byte.tsv
ff8ba847a495889f3ab9aa14fc6a6c356eb81ffb3781a45a80f71215e7011a8d  results/part2/cartesian_tree/draw.out
96fe4500e86529c1f94e5db97e70ed66e954205f6ac1001bdfd403a53e42852a  results/part2/cartesian_tree/draw.tsv
1d9024d609408c1cc54bf4666b96ce0a16daac4929c5bf90fd25f74806d89bcb  results/part2/cartesian_tree/guided.out
8eb5995e0571b3c51c1bfeb9760df56e0f776cc781481683335276b1abb9fcb3  results/part2/cartesian_tree/guided.tsv
283b74006c0a9c0b0954799050ec1b1865d24a272d141d337db59bf383eca4f5  results/part2/cartesian_tree/parents.out
77b15e1ad27401e679e5e36dbea442daf06c2f45c56f8d652c442a6876b3822c  results/part2/cartesian_tree/parents.tsv
9b654c11fc100f54df8e5d720fda8d1c9b7df50aeebe889fc973b358e6ecbdeb  results/part2/cartesian_tree/parents.txt
f0fa401dc0ef037c9a8dfda236341e9d1fa7a4c537e203d0366fdf34850599d2  results/part2/cartesian_tree/warmup.json
c0724fd1d3f2cada5cc25ac80898ce38054d5081624ea2bdf35737b0c3435ffe  results/part2/deque_operate_all_composite/byte.out
907d3dcf7bcb7f813c841536a12e3be4b86039c0e56ce41c05e0cd631ec08d6f  results/part2/deque_operate_all_composite/byte.tsv
671b0685d5afb8eacc7b8c051236349a31516d3ce521372a0a1ba1a7a0843ba4  results/part2/deque_operate_all_composite/draw.out
1a68f0b80c129d33dddd1b39ffd060eee3e1a988322fc4d650abe65c97ff0aaa  results/part2/deque_operate_all_composite/draw.tsv
519df4d0369710d031bf4b8cae670b87a3e04b3aab04639b8460e20300a1a563  results/part2/deque_operate_all_composite/guided.out
05d882adb1ada30fe7871a7950ed273f062779a49495cc7bef7e30526e0fc78d  results/part2/deque_operate_all_composite/guided.tsv
1e600275659f971ad2e3fd37fff10c4bc5b0ef3c14ceb1f316f7aaaeab1272f5  results/part2/deque_operate_all_composite/parents.out
bddfc9f35d3314dcc01787365937dff547fcf7b6f352c539f106468fa5db401b  results/part2/deque_operate_all_composite/parents.tsv
bf3c500c1727d19720a450d41f05a6b120d2fb35108ac235fa2b9f1a4db8496d  results/part2/deque_operate_all_composite/parents.txt
8e96b5e375fc53f2a9381d041b350a972c5c8ca8baf956cc79456275f169eda3  results/part2/deque_operate_all_composite/warmup.json
a5214e1fb2ba65b535fc959715eaa74b7cc174d6a8f021c1f6a665aff7ba81ac  results/part2/enumerate_palindromes/byte.out
cd47270643aec4cc7f00422f6e2f16ed1ec8d138ac095fb92add11476e826534  results/part2/enumerate_palindromes/byte.tsv
905e608e3b27c54ce82a5a3f30601e609ec5622e3525d98738502ee27ff605c9  results/part2/enumerate_palindromes/draw.out
8c26d515d27e97cd3ea48bb2caf97afcc104a01a7e84661b1d98ff5f26336778  results/part2/enumerate_palindromes/draw.tsv
23af80f135165b84ca4d4c13b9b8ba035c12f422ac4e3698ec2917940deac525  results/part2/enumerate_palindromes/guided.out
ceebc1194116514af6bd69308170fca66ac90cceda35d66b94973f8a9c246b16  results/part2/enumerate_palindromes/guided.tsv
ab42efa016f965038fd4b645e13d405f63a516866bd556354a45abdc73e6647c  results/part2/enumerate_palindromes/parents.out
812ae3cbddd9161fdc6ffc19f52911932072c0f96054b2e03a8696197b059081  results/part2/enumerate_palindromes/parents.tsv
0939981b299f1df32b556f581406211d1791ddddf058661a6b13b5e78555d047  results/part2/enumerate_palindromes/parents.txt
504e5c9fef0eeeae9859194d4f69e115afe88cf587fd880bd5e3472466750605  results/part2/enumerate_palindromes/warmup.json
ee4c06a8dfb7cf702f918394ceb232ff13b20bddc0944524a0f85050e135fdb0  results/part2/longest_common_substring/byte.out
ab410d78b26686a18bc0e51ddddabf16fbdb213be4bd6afd40eaebeea2fe59b3  results/part2/longest_common_substring/byte.tsv
69c076f28f42586ab636ae6e26aa2502e05d6dbb25af83f929d0a71988629ea2  results/part2/longest_common_substring/draw.out
aa812c98105dce3e5035cd3f04057b7478b6575c9b4e72f3dde830909616ae14  results/part2/longest_common_substring/draw.tsv
82decab7d61600d5d750eedd4df531902c6dda5864bc25a476e0ba74e079f6dd  results/part2/longest_common_substring/guided.out
12f3b26b8316656e6a72ff4daa32fe2607371fe609ff04c066e6d45c317735ac  results/part2/longest_common_substring/guided.tsv
460a0d0ca6886a8a138807e3f52427f09657ce663a73c8114031e8b4d4962fad  results/part2/longest_common_substring/parents.out
7f0d86b648dffc09ed4859fa5a76b3e30bee4768a87a700bfab3149a769de001  results/part2/longest_common_substring/parents.tsv
14396b5c0583d1ab1089ab6fb947b5a7cc858d67c5faa0a51373f89652d8c70a  results/part2/longest_common_substring/parents.txt
eed78d7cb4443d2176f99a2e4d8ae4c6b75cc70e0b8d104d7d87ae960b383055  results/part2/longest_common_substring/warmup.json
712fe2f3d4ca49a7b7729cd13b70d24cb09d58e9e38aa86a86d782073c2f7b5e  results/part2/majority_voting/byte.out
ca3ab1d3787bbb44cce06617351f23ad32b715ff3fe2f05d1393a0218cc9211f  results/part2/majority_voting/byte.tsv
1e4bce542db26a90152f1f2f9b600264972fed9942d40ec08f66bb51bcaf4784  results/part2/majority_voting/draw.out
af0d87d2d4ef27bd27bea24d99405c6531f0712918f15328f25aecfceebad965  results/part2/majority_voting/draw.tsv
78cfd5199b60b58ad3d0e59132111a0c1710c2a227ecc4f8f9120a75e701a5a2  results/part2/majority_voting/guided.out
1553f0376d25dc9d4dfc53328e31dd5ca8f09cba216d0c02bb05fb3f38d68235  results/part2/majority_voting/guided.tsv
af2a169811fd8b8d133fd796a20b77e00c0d1439645e085cdd1425fbc505d37d  results/part2/majority_voting/parents.out
f05b50428d82247cd2ae794e9bec8d41e207761699035f1c53e228566dc2bc58  results/part2/majority_voting/parents.tsv
c3dfb85303a9d6457e61399bd7fb5856247c6eb6240a62f430e529459f99eb22  results/part2/majority_voting/parents.txt
e6d0035dce3c4815f7ff0fbe0fe8ad54c043bcb3fbf752b4e29a2598aa5f0ef7  results/part2/majority_voting/warmup.json
66d1b66eee8051f3d2519c3f54a026c56ddd07e61f3979c24f970f6f76da776b  results/part2/range_linear_add_range_min/byte.out
98b4d30bc235b5fde0e98f137ba4c0b243b6fe7ce6285e63b7d90cf642eebb44  results/part2/range_linear_add_range_min/byte.tsv
153cdf5684bcd853d69d27de1de446e665043ded4abede5e0867304b03e4e998  results/part2/range_linear_add_range_min/draw.out
1738eb37170fd46bdad253822c73bdae63f1f6de0a31234c2fa4bba4d9bc631a  results/part2/range_linear_add_range_min/draw.tsv
efe5a5fcee96e35e0016bb85da901b6a002274bbb9c701749b6ec721d2063ef1  results/part2/range_linear_add_range_min/guided.out
94d89e6e597235c9e27279bcb460f400736a546c62d0e267e9677658cb7c94b1  results/part2/range_linear_add_range_min/guided.tsv
b4fa09c9bba6e46008762d30bcbf5631237b3509c6088c1885e21b366895059a  results/part2/range_linear_add_range_min/parents.out
85513d1d2e412b3c10026ddc6ea39abe8716d80b9860d0f77218536a3be934eb  results/part2/range_linear_add_range_min/parents.tsv
5d11bae9a65d68015002f60ae7cb28e2ce20f2b0b102f1ccc79a3ca3129ecab6  results/part2/range_linear_add_range_min/parents.txt
5d662d17373403f92324685bb2ec070b767ac72d7b9be651e89d5da7419d37c0  results/part2/range_linear_add_range_min/warmup.json
01c8e22170d6c94dd50be1c49848ac71cc55d95cb95c3e8bafd2d64709a9075f  results/part2/summary.json
```
