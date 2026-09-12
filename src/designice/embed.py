"""Pluggable embedding backends.

Resolution order when nothing is forced via DESIGNICE_EMBED_BACKEND:

    voyage  (if VOYAGE_API_KEY)  ->  openai (if OPENAI_API_KEY)  ->  lexical

API backends are the default because they genuinely understand that "a site for
my neobank" and "fintech dashboard" are the same request. But a design library
that refuses to answer without a key is useless, so `lexical` is always there as
a floor - it is pure stdlib TF-IDF over taxonomy-expanded text, and for a few
hundred designs it is a good deal better than it has any right to be.

The API backends talk raw HTTP through urllib on purpose: no SDK to install,
which keeps `designice` importable inside the MCP server with zero setup.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections import Counter
from typing import Any, Iterable, Sequence

from . import taxonomy

EMBED_TIMEOUT = 60


class EmbedError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # surface the provider's message
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise EmbedError(f"{url} returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise EmbedError(f"could not reach {url}: {exc.reason}") from exc


def _batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def enrich(text: str) -> str:
    """Append taxonomy expansions to the text before embedding.

    Short prompts ("landing page for a bank") carry very little to embed. Adding
    the sibling vocabulary of every tag the text implies gives the encoder more
    surface to work with, and pulls the query vector toward the same region of
    space that richly-written design descriptions already occupy.
    """
    extra = taxonomy.expansion_terms(text)
    return f"{text}\n\nRelated concepts: {', '.join(extra)}" if extra else text


class Backend:
    """Interface every backend implements."""

    name = "base"
    dim = 0

    def fit(self, documents: Sequence[str]) -> None:
        """Learn corpus statistics, if the backend needs any. Most don't."""

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    def encode_query(self, query: str) -> list[float]:
        raise NotImplementedError

    def state(self) -> dict[str, Any]:
        """Anything that must be persisted so queries encode like documents did."""
        return {}

    def load_state(self, state: dict[str, Any]) -> None:
        pass


class LexicalBackend(Backend):
    """Stdlib TF-IDF over taxonomy-expanded text. No key, no network, no install.

    The vocabulary and IDF weights are learned at index time and stored in the
    index file, because a query must be projected into exactly the same space
    the documents were - otherwise cosine similarity is meaningless.
    """

    name = "lexical"

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.idf: list[float] = []

    @property
    def dim(self) -> int:  # type: ignore[override]
        return len(self.vocab)

    @staticmethod
    def _terms(text: str) -> list[str]:
        tokens = taxonomy.tokenize(enrich(text))
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        return tokens + bigrams

    def fit(self, documents: Sequence[str]) -> None:
        doc_terms = [set(self._terms(doc)) for doc in documents]
        counts: Counter[str] = Counter()
        for terms in doc_terms:
            counts.update(terms)
        # Keep every term; design libraries are small and rare words are the
        # discriminating ones (a single mention of "terracotta" matters).
        self.vocab = {term: i for i, term in enumerate(sorted(counts))}
        n = max(len(documents), 1)
        self.idf = [0.0] * len(self.vocab)
        for term, idx in self.vocab.items():
            self.idf[idx] = math.log((n + 1) / (counts[term] + 1)) + 1.0

    def _vectorize(self, text: str) -> list[float]:
        vec = [0.0] * len(self.vocab)
        if not vec:
            return vec
        tf = Counter(self._terms(text))
        if not tf:
            return vec
        peak = max(tf.values())
        for term, count in tf.items():
            idx = self.vocab.get(term)
            if idx is not None:
                # Sublinear TF, damped by the document's own peak, so a long
                # description doesn't outrank a tight one purely on length.
                vec[idx] = (0.5 + 0.5 * count / peak) * self.idf[idx]
        return _l2(vec)

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        if not self.vocab:
            self.fit(documents)
        return [self._vectorize(doc) for doc in documents]

    def encode_query(self, query: str) -> list[float]:
        return self._vectorize(query)

    def state(self) -> dict[str, Any]:
        return {"vocab": self.vocab, "idf": self.idf}

    def load_state(self, state: dict[str, Any]) -> None:
        self.vocab = state.get("vocab", {})
        self.idf = state.get("idf", [])


