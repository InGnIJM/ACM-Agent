"""
Local embedding server — OpenAI-compatible /v1/embeddings endpoint.

Powered by BAAI/bge-m3 via FlagEmbedding.  Run with:

    python embedding_server.py

Default: http://localhost:8765
"""

from __future__ import annotations

import os

# Use HuggingFace mirror in China (set before any HF import)
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals (set at startup)
# ---------------------------------------------------------------------------
_MODEL: Any = None
_MODEL_NAME: str = "BAAI/bge-m3"
_DIM: int = 1024
_MAX_BATCH: int = 500
_DEVICE: str = "cuda" if os.environ.get("EMBED_DEVICE") != "cpu" else "cpu"
_USE_FP16: bool = os.environ.get("EMBED_FP16", "1") != "0"


# ---------------------------------------------------------------------------
# Pydantic schemas (OpenAI-compatible)
# ---------------------------------------------------------------------------
class EmbeddingRequest(BaseModel):
    input: str | List[str] | List[int] | List[List[int]] = Field(..., description="Text(s) to embed")
    model: str = Field(default="bge-m3", description="Model name")
    encoding_format: str = Field(default="float", description="float | base64")
    user: str | None = Field(default=None)


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]


class Usage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: Usage


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _MODEL, _MODEL_NAME, _DIM
    _MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

    if "large-zh" in _MODEL_NAME:
        _DIM = 1024
    elif "base-zh" in _MODEL_NAME:
        _DIM = 768
    elif "small-zh" in _MODEL_NAME:
        _DIM = 512
    elif "bge-m3" in _MODEL_NAME:
        _DIM = 1024
    else:
        _DIM = 1024  # default

    logger.info("Loading %s on %s (fp16=%s) ...", _MODEL_NAME, _DEVICE, _USE_FP16)
    try:
        from FlagEmbedding import BGEM3FlagModel

        _MODEL = BGEM3FlagModel(
            _MODEL_NAME,
            use_fp16=(_DEVICE == "cuda" and _USE_FP16),
            device=_DEVICE,
        )
        logger.info("Model loaded. Dim=%d", _DIM)
    except Exception:
        # Fallback: try sentence-transformers
        logger.warning("FlagEmbedding failed, falling back to sentence-transformers")
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(_MODEL_NAME, device=_DEVICE)
        _DIM = _MODEL.get_sentence_embedding_dimension()
        logger.info("Model loaded (sbert). Dim=%d", _DIM)

    yield
    _MODEL = None


app = FastAPI(title="BGE Embedding Server", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# OpenAI-compatible endpoints
# ---------------------------------------------------------------------------
@app.get("/v1/models")
@app.get("/models")
async def list_models():
    """List available models."""
    return {
        "object": "list",
        "data": [
            {
                "id": _MODEL_NAME.split("/")[-1],
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
@app.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(req: EmbeddingRequest):
    """Create embeddings for given text(s)."""
    if _MODEL is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    # Normalize input to list[str]
    if isinstance(req.input, str):
        texts = [req.input]
    elif isinstance(req.input, list):
        if len(req.input) == 0:
            raise HTTPException(status_code=400, detail="Empty input")
        if isinstance(req.input[0], int):
            # Tokenised input — not supported
            raise HTTPException(status_code=400, detail="Tokenised input not supported, pass raw text")
        if isinstance(req.input[0], list):
            raise HTTPException(status_code=400, detail="Batch tokenised input not supported")
        texts = req.input  # type: ignore[arg-type]
    else:
        raise HTTPException(status_code=400, detail="Invalid input type")

    if len(texts) > _MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(texts)} exceeds max {_MAX_BATCH}",
        )

    # Run embedding in thread pool (BGEM3FlagModel.encode is sync)
    loop = asyncio.get_running_loop()
    embeddings: List[List[float]] = await loop.run_in_executor(
        None, _encode, texts
    )

    data = [
        EmbeddingData(index=i, embedding=vec)
        for i, vec in enumerate(embeddings)
    ]
    # Rough token estimate for usage
    token_count = sum(len(t.encode("utf-8")) // 2 for t in texts)  # approximate

    return EmbeddingResponse(
        object="list",
        data=data,
        model=req.model,
        usage=Usage(prompt_tokens=token_count, total_tokens=token_count),
    )


def _encode(texts: List[str]) -> List[List[float]]:
    """Encode texts with BGE-M3, returning dense vectors (list-of-lists)."""
    if hasattr(_MODEL, "encode"):
        # BGEM3FlagModel
        output = _MODEL.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
            batch_size=min(len(texts), 64),
        )
        return [vec.tolist() for vec in output["dense_vecs"]]
    else:
        # sentence-transformers
        vecs = _MODEL.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": _MODEL_NAME,
        "dim": _DIM,
        "device": _DEVICE,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = int(os.environ.get("EMBED_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
