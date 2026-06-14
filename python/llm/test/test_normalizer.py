"""Tests for TagNormalizer and DifficultyNormalizer."""

import pytest
from pathlib import Path
from llm.normalizer import TagNormalizer, DifficultyNormalizer


@pytest.fixture(scope="module")
def tag_normalizer():
    return TagNormalizer()


@pytest.fixture(scope="module")
def difficulty_normalizer():
    return DifficultyNormalizer()


class TestTagNormalizer:
    """Tests for TagNormalizer."""

    def test_reverse_index_built_correctly(self, tag_normalizer):
        """Reverse index should have platform keys with raw→normalized mappings."""
        assert isinstance(tag_normalizer._reverse_index, dict)
        assert len(tag_normalizer._reverse_index) > 0
        for platform, mapping in tag_normalizer._reverse_index.items():
            assert isinstance(platform, str)
            assert isinstance(mapping, dict)
            for raw_tag, normalized_tag in mapping.items():
                assert isinstance(raw_tag, str)
                assert isinstance(normalized_tag, str)

    def test_normalize_tags_luogu(self, tag_normalizer):
        """Known tag maps correctly; unknown tag becomes unmapped: prefix."""
        result = tag_normalizer.normalize_tags("luogu", ["前缀和", "未知标签"])
        assert "prefix_sum" in result
        assert "unmapped:未知标签" in result

    def test_normalize_tags_leetcode(self, tag_normalizer):
        """LeetCode tag normalizes correctly."""
        result = tag_normalizer.normalize_tags("leetcode", ["Two Pointers"])
        assert "two_pointers" in result

    def test_normalize_tags_unknown_platform(self, tag_normalizer):
        """Unknown platform returns all unmapped."""
        result = tag_normalizer.normalize_tags("nonexistent", ["Some Tag"])
        assert result == ["unmapped:Some Tag"]

    def test_get_all_tags(self, tag_normalizer):
        """get_all_tags returns a non-empty flat list."""
        tags = tag_normalizer.get_all_tags()
        assert isinstance(tags, list)
        assert len(tags) > 0
        assert all(isinstance(t, str) for t in tags)


class TestDifficultyNormalizer:
    """Tests for DifficultyNormalizer."""

    def test_luogu_beginner(self, difficulty_normalizer):
        """入门 → 1."""
        assert difficulty_normalizer.normalize("luogu", "入门") == 1

    def test_leetcode_hard(self, difficulty_normalizer):
        """Hard → 8."""
        assert difficulty_normalizer.normalize("leetcode", "Hard") == 8

    def test_leetcode_easy(self, difficulty_normalizer):
        """Easy → 3."""
        assert difficulty_normalizer.normalize("leetcode", "Easy") == 3

    def test_leetcode_medium(self, difficulty_normalizer):
        """Medium → 5."""
        assert difficulty_normalizer.normalize("leetcode", "Medium") == 5

    def test_codeforces_2000(self, difficulty_normalizer):
        """CF 2000 → between 4 and 6."""
        val = difficulty_normalizer.normalize("codeforces", 2000)
        assert 4 <= val <= 6

    def test_codeforces_800(self, difficulty_normalizer):
        """CF 800 → 1 (clamped)."""
        val = difficulty_normalizer.normalize("codeforces", 800)
        assert val == 1.0

    def test_codeforces_3500(self, difficulty_normalizer):
        """CF 3500 → 10 (clamped)."""
        val = difficulty_normalizer.normalize("codeforces", 3500)
        assert val == 10.0

    def test_atcoder_400(self, difficulty_normalizer):
        """AtCoder 400 → 2.0."""
        val = difficulty_normalizer.normalize("atcoder", 400)
        assert val == 2.0

    def test_nowcoder_25(self, difficulty_normalizer):
        """NowCoder diff 25 → 5.0."""
        val = difficulty_normalizer.normalize("nowcoder", 25)
        assert val == 5.0

    def test_unknown_platform_default(self, difficulty_normalizer):
        """Unknown platform → default 5.0."""
        val = difficulty_normalizer.normalize("unknown_oj", "whatever")
        assert val == 5.0

    def test_luogu_unknown_string(self, difficulty_normalizer):
        """Unknown luogu difficulty string → default 5.0."""
        val = difficulty_normalizer.normalize("luogu", "不存在的等级")
        assert val == 5.0

    @pytest.mark.parametrize("raw, expected", [
        ("入门", 1),
        ("普及-", 2),
        ("普及/提高-", 3),
        ("普及+/提高", 4),
        ("提高+/省选-", 5),
        ("省选/NOI-", 6),
        ("NOI/NOI+", 7),
        ("NOI+", 8),
        ("CTSC", 9),
        ("CTSC+", 10),
    ])
    def test_all_luogu_difficulties(self, difficulty_normalizer, raw, expected):
        """All 10 luogu difficulty tiers map to correct 1-10 values."""
        assert difficulty_normalizer.normalize("luogu", raw) == expected
