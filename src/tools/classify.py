"""Classify tool — batched LLM classification of reviews against the taxonomy.

Every review is classified; low-confidence rows (confidence < 0.5) are kept
and flagged rather than dropped so the full corpus remains visible downstream.
"""

from __future__ import annotations

import logging

from agent.state import (
    ClassificationBatch,
    ClassifiedReview,
)
from sources.models import Review

log = logging.getLogger(__name__)

_BATCH_SIZE = 20
_LOW_CONF_THRESHOLD = 0.5

_SYSTEM_PROMPT = """\
You classify app-store reviews for competitive analysis.
For each review return the PRIMARY theme, overall sentiment, a short friction phrase
(≤8 words capturing the core issue or praise), and your confidence (0–1).
Return ONLY the JSON — no explanation.\
"""


def classify_reviews(
    reviews: list[Review],
    taxonomy_themes: list[str],
    llm: object,  # LLMClient | StubLLMClient
    *,
    batch_size: int = _BATCH_SIZE,
) -> tuple[list[ClassifiedReview], int]:
    """Classify all reviews in batches.

    Returns:
        classified:           One ClassifiedReview per input Review.
        low_confidence_count: How many had confidence < threshold (all kept).
    """
    results: list[ClassifiedReview] = []
    low_conf_count = 0

    for i in range(0, len(reviews), batch_size):
        batch = reviews[i : i + batch_size]
        try:
            batch_result = _classify_batch(batch, taxonomy_themes, llm)
        except Exception as exc:
            log.warning("classify batch %d failed: %s — skipping batch", i // batch_size, exc)
            continue

        # Index by review_id so we can match back even if order differs
        result_map = {c.review_id: c for c in batch_result.classifications}
        for review in batch:
            raw = result_map.get(review.id)
            if raw is None:
                log.warning("LLM did not classify review %s — using fallback", review.id)
                raw_data = {
                    "review_id": review.id,
                    "theme": "unknown",
                    "sentiment": "neutral",
                    "friction_phrase": "",
                    "confidence": 0.0,
                }
                from agent.state import ReviewClassification

                raw = ReviewClassification.model_validate(raw_data)

            flagged = raw.confidence < _LOW_CONF_THRESHOLD
            if flagged:
                low_conf_count += 1
                log.debug(
                    "Low-confidence classification for review %s (%.2f)", review.id, raw.confidence
                )

            results.append(
                ClassifiedReview(
                    review_id=review.id,
                    app=review.app,
                    date=review.date,
                    theme=raw.theme,
                    sentiment=raw.sentiment,
                    friction_phrase=raw.friction_phrase,
                    confidence=raw.confidence,
                    low_confidence=flagged,
                )
            )

    return results, low_conf_count


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _classify_batch(
    reviews: list[Review],
    taxonomy_themes: list[str],
    llm: object,
) -> ClassificationBatch:
    theme_list = ", ".join(taxonomy_themes)
    lines = [f"Available themes: {theme_list}\n"]
    for r in reviews:
        lines.append(
            f"Review ID: {r.id}\n"
            f"App: {r.app}\n"
            f"Rating: {r.rating}/5\n"
            f"Title: {r.title}\n"
            f"Body: {r.body}\n"
        )

    prompt = "\n".join(lines)
    return llm.structured_output(  # type: ignore[union-attr]
        ClassificationBatch,
        [{"role": "user", "content": prompt}],
        system=_SYSTEM_PROMPT,
        max_tokens=2048,
    )
