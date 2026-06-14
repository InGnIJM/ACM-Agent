"""
ACM Agent 题目分类体系 —— 标签、依赖关系、分类映射。

Pure Python — no LLM, no DB.
"""

from __future__ import annotations

from typing import Dict, List

# ============================================================
# DEPENDENCY_GRAPH — topic → prerequisite topics
# ============================================================

DEPENDENCY_GRAPH: Dict[str, List[str]] = {
    # ---- 用户指定的依赖 ----
    "backtracking":      ["binary_tree_traverse"],
    "bfs":               ["binary_tree_traverse"],
    "tree_dp":           ["binary_tree_traverse", "linear_dp"],
    "bitmask_dp":        ["backtracking"],
    "shortest_path":     ["union_find", "bfs"],
    "mst":               ["union_find"],
    "kmp":               ["two_pointers"],
    "ac_automaton":      ["kmp", "trie"],
    # ---- 数据结构 ----
    "segment_tree":      ["binary_tree"],
    "fenwick_tree":      ["prefix_sum"],
    "sparse_table":      ["prefix_sum"],
    "sqrt_decomposition": ["prefix_sum"],
    "persistent_segment_tree": ["segment_tree"],
    "treap":             ["bst"],
    "splay_tree":        ["bst"],
    "monotonic_stack":   ["stack"],
    "monotonic_queue":   ["queue"],
    # ---- 图论 ----
    "topological_sort":  ["dfs"],
    "scc":               ["dfs"],
    "tarjan":            ["dfs"],
    "kosaraju":          ["dfs"],
    "bcc":               ["dfs", "scc"],
    "cut_vertex":        ["tarjan"],
    "bridge":            ["tarjan"],
    "dijkstra":          ["bfs", "heap"],
    "bellman_ford":      ["shortest_path"],
    "spfa":              ["bellman_ford"],
    "floyd_warshall":    ["shortest_path"],
    "max_flow":          ["bfs"],
    "dinic":             ["max_flow", "bfs"],
    "min_cost_max_flow": ["max_flow"],
    "isap":              ["max_flow"],
    "bipartite_matching": ["max_flow", "dfs"],
    "euler_path":        ["dfs"],
    "hamilton_path":     ["backtracking"],
    "lca":               ["binary_tree", "sparse_table"],
    "heavy_light_decomposition": ["segment_tree", "binary_tree_traverse"],
    "tree_diameter":     ["bfs", "binary_tree_traverse"],
    "tree_centroid":     ["binary_tree_traverse"],
    "kruskal":           ["union_find"],
    "prim":              ["heap"],
    "a_star":            ["bfs", "dijkstra"],
    "ida_star":          ["backtracking"],
    "bidirectional_bfs": ["bfs"],
    # ---- 字符串 ----
    "suffix_array":      ["kmp"],
    "sam":               ["suffix_array", "trie"],
    "palindrome_tree":   ["trie"],
    "z_algorithm":       ["rolling_hash"],
    "manacher":          ["two_pointers"],
    "rolling_hash":      ["prefix_sum"],
    "minimum_expression": ["two_pointers"],
    # ---- DP ----
    "knapsack":          ["linear_dp"],
    "interval_dp":       ["linear_dp"],
    "digit_dp":          ["linear_dp"],
    "state_compression_dp": ["bitmask_dp"],
    "probability_dp":    ["linear_dp"],
    "game_dp":           ["linear_dp"],
    "lis":               ["linear_dp", "binary_search"],
    "lcs":               ["linear_dp"],
    "edit_distance":     ["linear_dp"],
    "matrix_chain":      ["interval_dp"],
    # ---- 数学 ----
    "matrix_exponentiation": ["linear_algebra"],
    "fft":               ["complex_number"],
    "ntt":               ["fft", "modular_arithmetic"],
    "fwt":               ["fft"],
    "generating_function": ["combinatorics", "fft"],
    "inclusion_exclusion": ["combinatorics"],
    "polya":             ["burnside"],
    "mobius_inversion":  ["number_theory"],
    "miller_rabin":      ["modular_arithmetic"],
    "crt":               ["modular_arithmetic"],
    "pollard_rho":       ["miller_rabin"],
    "simplex":           ["linear_algebra"],
    "gaussian_elimination": ["linear_algebra"],
    "catalan_number":    ["combinatorics"],
    "sterlings":         ["combinatorics"],
    # ---- 搜索 ----
    "meet_in_the_middle": ["binary_search", "bruteforce"],
    "branch_and_bound":  ["backtracking"],
    # ---- 计算几何 ----
    "half_plane_intersection": ["convex_hull"],
    "rotating_calipers": ["convex_hull"],
    # ---- 技巧 ----
    "difference_array":  ["prefix_sum"],
    "discretization":    ["prefix_sum"],
    "coordinate_compression": ["two_pointers"],
}


