"""
Comprehensive tests for taxonomy.py — DEPENDENCY_GRAPH, ALL_TAGS, BASIC_TAGS,
ADVANCED_TAGS, CATEGORY_MAP.

Covers: valid keys/values, no circular deps, tag set integrity.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.taxonomy import (
    ADVANCED_TAGS,
    ALL_TAGS,
    BASIC_TAGS,
    CATEGORY_MAP,
    DEPENDENCY_GRAPH,
)


# ============================================================
# Helpers
# ============================================================

def _build_adjacency() -> dict:
    """Return adjacency dict {topic: [dependencies]} from DEPENDENCY_GRAPH."""
    return dict(DEPENDENCY_GRAPH)


def _detect_cycle(graph: dict) -> list | None:
    """Return the first cycle found via DFS, or None if graph is acyclic.

    Returns the cycle as a list of nodes in reverse order (from deepest back to entry).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict = {node: WHITE for node in graph}
    parent: dict = {}

    def dfs(u: str) -> list | None:
        color[u] = GRAY
        for v in graph.get(u, []):
            if v not in color:
                color[v] = WHITE
            if color[v] == GRAY:
                # Found a back edge: u → v where v is in current DFS path
                cycle = [v, u]
                while parent.get(u) and u != v:
                    u = parent[u]
                    cycle.append(u)
                cycle.reverse()
                return cycle
            if color[v] == WHITE:
                parent[v] = u
                result = dfs(v)
                if result is not None:
                    return result
        color[u] = BLACK
        return None

    for node in graph:
        if color.get(node, WHITE) == WHITE:
            result = dfs(node)
            if result is not None:
                return result
    return None


# ============================================================
# Tests: DEPENDENCY_GRAPH structural validity
# ============================================================

class TestDependencyGraphStructure:
    """DEPENDENCY_GRAPH keys and values are all strings."""

    def test_all_keys_are_strings(self):
        for key in DEPENDENCY_GRAPH:
            assert isinstance(key, str), f"Key {key!r} is not a string"

    def test_non_empty_keys(self):
        for key in DEPENDENCY_GRAPH:
            assert key.strip(), f"Key {key!r} is empty or whitespace-only"

    def test_all_values_are_lists_of_strings(self):
        for key, deps in DEPENDENCY_GRAPH.items():
            assert isinstance(deps, list), (
                f"Value for {key!r} is {type(deps).__name__}, expected list"
            )
            for i, dep in enumerate(deps):
                assert isinstance(dep, str), (
                    f"Dependency #{i} of {key!r} is {type(dep).__name__}: {dep!r}"
                )
                assert dep.strip(), (
                    f"Dependency #{i} of {key!r} is empty string"
                )

    def test_no_self_loops(self):
        for key, deps in DEPENDENCY_GRAPH.items():
            assert key not in deps, (
                f"Self-loop detected: {key!r} depends on itself"
            )

    def test_no_duplicate_dependencies(self):
        for key, deps in DEPENDENCY_GRAPH.items():
            assert len(deps) == len(set(deps)), (
                f"Duplicate dependencies in {key!r}: {deps}"
            )


class TestDependencyGraphNoCycles:
    """DEPENDENCY_GRAPH must be a DAG — no circular dependencies."""

    def test_no_circular_dependencies(self):
        graph = _build_adjacency()
        cycle = _detect_cycle(graph)
        assert cycle is None, (
            f"Circular dependency detected: {' → '.join(cycle)} → {cycle[0]}"
        )

    def test_no_simple_two_node_cycle(self):
        """Ensure no A→B and B→A patterns."""
        for a, deps in DEPENDENCY_GRAPH.items():
            for b in deps:
                if b in DEPENDENCY_GRAPH:
                    assert a not in DEPENDENCY_GRAPH[b], (
                        f"Two-node cycle: {a!r} ↔ {b!r}"
                    )


# ============================================================
# Tests: ALL_TAGS integrity
# ============================================================

