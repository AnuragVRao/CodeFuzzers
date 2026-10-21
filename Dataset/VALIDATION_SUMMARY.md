# Validation summary

30 problems, 9524 differential cases (generator -> verifier -> fast solution + brute force -> checker). Compiler: g++ 13.3, -std=c++17. Library Checker commit 1814c4e.

| Group | Problem | Checker | Generator | Cases | Input bytes (min-max) | ms/case sol | ms/case brute | Defects |
|---|---|---|---|---|---|---|---|---|
| array | deque_operate_all_composite | exact-match | generator.cpp | 300 | 83-477 | 2.96 | 2.99 | 0 |
| array | line_add_get_min | exact-match | generator.cpp | 300 | 68-1083 | 2.92 | 2.92 | 0 |
| array | majority_voting | exact-match | generator.cpp | 300 | 9790-15597 | 3.58 | 3.29 | 0 |
| array | range_add_range_min | exact-match | generator.cpp | 300 | 1465-52570 | 3.67 | 3.54 | 0 |
| array | range_add_range_min | exact-match | generator_alt_1.cpp | 75 | 10782-11717 | 3.08 | 3.03 | 0 |
| array | range_affine_point_get | exact-match | generator.cpp | 300 | 1402-56968 | 3.91 | 3.68 | 0 |
| array | range_affine_point_get | exact-match | generator_alt_1.cpp | 75 | 14104-15887 | 3.35 | 3.2 | 0 |
| array | range_affine_range_sum | exact-match | generator.cpp | 300 | 1402-60334 | 3.88 | 4.31 | 0 |
| array | range_affine_range_sum | exact-match | generator_alt_1.cpp | 75 | 15135-16691 | 3.32 | 3.06 | 0 |
| array | range_kth_smallest | exact-match | generator.cpp | 300 | 554-14855 | 3.58 | 4.24 | 0 |
| array | range_linear_add_range_min | exact-match | generator.cpp | 300 | 1465-53786 | 5.35 | 3.67 | 0 |
| array | range_linear_add_range_min | exact-match | generator_alt_1.cpp | 75 | 11519-12518 | 3.55 | 3.3 | 0 |
| array | range_set_range_composite | exact-match | generator.cpp | 300 | 2779-90130 | 4.42 | 4.74 | 0 |
| array | range_set_range_composite | exact-match | generator_alt_1.cpp | 75 | 20574-21354 | 3.42 | 3.35 | 0 |
| array | rectangle_sum | exact-match | generator.cpp | 300 | 2473-32581 | 3.82 | 5.08 | 0 |
| array | static_range_lis_query | exact-match | generator.cpp | 300 | 552-11033 | 4.47 | 6.39 | 0 |
| array | static_range_mode_query | custom | generator.cpp | 300 | 6-442 | 2.83 | 2.79 | 0 |
| graph | cartesian_tree | exact-match | generator.cpp | 300 | 4-1096 | 3.03 | 2.99 | 0 |
| graph | connected_components_of_complement_graph | custom | generator.cpp | 300 | 4-2553 | 2.86 | 2.83 | 0 |
| graph | enumerate_triangles | exact-match | generator.cpp | 299 | 27-10926 | 3.02 | 71.11 | 1 |
| graph | frequency_table_of_tree_distance | exact-match | generator.cpp | 300 | 6-7485 | 3.8 | 7.05 | 0 |
| graph | incremental_scc | exact-match | generator.cpp | 300 | 18-145 | 2.8 | 2.79 | 0 |
| graph | three_edge_connected_components | custom | generator.cpp | 300 | 9-1141 | 2.8 | 9.24 | 0 |
| graph | three_edge_connected_components | custom | generator_alt_1.cpp | 75 | 40-2483 | 2.99 | 6.02 | 0 |
| graph | two_edge_connected_components | custom | generator.cpp | 300 | 9-1141 | 2.83 | 6.91 | 0 |
| graph | two_edge_connected_components | custom | generator_alt_1.cpp | 75 | 40-2483 | 2.76 | 3.71 | 0 |
| graph | vertex_add_path_sum | exact-match | generator.cpp | 300 | 2269-29717 | 3.45 | 3.37 | 0 |
| graph | vertex_add_subtree_sum | exact-match | generator.cpp | 300 | 1760-49865 | 3.41 | 3.37 | 0 |
| graph | vertex_set_path_composite | exact-match | generator.cpp | 300 | 3653-103326 | 4.16 | 7.02 | 0 |
| string | enumerate_palindromes | exact-match | generator.cpp | 300 | 3-2000 | 2.99 | 2.87 | 0 |
| string | longest_common_substring | custom | generator.cpp | 300 | 4-12 | 2.86 | 2.87 | 0 |
| string | lyndon_factorization | exact-match | generator.cpp | 300 | 2-33 | 2.93 | 2.91 | 0 |
| string | number_of_substrings | exact-match | generator.cpp | 300 | 2-33 | 2.86 | 2.87 | 0 |
| string | prefix_substring_lcs | exact-match | generator.cpp | 300 | 12-542 | 2.9 | 2.86 | 0 |
| string | suffixarray | exact-match | generator.cpp | 300 | 2-33 | 2.6 | 2.64 | 0 |
| string | wildcard_pattern_matching | exact-match | generator.cpp | 300 | 4-60 | 2.88 | 2.82 | 0 |
| string | zalgorithm | exact-match | generator.cpp | 300 | 2-33 | 2.82 | 2.86 | 0 |

The single defect is the upstream generator abort noted in `enumerate_triangles/meta.json`.
Per-case times are wall-clock including process start-up (~3 ms).
