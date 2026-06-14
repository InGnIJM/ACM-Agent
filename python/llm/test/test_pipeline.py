"""Tests for ProblemPipeline and CLI arg parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.pipeline import (
    ProblemPipeline,
    _read_problems,
    _write_problems,
    build_parser,
    parse_args,
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_RAW_PROBLEM: Dict[str, Any] = {
    "platform": "leetcode",
    "source_id": "525",
    "title": "Contiguous Array",
    "difficulty_raw": "Medium",
    "tags_platform": ["Prefix Sum", "Hash Map"],
    "full_content": "Given a binary array nums, return the maximum length...",
}


MOCK_SUMMARY_RESULT: Dict[str, Any] = {
    "summary": "Find the longest subarray with equal 0s and 1s.",
    "solution_approach": "prefix_sum + hash_map",
    "key_points": ["Transform 0 to -1.", "Use prefix sums in a hash map."],
    "pitfalls": ["Empty array edge case."],
    "tags_normalized": ["prefix_sum", "hash_map"],
    "difficulty_normalized": 5.0,
    "similar_problems_hint": "Similar to LeetCode 525.",
}

MOCK_EMBEDDING_DIM = 1536


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_summarizer() -> MagicMock:
    """Return a mock ProblemSummarizer whose ``summarize`` returns preset data."""
    mock = MagicMock()
    mock.summarize = AsyncMock(return_value=dict(MOCK_SUMMARY_RESULT))
    mock._format_summary = MagicMock(return_value="Formatted summary text.")
    return mock


def _make_mock_embedder() -> MagicMock:
    """Return a mock ProblemEmbedder that attaches fake embedding vectors."""
    mock = MagicMock()

    async def _embed_problems(problems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for p in problems:
            p["vector_embedding"] = [0.1] * MOCK_EMBEDDING_DIM
            p["content_vector"] = [0.2] * MOCK_EMBEDDING_DIM
        return problems

    mock.embed_problems = _embed_problems
    return mock


def _make_pipeline() -> ProblemPipeline:
    """Create a ProblemPipeline with mocked summarizer and embedder."""
    db = MagicMock()
    llm = MagicMock()
    openai_client = MagicMock()
    pipeline = ProblemPipeline(db=db, llm=llm, openai_client=openai_client)
    pipeline._summarizer = _make_mock_summarizer()
    pipeline._embedder = _make_mock_embedder()
    return pipeline


# ---------------------------------------------------------------------------
# process_problem
# ---------------------------------------------------------------------------


class TestProcessProblem:
    """Tests for ProblemPipeline.process_problem."""

    @pytest.mark.asyncio
    async def test_returns_enriched_dict_with_all_expected_keys(self):
        """The enriched problem must include normalized, summary, and embedding keys."""
        pipeline = _make_pipeline()
        result = await pipeline.process_problem(SAMPLE_RAW_PROBLEM)

        # Original keys preserved
        assert result["platform"] == "leetcode"
        assert result["source_id"] == "525"
        assert result["title"] == "Contiguous Array"
        assert result["full_content"] == SAMPLE_RAW_PROBLEM["full_content"]

        # Step 1: deterministic normalization
        assert "tags_normalized" in result
        assert isinstance(result["tags_normalized"], list)
        assert "difficulty_normalized" in result
        # LeetCode difficulty map uses int literals (e.g. 5); accept any numeric type
        assert isinstance(result["difficulty_normalized"], (int, float))

        # Step 2: LLM summary fields
        assert result["summary"] == MOCK_SUMMARY_RESULT["summary"]
        assert result["solution_approach"] == MOCK_SUMMARY_RESULT["solution_approach"]
        assert result["key_points"] == MOCK_SUMMARY_RESULT["key_points"]
        assert result["pitfalls"] == MOCK_SUMMARY_RESULT["pitfalls"]
        assert result["similar_problems_hint"] == MOCK_SUMMARY_RESULT["similar_problems_hint"]
        assert result["solution_summary"] == "Formatted summary text."

        # Step 3: embedding vectors
        assert "vector_embedding" in result
        assert len(result["vector_embedding"]) == MOCK_EMBEDDING_DIM
        assert "content_vector" in result
        assert len(result["content_vector"]) == MOCK_EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_does_not_mutate_input_dict(self):
        """process_problem must return a new dict and leave the original unchanged."""
        original = dict(SAMPLE_RAW_PROBLEM)
        original_keys = set(original.keys())

        pipeline = _make_pipeline()
        result = await pipeline.process_problem(original)

        # Original dict must not gain new keys
        assert set(original.keys()) == original_keys
        # Result is a different object
        assert result is not original

    @pytest.mark.asyncio
    async def test_normalization_called_with_correct_arguments(self):
        """Tag and difficulty normalizers are invoked with platform-specific args."""
        pipeline = _make_pipeline()

        # Use real normalizers for this test (they are deterministic)
        from llm.normalizer import DifficultyNormalizer, TagNormalizer

        real_tag = TagNormalizer()
        real_diff = DifficultyNormalizer()
        pipeline._tag_normalizer = real_tag
        pipeline._diff_normalizer = real_diff

        problem = {
            "platform": "leetcode",
            "source_id": "1",
            "title": "Two Sum",
            "difficulty_raw": "Easy",
            "tags_platform": ["Two Pointers", "UnknownXYZ"],
            "full_content": "content",
        }

        result = await pipeline.process_problem(problem)

        # Known LeetCode tag → normalized
        assert "two_pointers" in result["tags_normalized"]
        # Unknown tag → unmapped: prefix
        assert "unmapped:UnknownXYZ" in result["tags_normalized"]
        # LeetCode Easy → 3.0
        assert result["difficulty_normalized"] == 3.0

    @pytest.mark.asyncio
    async def test_summarizer_called_once(self):
        """summarizer.summarize must be called exactly once per problem."""
        pipeline = _make_pipeline()

        # We already swapped _summarizer in _make_pipeline; verify call count.
        await pipeline.process_problem(SAMPLE_RAW_PROBLEM)
        pipeline._summarizer.summarize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embedder_called_with_solution_summary_and_content(self):
        """embedder.embed_problems must receive the problem with solution_summary set."""
        pipeline = _make_pipeline()

        # Wrap embed_problems to capture the argument
        captured: List[List[Dict[str, Any]]] = []

        async def _capture_embed(problems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            captured.append(problems)
            for p in problems:
                p["vector_embedding"] = [0.1] * MOCK_EMBEDDING_DIM
                p["content_vector"] = [0.2] * MOCK_EMBEDDING_DIM
            return problems

        pipeline._embedder.embed_problems = _capture_embed

        await pipeline.process_problem(SAMPLE_RAW_PROBLEM)

        assert len(captured) == 1
        sent_problem = captured[0][0]
        # At this point solution_summary must exist (from _format_summary)
        assert "solution_summary" in sent_problem
        assert "full_content" in sent_problem

    @pytest.mark.asyncio
    async def test_unknown_platform_uses_defaults(self):
        """Unknown platform should not crash; uses default normalization."""
        pipeline = _make_pipeline()
        problem = {
            "platform": "mysterious_oj",
            "source_id": "X",
            "title": "???",
            "difficulty_raw": "???",
            "tags_platform": ["weird_tag"],
            "full_content": "???",
        }
        result = await pipeline.process_problem(problem)

        # Unknown platform → all tags unmapped
        assert result["tags_normalized"] == ["unmapped:weird_tag"]
        # Unknown platform difficulty → default 5.0
        assert result["difficulty_normalized"] == 5.0


# ---------------------------------------------------------------------------
# process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    """Tests for ProblemPipeline.process_batch."""

    @pytest.mark.asyncio
    async def test_all_successful_returns_correct_stats(self):
        """When every problem succeeds, stats show processed=total and errors=0."""
        pipeline = _make_pipeline()
        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(5)]
        # Give each a unique source_id
        for i, p in enumerate(problems):
            p["source_id"] = str(i)

        stats = await pipeline.process_batch(problems)
        assert stats == {"processed": 5, "errors": 0}

    @pytest.mark.asyncio
    async def test_partial_failures_handled_gracefully(self):
        """When some problems fail the batch continues and errors are counted."""
        pipeline = _make_pipeline()
        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(4)]
        for i, p in enumerate(problems):
            p["source_id"] = str(i)

        # Make process_problem fail for problems with source_id "1" or "3"
        original_process = pipeline.process_problem

        async def _flaky_process(raw: Dict[str, Any]) -> Dict[str, Any]:
            if raw["source_id"] in ("1", "3"):
                raise RuntimeError(f"Simulated failure for {raw['source_id']}")
            return await original_process(raw)

        pipeline.process_problem = _flaky_process

        stats = await pipeline.process_batch(problems)
        assert stats == {"processed": 2, "errors": 2}

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero_stats(self):
        """Empty input produces zero processed and zero errors."""
        pipeline = _make_pipeline()
        stats = await pipeline.process_batch([])
        assert stats == {"processed": 0, "errors": 0}

    @pytest.mark.asyncio
    async def test_all_failures_returns_zero_processed(self):
        """When every problem fails, processed=0 and errors=total."""
        pipeline = _make_pipeline()
        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(3)]

        async def _always_fail(_raw: Dict[str, Any]) -> Dict[str, Any]:
            raise RuntimeError("boom")

        pipeline.process_problem = _always_fail

        stats = await pipeline.process_batch(problems)
        assert stats == {"processed": 0, "errors": 3}

    @pytest.mark.asyncio
    async def test_upsert_called_for_each_successful_problem(self):
        """_upsert_problem is called once per successful problem."""
        pipeline = _make_pipeline()
        pipeline._upsert_problem = AsyncMock()

        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(3)]
        for i, p in enumerate(problems):
            p["source_id"] = str(i)

        await pipeline.process_batch(problems)

        assert pipeline._upsert_problem.await_count == 3

    @pytest.mark.asyncio
    async def test_upsert_not_called_for_failed_problems(self):
        """_upsert_problem is skipped when process_problem raises."""
        pipeline = _make_pipeline()
        pipeline._upsert_problem = AsyncMock()

        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(2)]
        for i, p in enumerate(problems):
            p["source_id"] = str(i)

        # First succeeds, second fails
        call_count = 0

        async def _one_success(raw: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("fail")
            return await _make_pipeline().process_problem(raw)

        pipeline.process_problem = _one_success

        await pipeline.process_batch(problems)
        assert pipeline._upsert_problem.await_count == 1


# ---------------------------------------------------------------------------
# CLI arg parsing
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for CLI argument parsing."""

    def test_build_parser_returns_parser(self):
        """build_parser returns an ArgumentParser instance."""
        import argparse

        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_parse_args_process_action(self):
        """--action process with all flags parses correctly."""
        args = parse_args(
            ["--platform", "leetcode", "--action", "process", "--count", "50", "--date", "2026-06-01"]
        )
        assert args.platform == "leetcode"
        assert args.action == "process"
        assert args.count == 50
        assert args.date == "2026-06-01"

    def test_parse_args_re_embed_action(self):
        """--action re-embed parses correctly."""
        args = parse_args(
            ["--platform", "codeforces", "--action", "re-embed", "--count", "0"]
        )
        assert args.platform == "codeforces"
        assert args.action == "re-embed"
        assert args.count == 0

    def test_parse_args_required_flags_enforced(self):
        """--platform and --action are required."""
        with pytest.raises(SystemExit):
            parse_args([])

        with pytest.raises(SystemExit):
            parse_args(["--platform", "luogu"])

    def test_parse_args_invalid_action_rejected(self):
        """Invalid --action value triggers a SystemExit."""
        with pytest.raises(SystemExit):
            parse_args(["--platform", "luogu", "--action", "invalid"])

    def test_parse_args_count_default(self):
        """--count defaults to 100 when omitted."""
        args = parse_args(["--platform", "luogu", "--action", "process"])
        assert args.count == 100

    def test_parse_args_date_default_is_today(self):
        """--date defaults to today's date in ISO format."""
        from datetime import date

        args = parse_args(["--platform", "luogu", "--action", "process"])
        assert args.date == date.today().isoformat()

    def test_parse_args_count_zero(self):
        """--count 0 means unlimited."""
        args = parse_args(["--platform", "atcoder", "--action", "re-embed", "--count", "0"])
        assert args.count == 0


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