class TestAllTags:
    """ALL_TAGS list must be non-empty, sorted, and contain valid tags."""

    def test_non_empty(self):
        assert len(ALL_TAGS) > 0, "ALL_TAGS must not be empty"

    def test_sorted(self):
        assert ALL_TAGS == sorted(ALL_TAGS), (
            "ALL_TAGS must be sorted alphabetically. "
            f"First out-of-order at index {next(i for i, (a, b) in enumerate(zip(ALL_TAGS, sorted(ALL_TAGS))) if a != b)}"
        )

    def test_all_elements_are_non_empty_strings(self):
        for i, tag in enumerate(ALL_TAGS):
            assert isinstance(tag, str), f"ALL_TAGS[{i}] is {type(tag).__name__}: {tag!r}"
            assert tag.strip(), f"ALL_TAGS[{i}] is empty string"

    def test_no_duplicates(self):
        assert len(ALL_TAGS) == len(set(ALL_TAGS)), (
            f"ALL_TAGS has duplicates: {[t for t in set(ALL_TAGS) if ALL_TAGS.count(t) > 1]}"
        )

    def test_has_expected_size(self):
        """ALL_TAGS should contain roughly 120 tags."""
        assert 100 <= len(ALL_TAGS) <= 150, (
            f"ALL_TAGS has {len(ALL_TAGS)} tags, expected ~120"
        )


# ============================================================
# Tests: BASIC_TAGS and ADVANCED_TAGS subsets
# ============================================================

class TestTagSubsets:
    """BASIC_TAGS and ADVANCED_TAGS must be subsets of ALL_TAGS."""

    def test_basic_tags_is_subset_of_all_tags(self):
        all_set = set(ALL_TAGS)
        missing = [t for t in BASIC_TAGS if t not in all_set]
        assert not missing, (
            f"BASIC_TAGS contains tags not in ALL_TAGS: {missing}"
        )

    def test_advanced_tags_is_subset_of_all_tags(self):
        all_set = set(ALL_TAGS)
        missing = [t for t in ADVANCED_TAGS if t not in all_set]
        assert not missing, (
            f"ADVANCED_TAGS contains tags not in ALL_TAGS: {missing}"
        )

    def test_basic_tags_has_expected_content(self):
        expected = {"prefix_sum", "two_pointers", "binary_search",
                    "sliding_window", "binary_tree_traverse", "bst",
                    "hash_map", "heap"}
        assert set(BASIC_TAGS) == expected, (
            f"BASIC_TAGS mismatch. Expected {expected}, got {set(BASIC_TAGS)}"
        )

    def test_advanced_tags_has_expected_content(self):
        expected = {"suffix_array", "sam", "max_flow",
                    "dinic", "convex_hull", "burnside"}
        assert set(ADVANCED_TAGS) == expected, (
            f"ADVANCED_TAGS mismatch. Expected {expected}, got {set(ADVANCED_TAGS)}"
        )

    def test_basic_and_advanced_are_disjoint(self):
        overlap = set(BASIC_TAGS) & set(ADVANCED_TAGS)
        assert not overlap, (
            f"BASIC_TAGS and ADVANCED_TAGS overlap: {overlap}"
        )

    def test_basic_and_advanced_non_empty(self):
        assert len(BASIC_TAGS) > 0, "BASIC_TAGS must not be empty"
        assert len(ADVANCED_TAGS) > 0, "ADVANCED_TAGS must not be empty"


# ============================================================
# Tests: All dependency references are valid tags
# ============================================================

