"""Problem and solution embedding via OpenAI text-embedding-3-small."""

import asyncio
from typing import Any


class ProblemEmbedder:
    """Embeds problems and solutions using OpenAI's embedding API with batching and retry."""

    def __init__(self, openai_client: Any, batch_size: int = 500) -> None:
        """Initialize with an OpenAI client instance and configurable batch size.

        Args:
            openai_client: An OpenAI / AsyncOpenAI client instance (must expose
                           ``client.embeddings.create``).
            batch_size: Max texts per embedding API call (default 500).
        """
        self._client = openai_client
        self._batch_size = batch_size

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Process *texts* in batches of *batch_size*, retrying on failure.

        Args:
            texts: List of strings to embed.

        Returns:
            Flat list of embedding vectors, one per input text, in original order.
        """
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            embeddings = await self._embed_one_batch(batch)
            results.extend(embeddings)
        return results

    async def _embed_one_batch(self, batch: list[str]) -> list[list[float]]:
        """Call the embedding API for one batch, with up to 3 retries (exponential
        backoff: 2^n seconds)."""
        last_exc: Exception | None = None
        for attempt in range(4):  # 0=initial, 1-3=retries
            try:
                response = await self._client.embeddings.create(
                    model="text-embedding-3-small",
                    input=batch,
                )
                # Data is returned in input order by the API
                return [item.embedding for item in response.data]
            except Exception as exc:
                last_exc = exc
                if attempt < 3:  # 0,1,2 → sleep before retry 1,2,3
                    await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError(
            f"Embedding API call failed after 4 attempts (3 retries)"
        ) from last_exc

    async def embed_problems(self, problems: list[dict]) -> list[dict]:
        """Embed problems by creating a parent vector from ``solution_summary``
        and a content vector from ``full_content``.

        Each problem dict is mutated in-place by adding:

        - ``vector_embedding``    – embedding of ``solution_summary``
        - ``content_vector``      – embedding of ``full_content``
        """
        if not problems:
            return problems

        # Parent vectors from solution_summary
        summaries = [
            p.get("solution_summary", "") or "" for p in problems
        ]
        parent_vectors = await self.embed_batch(summaries)

        # Content vectors from full_content
        contents = [
            p.get("full_content", "") or "" for p in problems
        ]
        content_vectors = await self.embed_batch(contents)

        for prob, pvec, cvec in zip(problems, parent_vectors, content_vectors):
            prob["vector_embedding"] = pvec
            prob["content_vector"] = cvec

        return problems

    async def embed_solutions(self, solutions: list[dict]) -> list[dict]:
        """Embed solutions by vectorising their content (truncated to 2000 chars).

        Each solution dict is mutated in-place by adding:

        - ``vector_embedding`` – embedding of (truncated) ``content``
        """
        if not solutions:
            return solutions

        truncated = [
            (s.get("content", "") or "")[:2000] for s in solutions
        ]
        vectors = await self.embed_batch(truncated)

        for sol, vec in zip(solutions, vectors):
            sol["vector_embedding"] = vec

        return solutions
