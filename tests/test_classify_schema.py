"""Unit tests for classify tool: schema validation and low-confidence handling.

Guarantees tested:
  - ReviewClassification schema rejects malformed LLM output (bad enum, out-of-range
    confidence, missing required field) with a Pydantic ValidationError.
  - Low-confidence rows (confidence < 0.5) are flagged and counted but NEVER dropped;
    every input review produces exactly one ClassifiedReview.
  - Reviews missing from the LLM batch response receive a fallback classification
    (theme="unknown", confidence=0.0, low_confidence=True) and are still returned.
  - A batch-level exception (e.g. broken LLM JSON) is caught gracefully; the failed
    batch is skipped without raising, so other batches still complete.

All tests are pure Python — no network, no API key.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.state import ClassificationBatch, ReviewClassification
from sources.models import Review
from tools.classify import _LOW_CONF_THRESHOLD, classify_reviews

_DATE = datetime(2025, 6, 1)
_THEMES = ["support", "activation", "refund_billing", "coverage_speed", "app_ux", "value_pricing"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review(rid: str, app: str = "USim") -> Review:
    return Review(
        id=rid,
        source="appstore",
        app=app,
        country="us",
        rating=3,
        title=f"review {rid}",
        body="some review text",
        date=_DATE,
    )


def _rc(
    review_id: str,
    *,
    theme: str = "support",
    sentiment: str = "negative",
    confidence: float = 0.9,
) -> ReviewClassification:
    return ReviewClassification(
        review_id=review_id,
        theme=theme,
        sentiment=sentiment,
        friction_phrase="",
        confidence=confidence,
    )


class _MockLLM:
    """Minimal LLM mock for classify_reviews — no network, no API."""

    def __init__(
        self,
        *,
        batch: ClassificationBatch | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._batch = batch
        self._raises = raises

    def structured_output(self, schema, messages, *, system=None, max_tokens=None):
        if self._raises is not None:
            raise self._raises
        return self._batch


# ---------------------------------------------------------------------------
# Schema validation — ReviewClassification rejects malformed LLM output
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """ReviewClassification Pydantic model rejects bad LLM-produced JSON."""

    def test_invalid_sentiment_enum_raises(self):
        with pytest.raises(ValidationError):
            ReviewClassification.model_validate(
                {
                    "review_id": "x",
                    "theme": "support",
                    "sentiment": "ANGRY",  # not in Literal
                    "friction_phrase": "",
                    "confidence": 0.9,
                }
            )

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            ReviewClassification.model_validate(
                {
                    "review_id": "x",
                    "theme": "support",
                    "sentiment": "negative",
                    "friction_phrase": "",
                    "confidence": 1.5,  # > 1.0 violates Field(le=1.0)
                }
            )

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            ReviewClassification.model_validate(
                {
                    "review_id": "x",
                    "theme": "support",
                    "sentiment": "negative",
                    "friction_phrase": "",
                    "confidence": -0.1,  # < 0.0 violates Field(ge=0.0)
                }
            )

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            ReviewClassification.model_validate(
                {
                    "review_id": "x",
                    # theme is required — omitting it must raise
                    "sentiment": "negative",
                    "friction_phrase": "",
                    "confidence": 0.9,
                }
            )

    def test_missing_review_id_raises(self):
        with pytest.raises(ValidationError):
            ReviewClassification.model_validate(
                {
                    # review_id is required
                    "theme": "support",
                    "sentiment": "negative",
                    "friction_phrase": "",
                    "confidence": 0.9,
                }
            )

    def test_valid_row_accepted(self):
        """Baseline: a well-formed row passes without error."""
        rc = ReviewClassification.model_validate(
            {
                "review_id": "ok",
                "theme": "support",
                "sentiment": "negative",
                "friction_phrase": "slow response",
                "confidence": 0.85,
            }
        )
        assert rc.review_id == "ok"
        assert rc.confidence == pytest.approx(0.85)

    def test_all_valid_sentiments_accepted(self):
        for s in ("positive", "negative", "neutral", "mixed"):
            rc = ReviewClassification.model_validate(
                {
                    "review_id": "x",
                    "theme": "support",
                    "sentiment": s,
                    "friction_phrase": "",
                    "confidence": 0.5,
                }
            )
            assert rc.sentiment == s

    def test_confidence_boundary_zero_accepted(self):
        rc = ReviewClassification(
            review_id="x",
            theme="support",
            sentiment="neutral",
            friction_phrase="",
            confidence=0.0,
        )
        assert rc.confidence == 0.0

    def test_confidence_boundary_one_accepted(self):
        rc = ReviewClassification(
            review_id="x",
            theme="support",
            sentiment="neutral",
            friction_phrase="",
            confidence=1.0,
        )
        assert rc.confidence == 1.0


# ---------------------------------------------------------------------------
# Low-confidence: flagged + counted, never dropped
# ---------------------------------------------------------------------------


class TestLowConfidenceFlagging:
    """Low-confidence rows appear in output with low_confidence=True."""

    def test_low_confidence_row_is_kept(self):
        """A confidence=0.2 row must appear in results (not dropped)."""
        reviews = [_review("r1")]
        batch = ClassificationBatch(classifications=[_rc("r1", confidence=0.2)])
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert len(classified) == 1
        assert classified[0].review_id == "r1"
        assert classified[0].low_confidence is True

    def test_low_confidence_rows_counted(self):
        """low_confidence_count reflects every row below the threshold."""
        reviews = [_review("r1"), _review("r2"), _review("r3")]
        batch = ClassificationBatch(
            classifications=[
                _rc("r1", confidence=0.1),  # below threshold
                _rc("r2", confidence=0.49),  # below threshold (0.49 < 0.5)
                _rc("r3", confidence=0.5),  # exactly at threshold — not flagged
            ]
        )
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert len(classified) == 3
        assert low_count == 2
        flagged = [c for c in classified if c.low_confidence]
        assert len(flagged) == 2

    def test_threshold_boundary_exactly_at_threshold_not_flagged(self):
        """confidence=0.5 is NOT below the threshold (threshold is strictly < 0.5)."""
        reviews = [_review("r1")]
        batch = ClassificationBatch(classifications=[_rc("r1", confidence=_LOW_CONF_THRESHOLD)])
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert low_count == 0
        assert classified[0].low_confidence is False

    def test_high_confidence_rows_not_flagged(self):
        """Rows with high confidence are classified normally, not flagged."""
        reviews = [_review("r1"), _review("r2")]
        batch = ClassificationBatch(
            classifications=[
                _rc("r1", confidence=0.95),
                _rc("r2", confidence=0.8),
            ]
        )
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert low_count == 0
        assert all(not c.low_confidence for c in classified)

    def test_all_reviews_returned_regardless_of_confidence(self):
        """Output always has one ClassifiedReview per input Review."""
        reviews = [_review(f"r{i}") for i in range(5)]
        batch = ClassificationBatch(
            classifications=[_rc(f"r{i}", confidence=0.1 * i) for i in range(5)]
        )
        classified, _ = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert len(classified) == len(reviews)
        assert {c.review_id for c in classified} == {r.id for r in reviews}


# ---------------------------------------------------------------------------
# Missing review fallback
# ---------------------------------------------------------------------------


class TestMissingReviewFallback:
    """Reviews absent from the LLM batch response get a safe fallback classification."""

    def test_missing_review_gets_fallback(self):
        """LLM omits r2 — r2 must still appear with theme='unknown', confidence=0.0."""
        reviews = [_review("r1"), _review("r2")]
        batch = ClassificationBatch(
            classifications=[
                _rc("r1", confidence=0.9),
                # r2 deliberately absent
            ]
        )
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert len(classified) == 2, "both reviews must appear in output"
        r2 = next(c for c in classified if c.review_id == "r2")
        assert r2.theme == "unknown"
        assert r2.confidence == 0.0
        assert r2.low_confidence is True

    def test_missing_review_increments_low_conf_count(self):
        """Fallback confidence=0.0 < threshold → counted as low-confidence."""
        reviews = [_review("r1"), _review("r2")]
        batch = ClassificationBatch(classifications=[_rc("r1", confidence=0.9)])
        _, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert low_count == 1  # r2 fallback is confidence=0.0

    def test_all_missing_reviews_get_fallback(self):
        """LLM returns empty batch — all reviews get fallback."""
        reviews = [_review(f"r{i}") for i in range(3)]
        batch = ClassificationBatch(classifications=[])
        classified, low_count = classify_reviews(reviews, _THEMES, _MockLLM(batch=batch))
        assert len(classified) == 3
        assert low_count == 3
        assert all(c.theme == "unknown" for c in classified)


# ---------------------------------------------------------------------------
# Batch exception handling
# ---------------------------------------------------------------------------


class TestBatchExceptionHandling:
    """classify_reviews() handles batch failures gracefully — no crash, batch skipped."""

    def test_exception_does_not_propagate(self):
        """A failing batch (e.g. broken LLM JSON) must not raise from classify_reviews."""
        reviews = [_review("r1"), _review("r2")]
        llm = _MockLLM(raises=ValueError("malformed LLM response"))
        classified, low_count = classify_reviews(reviews, _THEMES, llm)
        # The batch is skipped — reviews not in output, but no exception raised
        assert isinstance(classified, list)
        assert low_count == 0

    def test_valid_second_batch_processed_after_first_fails(self):
        """When the first batch fails, subsequent batches still process."""
        call_count = 0

        class _PartialLLM:
            def structured_output(self, schema, messages, *, system=None, max_tokens=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ValueError("first batch broken")
                return ClassificationBatch(classifications=[_rc("r21", confidence=0.9)])

        reviews = [
            _review("r21"),
            _review("r22"),
        ]  # 2 reviews; batch_size=20 → two calls would need 21+
        # Force batch_size=1 so each review is its own batch
        classified, _ = classify_reviews(reviews, _THEMES, _PartialLLM(), batch_size=1)
        # First batch (r21) raises → skipped; second batch (r22) also tries and raises again
        # With the above mock, call 1 raises, call 2 returns r21 (not r22) — testing that the
        # exception path doesn't abort subsequent batches
        assert isinstance(classified, list)
        assert call_count == 2