# ============================================================
# ALL_TAGS — 全部约 120 个规范化标签（按字母排序）
# ============================================================

ALL_TAGS: List[str] = sorted([
    # Data Structures 数据结构
    "array",
    "binary_tree",
    "binary_tree_traverse",
    "bitset",
    "bst",
    "deque",
    "fenwick_tree",
    "hash_map",
    "hash_set",
    "heap",
    "linked_list",
    "monotonic_queue",
    "monotonic_stack",
    "persistent_segment_tree",
    "priority_queue",
    "queue",
    "segment_tree",
    "sparse_table",
    "splay_tree",
    "sqrt_decomposition",
    "stack",
    "treap",
    "trie",
    "union_find",
    # String 字符串
    "ac_automaton",
    "kmp",
    "lcp",
    "manacher",
    "minimum_expression",
    "palindrome_tree",
    "rolling_hash",
    "sam",
    "suffix_array",
    "z_algorithm",
    # Graph 图论
    "a_star",
    "bcc",
    "bellman_ford",
    "bfs",
    "bidirectional_bfs",
    "bipartite_matching",
    "bridge",
    "cut_vertex",
    "dfs",
    "dijkstra",
    "dinic",
    "euler_path",
    "floyd_warshall",
    "hamilton_path",
    "heavy_light_decomposition",
    "ida_star",
    "isap",
    "kosaraju",
    "kruskal",
    "lca",
    "max_flow",
    "min_cost_max_flow",
    "mst",
    "prim",
    "scc",
    "shortest_path",
    "spfa",
    "tarjan",
    "topological_sort",
    "tree_centroid",
    "tree_diameter",
    # DP 动态规划
    "bitmask_dp",
    "digit_dp",
    "edit_distance",
    "game_dp",
    "interval_dp",
    "knapsack",
    "lcs",
    "linear_dp",
    "lis",
    "matrix_chain",
    "probability_dp",
    "state_compression_dp",
    "tree_dp",
    # Math 数学
    "burnside",
    "catalan_number",
    "combinatorics",
    "complex_number",
    "crt",
    "euler_function",
    "exgcd",
    "fft",
    "fwt",
    "game_theory",
    "gaussian_elimination",
    "gcd",
    "generating_function",
    "inclusion_exclusion",
    "integer_programming",
    "linear_algebra",
    "matrix_exponentiation",
    "miller_rabin",
    "mobius_inversion",
    "modular_arithmetic",
    "ntt",
    "number_theory",
    "pollard_rho",
    "polya",
    "prime",
    "probability",
    "simplex",
    "sterlings",
    # Search 搜索
    "backtracking",
    "binary_search",
    "branch_and_bound",
    "heuristic_search",
    "meet_in_the_middle",
    "ternary_search",
    # Sorting 排序
    "bucket_sort",
    "counting_sort",
    "heap_sort",
    "merge_sort",
    "quick_sort",
    "radix_sort",
    # Two Pointers / Window 双指针 / 滑动窗口
    "difference_array",
    "discretization",
    "prefix_sum",
    "sliding_window",
    "two_pointers",
    # Geometry 计算几何
    "computational_geometry",
    "convex_hull",
    "half_plane_intersection",
    "rotating_calipers",
    "scanline",
    # Techniques 泛用技巧
    "bitwise_operation",
    "bruteforce",
    "constructive",
    "coordinate_compression",
    "divide_and_conquer",
    "greedy",
    "interactive",
    "random",
    "recursion",
    "simulation",
])