class TestFileIO:
    """Tests for _read_problems and _write_problems helpers."""

    def test_read_problems_returns_parsed_json(self, tmp_path: Path):
        """_read_problems reads and parses all .json files in the directory."""
        problems_dir = tmp_path / "data" / "raw" / "cf" / "2026-06-01" / "problems"
        problems_dir.mkdir(parents=True)

        (problems_dir / "p1.json").write_text(
            json.dumps({"source_id": "p1", "title": "Prob 1"}), encoding="utf-8"
        )
        (problems_dir / "p2.json").write_text(
            json.dumps({"source_id": "p2", "title": "Prob 2"}), encoding="utf-8"
        )
        # A non-json file should be ignored
        (problems_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

        problems = _read_problems("cf", "2026-06-01", tmp_path)
        assert len(problems) == 2
        assert problems[0]["source_id"] == "p1"
        assert problems[1]["source_id"] == "p2"

    def test_read_problems_missing_directory_raises(self, tmp_path: Path):
        """FileNotFoundError when the problems directory does not exist."""
        with pytest.raises(FileNotFoundError, match="Problems directory not found"):
            _read_problems("no_platform", "2099-01-01", tmp_path)

    def test_read_problems_empty_directory_returns_empty_list(self, tmp_path: Path):
        """An empty directory yields an empty list."""
        problems_dir = tmp_path / "data" / "raw" / "luogu" / "2026-01-01" / "problems"
        problems_dir.mkdir(parents=True)
        problems = _read_problems("luogu", "2026-01-01", tmp_path)
        assert problems == []

    def test_write_problems_creates_files(self, tmp_path: Path):
        """_write_problems writes each problem to a separate JSON file."""
        problems = [
            {"source_id": "A", "title": "First"},
            {"source_id": "B", "title": "Second"},
        ]
        _write_problems(problems, "leetcode", "2026-06-13", tmp_path)

        out_dir = tmp_path / "data" / "raw" / "leetcode" / "2026-06-13" / "problems"
        assert out_dir.is_dir()

        files = sorted(out_dir.glob("*.json"))
        assert len(files) == 2
        assert files[0].name == "A.json"
        assert files[1].name == "B.json"

        with open(files[0], "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["title"] == "First"

    def test_write_problems_missing_source_id(self, tmp_path: Path):
        """Problems without source_id fall back to 'unknown'.json."""
        problems = [{"title": "No ID"}]
        _write_problems(problems, "cf", "2026-01-01", tmp_path)

        out_file = (
            tmp_path / "data" / "raw" / "cf" / "2026-01-01" / "problems" / "unknown.json"
        )
        assert out_file.is_file()

    def test_write_problems_handles_unicode(self, tmp_path: Path):
        """Unicode titles are written and read correctly."""
        problems = [{"source_id": "1", "title": "动态规划入门"}]
        _write_problems(problems, "luogu", "2026-06-01", tmp_path)

        out_file = (
            tmp_path / "data" / "raw" / "luogu" / "2026-06-01" / "problems" / "1.json"
        )
        with open(out_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["title"] == "动态规划入门"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge-case and robustness tests for ProblemPipeline."""

    @pytest.mark.asyncio
    async def test_minimal_problem_with_empty_fields(self):
        """A problem with only platform and source_id must not crash."""
        pipeline = _make_pipeline()
        minimal = {
            "platform": "codeforces",
            "source_id": "1A",
        }
        result = await pipeline.process_problem(minimal)

        assert result["platform"] == "codeforces"
        assert result["source_id"] == "1A"
        # Defaults for missing fields
        assert result["tags_normalized"] == []
        assert result["difficulty_normalized"] == 5.0
        assert "vector_embedding" in result
        assert "content_vector" in result

    @pytest.mark.asyncio
    async def test_missing_platform_defaults_to_unknown(self):
        """When platform is absent, 'unknown' is used."""
        pipeline = _make_pipeline()
        result = await pipeline.process_problem({"source_id": "X"})

        # Default difficulty for unknown platform is 5.0
        assert result["difficulty_normalized"] == 5.0
        assert result["tags_normalized"] == []

    @pytest.mark.asyncio
    async def test_summarizer_raises_is_propagated_from_process_problem(self):
        """If the summarizer raises, process_problem must propagate that error."""
        pipeline = _make_pipeline()
        pipeline._summarizer.summarize = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )

        with pytest.raises(RuntimeError, match="LLM timeout"):
            await pipeline.process_problem(SAMPLE_RAW_PROBLEM)

    @pytest.mark.asyncio
    async def test_embedder_raises_is_propagated_from_process_problem(self):
        """If the embedder raises, process_problem must propagate that error."""
        pipeline = _make_pipeline()

        async def _failing_embed(problems):
            raise RuntimeError("Embedding API down")

        pipeline._embedder.embed_problems = _failing_embed

        with pytest.raises(RuntimeError, match="Embedding API down"):
            await pipeline.process_problem(SAMPLE_RAW_PROBLEM)

    @pytest.mark.asyncio
    async def test_process_batch_isolates_embedder_failure(self):
        """When the embedder fails for one problem, others still complete."""
        pipeline = _make_pipeline()
        problems = [dict(SAMPLE_RAW_PROBLEM) for _ in range(3)]
        for i, p in enumerate(problems):
            p["source_id"] = str(i)

        # Fail embedder for problem "1" only
        original_process = pipeline.process_problem

        async def _flaky(raw):
            if raw["source_id"] == "1":
                raise RuntimeError("Embedding failed")
            return await original_process(raw)

        pipeline.process_problem = _flaky

        stats = await pipeline.process_batch(problems)
        assert stats["processed"] == 2
        assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# CLI runner functions (integration-light, dependency-mocked)
# ---------------------------------------------------------------------------


class TestRunProcess:
    """Tests for _run_process."""

    @pytest.mark.asyncio
    async def test_run_process_with_count_limit(self):
        """_run_process reads problems, applies count limit, returns stats."""
        from llm.pipeline import _run_process

        db = MagicMock()
        llm = MagicMock()
        openai_client = MagicMock()

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline.ProblemPipeline") as MockPipeline:
            mock_read.return_value = [
                {"source_id": str(i), "platform": "cf"} for i in range(10)
            ]
            mock_instance = MockPipeline.return_value
            mock_instance.process_batch = AsyncMock(
                return_value={"processed": 5, "errors": 0}
            )

            stats = await _run_process(
                platform="cf",
                count=5,
                date_str="2026-06-01",
                db=db,
                llm=llm,
                openai_client=openai_client,
                base_dir=Path("/fake"),
            )

            # Only first 5 passed to pipeline
            problems_sent = mock_instance.process_batch.call_args[0][0]
            assert len(problems_sent) == 5
            assert stats == {"processed": 5, "errors": 0}

    @pytest.mark.asyncio
    async def test_run_process_count_zero_means_all(self):
        """count=0 means no slicing (all problems)."""
        from llm.pipeline import _run_process

        db = MagicMock()
        llm = MagicMock()
        openai_client = MagicMock()

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline.ProblemPipeline") as MockPipeline:
            mock_read.return_value = [
                {"source_id": str(i)} for i in range(20)
            ]
            mock_instance = MockPipeline.return_value
            mock_instance.process_batch = AsyncMock(
                return_value={"processed": 20, "errors": 0}
            )

            stats = await _run_process(
                platform="lc",
                count=0,
                date_str="2026-06-01",
                db=db,
                llm=llm,
                openai_client=openai_client,
                base_dir=Path("/fake"),
            )

            problems_sent = mock_instance.process_batch.call_args[0][0]
            assert len(problems_sent) == 20
            assert stats == {"processed": 20, "errors": 0}

    @pytest.mark.asyncio
    async def test_run_process_default_base_dir(self):
        """When base_dir is None, _project_root() is used."""
        from llm.pipeline import _run_process

        db = MagicMock()
        llm = MagicMock()
        openai_client = MagicMock()

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline.ProblemPipeline") as MockPipeline:
            mock_read.return_value = []
            mock_instance = MockPipeline.return_value
            mock_instance.process_batch = AsyncMock(
                return_value={"processed": 0, "errors": 0}
            )

            stats = await _run_process(
                platform="cf",
                count=10,
                date_str="2026-06-01",
                db=db,
                llm=llm,
                openai_client=openai_client,
                base_dir=None,
            )

            # _read_problems was called with a Path (from _project_root)
            called_base_dir = mock_read.call_args[0][2]
            assert isinstance(called_base_dir, Path)
            assert stats == {"processed": 0, "errors": 0}


class TestRunReEmbed:
    """Tests for _run_re_embed."""

    @pytest.mark.asyncio
    async def test_run_re_embed_writes_enriched_problems(self):
        """_run_re_embed reads, embeds, and writes problems."""
        from llm.pipeline import _run_re_embed

        openai_client = MagicMock()
        raw_problems = [
            {"source_id": "A", "full_content": "a"},
            {"source_id": "B", "full_content": "b"},
        ]

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline._write_problems") as mock_write, \
             patch("llm.pipeline.ProblemEmbedder") as MockEmbedder:
            mock_read.return_value = list(raw_problems)
            mock_instance = MockEmbedder.return_value

            async def _fake_embed(problems):
                for p in problems:
                    p["vector_embedding"] = [0.1] * 10
                    p["content_vector"] = [0.2] * 10
                return problems

            mock_instance.embed_problems = _fake_embed

            stats = await _run_re_embed(
                platform="lc",
                count=2,
                date_str="2026-06-01",
                openai_client=openai_client,
                base_dir=Path("/fake"),
            )

            assert stats == {"re_embedded": 2}
            mock_write.assert_called_once()
            # The written problems should have embeddings attached
            written = mock_write.call_args[0][0]
            assert "vector_embedding" in written[0]
            assert "content_vector" in written[0]

    @pytest.mark.asyncio
    async def test_run_re_embed_count_limit(self):
        """count > 0 limits the number of re-embedded problems."""
        from llm.pipeline import _run_re_embed

        openai_client = MagicMock()

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline._write_problems") as mock_write, \
             patch("llm.pipeline.ProblemEmbedder") as MockEmbedder:
            mock_read.return_value = [
                {"source_id": str(i)} for i in range(10)
            ]
            mock_instance = MockEmbedder.return_value
            mock_instance.embed_problems = AsyncMock(
                return_value=[{"source_id": str(i), "vector_embedding": []} for i in range(3)]
            )

            stats = await _run_re_embed(
                platform="lc",
                count=3,
                date_str="2026-06-01",
                openai_client=openai_client,
                base_dir=Path("/fake"),
            )

            embedded = mock_instance.embed_problems.call_args[0][0]
            assert len(embedded) == 3
            assert stats == {"re_embedded": 3}

    @pytest.mark.asyncio
    async def test_run_re_embed_default_base_dir(self):
        """When base_dir is None, _project_root() is used."""
        from llm.pipeline import _run_re_embed

        openai_client = MagicMock()

        with patch("llm.pipeline._read_problems") as mock_read, \
             patch("llm.pipeline._write_problems") as mock_write, \
             patch("llm.pipeline.ProblemEmbedder") as MockEmbedder:
            mock_read.return_value = []
            mock_instance = MockEmbedder.return_value
            mock_instance.embed_problems = AsyncMock(return_value=[])

            stats = await _run_re_embed(
                platform="cf",
                count=0,
                date_str="2026-06-01",
                openai_client=openai_client,
                base_dir=None,
            )

            called_base_dir = mock_read.call_args[0][2]
            assert isinstance(called_base_dir, Path)
            assert stats == {"re_embedded": 0}


class TestMainAsync:
    """Tests for main_async."""

    @pytest.mark.asyncio
    async def test_main_async_process_action(self):
        """main_async with --action process triggers _run_process."""
        from llm.pipeline import main_async

        argv = ["--platform", "leetcode", "--action", "process", "--count", "5"]

        with patch("llm.pipeline._run_process") as mock_run_process, \
             patch("llm.pipeline._project_root") as mock_root, \
             patch("openai.AsyncOpenAI") as mock_async_openai, \
             patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
            mock_run_process.return_value = {"processed": 5, "errors": 0}
            mock_root.return_value = Path("/fake/project")

            await main_async(argv)

            mock_run_process.assert_awaited_once()
            call_kwargs = mock_run_process.call_args.kwargs
            assert call_kwargs["platform"] == "leetcode"
            assert call_kwargs["count"] == 5

    @pytest.mark.asyncio
    async def test_main_async_re_embed_action(self):
        """main_async with --action re-embed triggers _run_re_embed."""
        from llm.pipeline import main_async

        argv = ["--platform", "codeforces", "--action", "re-embed", "--count", "0"]

        with patch("llm.pipeline._run_re_embed") as mock_run_re_embed, \
             patch("llm.pipeline._project_root") as mock_root, \
             patch("openai.AsyncOpenAI") as mock_async_openai:
            mock_run_re_embed.return_value = {"re_embedded": 10}
            mock_root.return_value = Path("/fake/project")

            await main_async(argv)

            mock_run_re_embed.assert_awaited_once()
            call_kwargs = mock_run_re_embed.call_args.kwargs
            assert call_kwargs["platform"] == "codeforces"
            assert call_kwargs["count"] == 0

    @pytest.mark.asyncio
    async def test_main_async_process_action_without_count(self):
        """Default count is applied when not specified."""
        from llm.pipeline import main_async

        argv = ["--platform", "luogu", "--action", "process"]

        with patch("llm.pipeline._run_process") as mock_run_process, \
             patch("llm.pipeline._project_root") as mock_root, \
             patch("openai.AsyncOpenAI") as mock_async_openai, \
             patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
            mock_run_process.return_value = {"processed": 100, "errors": 0}
            mock_root.return_value = Path("/fake/project")

            await main_async(argv)

            call_kwargs = mock_run_process.call_args.kwargs
            assert call_kwargs["count"] == 100  # default


class TestMain:
    """Tests for the synchronous main wrapper."""

    def test_main_calls_asyncio_run(self):
        """main() delegates to asyncio.run(main_async)."""
        from llm.pipeline import main

        with patch("llm.pipeline.asyncio.run") as mock_asyncio_run:
            main(["--platform", "cf", "--action", "process"])
            mock_asyncio_run.assert_called_once()

    def test_main_no_args_triggers_system_exit(self):
        """No arguments causes argparse to exit."""
        from llm.pipeline import main

        with pytest.raises(SystemExit):
            main([])
