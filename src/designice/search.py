"""Rank designs against a natural-language prompt.

Three signals, fused:

  dense    cosine against the stored embedding - handles meaning
  lexical  BM25 over the description - handles exact words the encoder blurs
           away, like a brand name or "terracotta"
  tags     overlap between the tags the query implies and the ones the design
           carries - handles the "which field is this for" question directly

Each signal is min-max normalised across the candidate set before fusion, so
the weights mean the same thing whether the vectors came from OpenAI (cosines
clustered around 0.4) or the lexical backend (cosines near 0). Without that,
swapping backends would silently re-weight the whole ranking.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable, Sequence

from . import embed, taxonomy

WEIGHTS = {"dense": 0.60, "lexical": 0.25, "tags": 0.15}

# A single reusable block and a whole marketing site can describe themselves in
# almost identical language, so the text signals cannot tell them apart. Scope
# is a separate question from similarity and deserves its own adjustment:
# someone asking for "a site" does not want a features section that happens to
# use the same words, and someone asking for "a pricing section" does not want
# an entire eleven-section landing page.
SCOPE_PENALTY = 0.72
COMPONENT_TYPES = {"component", "hero", "auth", "error-page"}
PAGE_TYPES = {"landing-page", "marketing-site", "portfolio-page", "dashboard",
              "docs", "app-shell", "blog", "product-detail", "pricing-page"}
# Words that mean "one block", not "a whole site".
_PART_WORDS = {"section", "sections", "component", "components", "block", "blocks",
               "widget", "snippet", "module"}
BM25_K1 = 1.5
BM25_B = 0.75


def _normalise(scores: Sequence[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        # Every candidate scored the same: the signal carries no information
        # here, so give it a flat neutral value rather than a fake spread.
        return [0.0 if hi <= 0 else 1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def _bm25(query_tokens: list[str], docs_tokens: list[list[str]]) -> list[float]:
    n = len(docs_tokens)
    if not n or not query_tokens:
        return [0.0] * n
    avgdl = sum(len(d) for d in docs_tokens) / n or 1.0
    df: Counter[str] = Counter()
    for tokens in docs_tokens:
        df.update(set(tokens))
    scores = []
    for tokens in docs_tokens:
        tf = Counter(tokens)
        dl = len(tokens) or 1
        total = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            total += idf * (freq * (BM25_K1 + 1)) / (freq + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        scores.append(total)
    return scores


def _tag_overlap(query_tags: set[str], design_tags: Iterable[str]) -> float:
    """Jaccard-ish, but asymmetric: we care how much of the *query* is covered.

    A rich design with 20 tags shouldn't be penalised for having more tags than
    a three-word prompt asked about.
    """
    design = set(design_tags)
    if not query_tags:
        return 0.0
    return len(query_tags & design) / len(query_tags)


def _query_scope(query: str) -> str:
    """Is the user asking for a whole page, one block, or not saying?"""
    tokens = set(taxonomy.tokenize(query))
    detected = taxonomy.detect_tags(query).get("page_type", [])
    if tokens & _PART_WORDS or "component" in detected:
        return "part"
    if tokens & {"site", "website", "page", "landing", "homepage"} or set(detected) & PAGE_TYPES:
        return "page"
    return "any"


def _scope_factor(query_scope: str, design: dict[str, Any]) -> float:
    if query_scope == "any":
        return 1.0
    types = set(design.get("primary", {}).get("page_type")
                or design.get("tags", {}).get("page_type", []))
    if not types:
        return 1.0
    is_part = bool(types & COMPONENT_TYPES) and not (types & PAGE_TYPES)
    if query_scope == "page" and is_part:
        return SCOPE_PENALTY
    if query_scope == "part" and not is_part:
        return SCOPE_PENALTY
    return 1.0


def parse_filters(pairs: Iterable[str] | None) -> dict[str, list[str]]:
    """['industry=fintech', 'motion=3d-webgl,scroll-driven'] -> dict of facet -> tags."""
    filters: dict[str, list[str]] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValueError(f"filter must look like facet=tag, got {item!r}")
        facet, values = item.split("=", 1)
        filters.setdefault(facet.strip(), []).extend(
            v.strip() for v in values.split(",") if v.strip()
        )
    return filters


def _passes(design: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    """A design must satisfy every facet named, matching any tag within it."""
    for facet, wanted in filters.items():
        have = set(design.get("tags", {}).get(facet, []))
        if not have & set(wanted):
            return False
    return True


def search(
    query: str,
    index: dict[str, Any],
    k: int = 5,
    filters: dict[str, list[str]] | None = None,
    backend: embed.Backend | None = None,
    require_media: bool = False,
) -> list[dict[str, Any]]:
    """Rank designs for a query.

    `require_media` is a hard filter, not a boost: a workflow that treats the
    match as a *template* to reproduce cannot do anything with a design that has
    no screenshots, and at k=1 a boost still lets a text-only brief win on words.
    """
    designs = [d for d in index["designs"] if _passes(d, filters or {})]
    if require_media:
        designs = [d for d in designs if d.get("media")]
    if not designs:
        return []

    backend = backend or embed.backend_from_state(index["backend"], index.get("backend_state", {}))
    qvec = backend.encode_query(query)

    dense = [embed.cosine(qvec, d.get("vector", [])) for d in designs]
    docs_tokens = [taxonomy.tokenize(d.get("embed_text") or d.get("description", "")) for d in designs]
    lexical = _bm25(taxonomy.tokenize(query), docs_tokens)

    query_tags = set(taxonomy.flatten_tags(taxonomy.detect_tags(query)))
    tags = [_tag_overlap(query_tags, d.get("tag_list", [])) for d in designs]

    nd, nl, nt = _normalise(dense), _normalise(lexical), _normalise(tags)

    scope = _query_scope(query)

    hits = []
    for i, design in enumerate(designs):
        score = WEIGHTS["dense"] * nd[i] + WEIGHTS["lexical"] * nl[i] + WEIGHTS["tags"] * nt[i]
        factor = _scope_factor(scope, design)
        score *= factor
        hit = {key: value for key, value in design.items() if key != "vector"}
        hit["score"] = round(score, 4)
        if factor != 1.0:
            hit["scope_penalty"] = round(factor, 2)
        hit["signals"] = {
            "dense": round(dense[i], 4),
            "lexical": round(lexical[i], 4),
            "tag_overlap": round(tags[i], 4),
        }
        hit["matched_tags"] = sorted(query_tags & set(design.get("tag_list", [])))
        hits.append(hit)

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:k]


def why(hit: dict[str, Any]) -> str:
    """One-line rationale. Agents paste this to the user so a pick isn't a black box."""
    bits = []
    if hit.get("matched_tags"):
        bits.append("tags " + ", ".join(t.split(":", 1)[1] for t in hit["matched_tags"][:5]))
    signals = hit.get("signals", {})
    bits.append(f"semantic {signals.get('dense', 0):.2f}")
    if signals.get("lexical", 0) > 0:
        bits.append(f"keyword {signals['lexical']:.1f}")
    return f"{hit['title']} (score {hit['score']:.3f}) - " + "; ".join(bits)
