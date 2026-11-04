"""Reciprocal Rank Fusion."""
from __future__ import annotations

from collections.abc import Hashable, Sequence


def rrf(rankings: Sequence[Sequence[Hashable]], k: int = 60, top_n: int | None = None) -> list[tuple[Hashable, float]]:
    """rankings: các danh sách id đã sắp theo thứ hạng (tốt nhất trước). score(d) = Σ 1/(k + rank_d), rank từ 1."""
    scores: dict[Hashable, float] = {}
    first_seen: dict[Hashable, int] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(doc, len(first_seen))
    # hoà điểm -> giữ thứ tự xuất hiện đầu tiên để kết quả ổn định
    out = sorted(scores.items(), key=lambda x: (-x[1], first_seen[x[0]]))
    return out[:top_n] if top_n else out