class TestDependencyReferencesValid:
    """Every tag referenced as a dependency must exist in ALL_TAGS."""

    def test_all_dependency_source_keys_in_all_tags(self):
        """Each key in DEPENDENCY_GRAPH must be in ALL_TAGS."""
        all_set = set(ALL_TAGS)
        missing = [k for k in DEPENDENCY_GRAPH if k not in all_set]
        assert not missing, (
            f"DEPENDENCY_GRAPH keys not in ALL_TAGS: {missing}"
        )

    def test_all_dependency_values_in_all_tags(self):
        """Every prerequisite listed in DEPENDENCY_GRAPH values must be in ALL_TAGS."""
        all_set = set(ALL_TAGS)
        invalid: list = []
        for topic, deps in DEPENDENCY_GRAPH.items():
            for dep in deps:
                if dep not in all_set:
                    invalid.append(f"{topic!r} → {dep!r}")
        assert not invalid, (
            f"Dependencies reference tags not in ALL_TAGS: {invalid}"
        )

    def test_specified_dependencies_present(self):
        """Verify the 8 explicitly-specified dependencies are defined."""
        required_entries = [
            ("backtracking", ["binary_tree_traverse"]),
            ("bfs", ["binary_tree_traverse"]),
            ("tree_dp", ["binary_tree_traverse", "linear_dp"]),
            ("bitmask_dp", ["backtracking"]),
            ("shortest_path", ["union_find", "bfs"]),
            ("mst", ["union_find"]),
            ("kmp", ["two_pointers"]),
            ("ac_automaton", ["kmp", "trie"]),
        ]
        for topic, expected_deps in required_entries:
            assert topic in DEPENDENCY_GRAPH, (
                f"Required dependency entry {topic!r} missing from DEPENDENCY_GRAPH"
            )
            actual = DEPENDENCY_GRAPH[topic]
            for dep in expected_deps:
                assert dep in actual, (
                    f"{topic!r} should depend on {dep!r}, got {actual}"
                )

    def test_no_orphan_dependencies(self):
        """Every topic that appears as a dependency should also be a key or at least in ALL_TAGS."""
        all_keys = set(DEPENDENCY_GRAPH.keys())
        all_tags = set(ALL_TAGS)
        all_dep_values: set = set()
        for deps in DEPENDENCY_GRAPH.values():
            all_dep_values.update(deps)
        # A dep that is NOT a key itself is fine — it's a leaf node
        # But it MUST be in ALL_TAGS
        missing_tags = all_dep_values - all_tags
        assert not missing_tags, (
            f"Dependency values not found in ALL_TAGS: {missing_tags}"
        )


# ============================================================
# Tests: CATEGORY_MAP integrity
# ============================================================

class TestCategoryMap:
    """CATEGORY_MAP must be well-formed and coherent with ALL_TAGS."""

    def test_all_categories_are_non_empty_strings(self):
        for cat in CATEGORY_MAP:
            assert isinstance(cat, str), f"Category key {cat!r} is not a string"
            assert cat.strip(), "Category key is empty string"

    def test_all_category_values_are_lists_of_strings(self):
        for cat, tags in CATEGORY_MAP.items():
            assert isinstance(tags, list), (
                f"Category {cat!r} value is {type(tags).__name__}, expected list"
            )
            for i, tag in enumerate(tags):
                assert isinstance(tag, str), (
                    f"Category {cat!r} tag #{i} is {type(tag).__name__}: {tag!r}"
                )
                assert tag.strip(), f"Category {cat!r} tag #{i} is empty string"

    def test_all_category_tags_in_all_tags(self):
        all_set = set(ALL_TAGS)
        for cat, tags in CATEGORY_MAP.items():
            missing = [t for t in tags if t not in all_set]
            assert not missing, (
                f"Category {cat!r} contains tags not in ALL_TAGS: {missing}"
            )

    def test_no_duplicate_tags_within_category(self):
        for cat, tags in CATEGORY_MAP.items():
            assert len(tags) == len(set(tags)), (
                f"Category {cat!r} has duplicate tags: "
                f"{[t for t in set(tags) if tags.count(t) > 1]}"
            )

    def test_categories_are_mutually_exclusive(self):
        """No tag should appear in more than one category."""
        seen: dict[str, str] = {}
        for cat, tags in CATEGORY_MAP.items():
            for tag in tags:
                if tag in seen:
                    assert False, (
                        f"Tag {tag!r} appears in both {seen[tag]!r} and {cat!r}"
                    )
                seen[tag] = cat

    def test_category_map_has_expected_categories(self):
        expected = {"数据结构", "字符串", "图论", "动态规划", "数学", "搜索", "排序", "技巧", "计算几何"}
        actual = set(CATEGORY_MAP.keys())
        missing = expected - actual
        extra = actual - expected
        assert not missing, f"CATEGORY_MAP missing expected categories: {missing}"
        assert not extra, f"CATEGORY_MAP has unexpected categories: {extra}"
