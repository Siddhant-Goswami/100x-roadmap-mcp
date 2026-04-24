"""
Local curriculum index.

Walks pilot-data/curriculum/ once at import time, tokenizes each page,
builds a BM25 index. search(query, k) returns the top-k pages with
content so callers can stuff them into prompts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from storage import PILOT_REPO

CURRICULUM_DIR = PILOT_REPO / "curriculum"

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


@dataclass
class Page:
    slug: str            # e.g. "concepts/retrieval-augmented-generation"
    title: str
    content: str
    tokens: list[str]


def _load_pages() -> list[Page]:
    pages: list[Page] = []
    if not CURRICULUM_DIR.exists():
        return pages
    for md in CURRICULUM_DIR.rglob("*.md"):
        rel = md.relative_to(CURRICULUM_DIR).with_suffix("")
        content = md.read_text(encoding="utf-8", errors="replace")
        title = _extract_title(content) or rel.name.replace("-", " ").title()
        pages.append(Page(
            slug=str(rel).replace("\\", "/"),
            title=title,
            content=content,
            tokens=_tokenize(content + " " + title),
        ))
    return pages


def _extract_title(content: str) -> str | None:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


# Lightweight BM25 (avoids extra dependency). Good enough for ~90 pages.
class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.avgdl = sum(len(d) for d in docs) / max(1, self.N)
        self.doc_lens = [len(d) for d in docs]
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for d in docs:
            counts: dict[str, int] = {}
            for t in d:
                counts[t] = counts.get(t, 0) + 1
            self.tf.append(counts)
            for t in counts:
                df[t] = df.get(t, 0) + 1
        import math
        self.idf = {
            t: math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            for t, n in df.items()
        }

    def score(self, query_tokens: list[str], i: int) -> float:
        score = 0.0
        dl = self.doc_lens[i]
        tf = self.tf[i]
        for q in query_tokens:
            if q not in self.idf:
                continue
            f = tf.get(q, 0)
            if f == 0:
                continue
            num = f * (self.k1 + 1)
            den = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self.idf[q] * num / den
        return score


_pages: list[Page] = _load_pages()
_bm25 = _BM25([p.tokens for p in _pages]) if _pages else None


def search(query: str, k: int = 3) -> list[Page]:
    if not _pages or _bm25 is None:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    scores = [(_bm25.score(q_tokens, i), i) for i in range(len(_pages))]
    scores.sort(key=lambda x: x[0], reverse=True)
    return [_pages[i] for s, i in scores[:k] if s > 0]


def get_page(slug: str) -> Page | None:
    for p in _pages:
        if p.slug == slug:
            return p
    return None


def page_count() -> int:
    return len(_pages)
