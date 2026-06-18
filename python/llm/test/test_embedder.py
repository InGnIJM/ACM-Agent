"""Tests for ProblemEmbedder with a mocked OpenAI client."""

import asyncio
from unittest.mock import MagicMock

import pytest

from llm.embedder import ProblemEmbedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(embedding_dim: int = 1536, fail_count: int = 0) -> MagicMock:
    """Build a mock OpenAI client whose ``embeddings.create`` returns fake vectors.

    Args:
        embedding_dim: Dimension of each returned embedding vector.
        fail_count: If > 0, the first *fail_count* calls raise RuntimeError
                    before subsequent calls succeed.
    """
    client = MagicMock()
    calls: list[int] = [0]  # mutable counter

    async def _create(*, model: str, input: list[str]) -> MagicMock:
        calls[0] += 1
        if calls[0] <= fail_count:
            raise RuntimeError(f"Simulated API failure #{calls[0]}")

        response = MagicMock()
        response.data = [
            MagicMock(embedding=[0.1] * embedding_dim) for _ in input
        ]
        return response

    client.embeddings.create = _create
    return client


# ---------------------------------------------------------------------------
# embed_batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_batch_returns_correct_number_of_vectors():
    """embed_batch returns one vector per input text."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    texts = ["alpha", "beta", "gamma", "delta"]
    vectors = await embedder.embed_batch(texts)
    assert len(vectors) == 4
    assert all(len(v) == 1536 for v in vectors)


@pytest.mark.asyncio
async def test_embed_batch_splits_into_correct_batch_sizes():
    """embed_batch respects batch_size and calls the API the expected number of times."""
    client = _make_mock_client()
    batch_size = 3
    embedder = ProblemEmbedder(client, batch_size=batch_size, backend="openai")
    texts = ["a", "b", "c", "d", "e"]  # 5 texts → ceil(5/3) = 2 batches
    _ = await embedder.embed_batch(texts)

    # Count how many times the mock was called
    call_count = 0

    async def _counting_create(*, model: str, input: list[str]) -> MagicMock:
        nonlocal call_count
        call_count += 1
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
        return response

    client.embeddings.create = _counting_create
    vectors = await embedder.embed_batch(texts)
    assert len(vectors) == 5
    assert call_count == 2  # batch of 3 + batch of 2


@pytest.mark.asyncio
async def test_embed_batch_retries_on_failure():
    """embed_batch retries transient failures (up to 3 retries) and still succeeds."""
    client = _make_mock_client(fail_count=2)  # fails twice, then succeeds
    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    texts = ["x", "y"]
    vectors = await embedder.embed_batch(texts)
    assert len(vectors) == 2


@pytest.mark.asyncio
async def test_embed_batch_exhausts_retries():
    """embed_batch raises RuntimeError after 4 total attempts (1 initial + 3 retries)."""
    client = _make_mock_client(fail_count=99)  # always fails
    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    with pytest.raises(RuntimeError, match="4 attempts"):
        await embedder.embed_batch(["test"])


@pytest.mark.asyncio
async def test_embed_batch_empty_list():
    """embed_batch returns an empty list immediately for empty input."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, backend="openai")
    vectors = await embedder.embed_batch([])
    assert vectors == []


# ---------------------------------------------------------------------------
# embed_problems
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_problems_creates_both_parent_and_content_vectors():
    """embed_problems attaches vector_embedding and content_vector to each problem."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    problems = [
        {"id": "p1", "solution_summary": "sum1", "full_content": "cont1"},
        {"id": "p2", "solution_summary": "sum2", "full_content": "cont2"},
    ]
    result = await embedder.embed_problems(problems)

    assert len(result) == 2
    for p in result:
        assert "vector_embedding" in p
        assert "content_vector" in p
        assert len(p["vector_embedding"]) == 1536
        assert len(p["content_vector"]) == 1536


@pytest.mark.asyncio
async def test_embed_problems_empty_list():
    """embed_problems returns the list unchanged for empty input."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, backend="openai")
    result = await embedder.embed_problems([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_problems_handles_missing_keys():
    """embed_problems treats missing solution_summary / full_content as empty string."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    problems = [{"id": "p1"}]  # no summary or content
    result = await embedder.embed_problems(problems)
    assert len(result) == 1
    assert "vector_embedding" in result[0]
    assert "content_vector" in result[0]


# ---------------------------------------------------------------------------
# embed_solutions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_solutions_truncates_long_content():
    """embed_solutions truncates content > 2000 chars before embedding."""
    client = _make_mock_client()

    # Capture what was sent to the API
    sent_inputs: list[str] = []

    async def _capture_create(*, model: str, input: list[str]) -> MagicMock:
        sent_inputs.extend(input)
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
        return response

    client.embeddings.create = _capture_create

    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    long_text = "x" * 3000
    solutions = [{"id": "s1", "content": long_text}]
    result = await embedder.embed_solutions(solutions)

    assert len(result) == 1
    assert "vector_embedding" in result[0]
    assert len(result[0]["vector_embedding"]) == 1536
    # The text sent to the API must be truncated
    assert sent_inputs[0] == long_text[:2000]
    assert len(sent_inputs[0]) == 2000


@pytest.mark.asyncio
async def test_embed_solutions_shorter_than_2000_chars():
    """embed_solutions does not modify content under the 2000-char limit."""
    client = _make_mock_client()

    sent_inputs: list[str] = []

    async def _capture_create(*, model: str, input: list[str]) -> MagicMock:
        sent_inputs.extend(input)
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
        return response

    client.embeddings.create = _capture_create

    embedder = ProblemEmbedder(client, batch_size=10, backend="openai")
    short_text = "hello world"
    solutions = [{"id": "s1", "content": short_text}]
    result = await embedder.embed_solutions(solutions)

    assert len(result) == 1
    assert sent_inputs[0] == short_text
    assert len(result[0]["vector_embedding"]) == 1536


@pytest.mark.asyncio
async def test_embed_solutions_empty_list():
    """embed_solutions returns the list unchanged for empty input."""
    client = _make_mock_client()
    embedder = ProblemEmbedder(client, backend="openai")
    result = await embedder.embed_solutions([])
    assert result == []