# ============================================================
# BASIC_TAGS — 基础标签子集
# ============================================================

BASIC_TAGS: List[str] = [
    "prefix_sum",
    "two_pointers",
    "binary_search",
    "sliding_window",
    "binary_tree_traverse",
    "bst",
    "hash_map",
    "heap",
]


# ============================================================
# ADVANCED_TAGS — 进阶标签子集
# ============================================================

ADVANCED_TAGS: List[str] = [
    "suffix_array",
    "sam",
    "max_flow",
    "dinic",
    "convex_hull",
    "burnside",
]


# ============================================================
# CATEGORY_MAP — 分类 → 标签列表（用于雷达图）
# ============================================================

CATEGORY_MAP: Dict[str, List[str]] = {
    "数据结构": [
        "array", "linked_list", "stack", "queue", "deque",
        "hash_map", "hash_set", "binary_tree", "binary_tree_traverse",
        "bst", "heap", "union_find", "segment_tree",
        "fenwick_tree", "sparse_table", "sqrt_decomposition", "treap",
        "splay_tree", "bitset", "persistent_segment_tree",
        "monotonic_stack", "monotonic_queue", "priority_queue",
    ],
    "字符串": [
        "kmp", "ac_automaton", "suffix_array", "sam", "lcp",
        "z_algorithm", "manacher", "rolling_hash", "trie",
        "palindrome_tree", "minimum_expression",
    ],
    "图论": [
        "dfs", "bfs", "shortest_path", "dijkstra", "bellman_ford",
        "floyd_warshall", "spfa", "topological_sort", "scc", "tarjan",
        "kosaraju", "bcc", "cut_vertex", "bridge", "mst", "kruskal",
        "prim", "tree_diameter", "tree_centroid", "lca",
        "heavy_light_decomposition", "bipartite_matching",
        "max_flow", "dinic", "min_cost_max_flow", "isap",
        "euler_path", "hamilton_path",
    ],
    "动态规划": [
        "linear_dp", "knapsack", "interval_dp", "tree_dp",
        "bitmask_dp", "state_compression_dp", "digit_dp",
        "probability_dp", "game_dp", "lcs", "lis",
        "matrix_chain", "edit_distance",
    ],
    "数学": [
        "number_theory", "combinatorics", "probability", "linear_algebra",
        "matrix_exponentiation", "fft", "ntt", "fwt", "generating_function",
        "game_theory", "inclusion_exclusion", "burnside", "polya",
        "sterlings", "catalan_number", "mobius_inversion",
        "prime", "gcd", "exgcd", "modular_arithmetic", "crt",
        "miller_rabin", "pollard_rho", "euler_function",
        "gaussian_elimination", "simplex", "integer_programming",
        "complex_number",
    ],
    "搜索": [
        "binary_search", "ternary_search", "meet_in_the_middle",
        "bidirectional_bfs", "a_star", "ida_star",
        "backtracking", "branch_and_bound", "heuristic_search",
    ],
    "排序": [
        "quick_sort", "merge_sort", "counting_sort",
        "bucket_sort", "radix_sort", "heap_sort",
    ],
    "技巧": [
        "two_pointers", "sliding_window", "prefix_sum", "difference_array",
        "discretization", "coordinate_compression", "greedy",
        "divide_and_conquer", "recursion", "bruteforce",
        "constructive", "random", "interactive", "simulation",
        "bitwise_operation",
    ],
    "计算几何": [
        "computational_geometry", "convex_hull", "rotating_calipers",
        "half_plane_intersection", "scanline",
    ],
}
