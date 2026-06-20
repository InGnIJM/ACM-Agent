"""Problem embedding via Ollama (Qwen3-Embedding-0.6B) or OpenAI."""

import asyncio
import json
import os
from typing import Any

import aiohttp


class ProblemEmbedder:
    """Embeds problems using a local Ollama server or OpenAI API.

    Default backend is Ollama (``http://localhost:11434/api/embed``).
    Set ``EMBED_BACKEND=openai`` to use OpenAI instead.

    Only the ``solution_summary`` field is vectorised.
    """

    def __init__(
        self,
        openai_client: Any = None,
        batch_size: int = 500,
        *,
        backend: str | None = None,
        ollama_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Args:
            openai_client: OpenAI / AsyncOpenAI client (only used when backend=="openai").
            batch_size: Max texts per API call (default 500).
            backend: ``"ollama"`` (default) or ``"openai"``.
            ollama_url: Override Ollama API base URL.
            model: Override model name (default: ``qwen3-embedding:0.6b`` for Ollama,
                   ``text-embedding-3-small`` for OpenAI).
        """
        self._openai_client = openai_client
        self._batch_size = batch_size

        self._backend = backend or os.environ.get("EMBED_BACKEND", "ollama")
        self._ollama_url = (ollama_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")

        if model:
            self._model = model
        elif self._backend == "openai":
            self._model = "text-embedding-3-small"
        else:
            self._model = os.environ.get("EMBED_MODEL", "qwen3-embedding:0.6b")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Process *texts* in batches of *batch_size*, retrying on failure.

        Returns one embedding vector per input text, in original order.
        """
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            if self._backend == "openai":
                embeddings = await self._embed_openai(batch)
            else:
                embeddings = await self._embed_ollama(batch)
            results.extend(embeddings)
        return results

    # ------------------------------------------------------------------
    # Ollama backend
    # ------------------------------------------------------------------

    async def _embed_ollama(self, batch: list[str]) -> list[list[float]]:
        """Call Ollama ``/api/embed`` with retries."""
        url = f"{self._ollama_url}/api/embed"
        payload = {"model": self._model, "input": batch}

        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            raise RuntimeError(
                                f"Ollama returned {resp.status}: {body[:500]}"
                            )
                        data = await resp.json()
                        return data["embeddings"]
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError(
            f"Ollama embedding failed after 4 attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # OpenAI backend (fallback)
    # ------------------------------------------------------------------

    async def _embed_openai(self, batch: list[str]) -> list[list[float]]:
        """Call OpenAI ``embeddings.create`` with retries."""
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = await self._openai_client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
                return [item.embedding for item in response.data]
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    await asyncio.sleep(2 ** (attempt + 1))
        raise RuntimeError(
            f"OpenAI embedding failed after 4 attempts: {last_exc}"
        ) from last_exc

    async def embed_problems(self, problems: list[dict]) -> list[dict]:
        """Embed problems by creating a vector from ``solution_summary``.

        Each problem dict is mutated in-place by adding:

        - ``vector_embedding``    – embedding of ``solution_summary``
        """
        if not problems:
            return problems

        summaries = [
            p.get("solution_summary", "") or "" for p in problems
        ]
        vectors = await self.embed_batch(summaries)

        for prob, vec in zip(problems, vectors):
            prob["vector_embedding"] = vec

        return problems