class OpenAIBackend(Backend):
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("DESIGNICE_EMBED_MODEL") or "text-embedding-3-small"
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.dim = 0

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for batch in _batched(texts, 128):
            data = _post_json(
                f"{self.base}/embeddings",
                {"model": self.model, "input": list(batch)},
                {"Authorization": f"Bearer {self.api_key}"},
            )
            rows = sorted(data["data"], key=lambda r: r["index"])
            out.extend(_l2([float(v) for v in row["embedding"]]) for row in rows)
        if out:
            self.dim = len(out[0])
        return out

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        return self._embed([enrich(d) for d in documents])

    def encode_query(self, query: str) -> list[float]:
        return self._embed([enrich(query)])[0]

    def state(self) -> dict[str, Any]:
        return {"model": self.model}


class VoyageBackend(Backend):
    """Voyage distinguishes document and query encodings, which helps retrieval."""

    name = "voyage"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.environ.get("DESIGNICE_EMBED_MODEL") or "voyage-3.5-lite"
        self.api_key = api_key or os.environ.get("VOYAGE_API_KEY", "")
        self.dim = 0

    def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        for batch in _batched(texts, 96):
            data = _post_json(
                "https://api.voyageai.com/v1/embeddings",
                {"model": self.model, "input": list(batch), "input_type": input_type},
                {"Authorization": f"Bearer {self.api_key}"},
            )
            rows = sorted(data["data"], key=lambda r: r["index"])
            out.extend(_l2([float(v) for v in row["embedding"]]) for row in rows)
        if out:
            self.dim = len(out[0])
        return out

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        return self._embed([enrich(d) for d in documents], "document")

    def encode_query(self, query: str) -> list[float]:
        return self._embed([enrich(query)], "query")[0]

    def state(self) -> dict[str, Any]:
        return {"model": self.model}


class SentenceTransformersBackend(Backend):
    name = "local"

    def __init__(self, model: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbedError(
                "the 'local' backend needs sentence-transformers: pip install 'designice[local]'"
            ) from exc
        self.model_name = model or os.environ.get("DESIGNICE_EMBED_MODEL") or "all-MiniLM-L6-v2"
        self._model = SentenceTransformer(self.model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [[float(v) for v in row] for row in vectors]

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        return self._embed([enrich(d) for d in documents])

    def encode_query(self, query: str) -> list[float]:
        return self._embed([enrich(query)])[0]

    def state(self) -> dict[str, Any]:
        return {"model": self.model_name}


def resolve_backend_name(preferred: str | None = None) -> str:
    """Pick a backend. Explicit choice wins, then keys, then the lexical floor."""
    choice = (preferred or os.environ.get("DESIGNICE_EMBED_BACKEND") or "").strip().lower()
    if choice and choice != "auto":
        return choice
    if os.environ.get("VOYAGE_API_KEY"):
        return "voyage"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "lexical"


def get_backend(name: str | None = None, *, allow_fallback: bool = True) -> Backend:
    """Build a backend, degrading to lexical rather than failing the whole run."""
    resolved = resolve_backend_name(name)
    try:
        if resolved == "openai":
            backend = OpenAIBackend()
            if not backend.api_key:
                raise EmbedError("OPENAI_API_KEY is not set")
            return backend
        if resolved == "voyage":
            backend = VoyageBackend()
            if not backend.api_key:
                raise EmbedError("VOYAGE_API_KEY is not set")
            return backend
        if resolved == "local":
            return SentenceTransformersBackend()
        if resolved == "lexical":
            return LexicalBackend()
        raise EmbedError(f"unknown embedding backend: {resolved!r}")
    except EmbedError:
        if allow_fallback and resolved != "lexical":
            return LexicalBackend()
        raise


def backend_from_state(name: str, state: dict[str, Any]) -> Backend:
    """Rebuild the exact backend an index was written with."""
    backend = get_backend(name, allow_fallback=False)
    backend.load_state(state or {})
    return backend


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Both sides are stored L2-normalised, so this is just a dot product."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))
