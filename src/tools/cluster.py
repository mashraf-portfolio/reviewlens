"""Cluster tool — normalise raw LLM theme labels onto the seed taxonomy.

Uses Sonnet at low temperature to map free-form theme labels produced by the
classifier back to the 7 canonical seed themes, while allowing genuinely
emergent themes (those with no good seed match) to pass through unchanged.
"""

from __future__ import annotations

import logging

from agent.state import ClassifiedReview, ThemeMapping

log = logging.getLogger(__name__)

_SEED_THEMES = [
    "activation",
    "support",
    "refund_billing",
    "coverage_speed",
    "app_ux",
    "value_pricing",
    "positive",
]

_SYSTEM_PROMPT = """\
You map free-form app-review theme labels onto a canonical taxonomy.
For each input label, return the closest canonical theme.
If a label clearly does not match any canonical theme, return it as-is
(emergent theme).  Return ONLY the JSON mapping — no prose.\
"""


def cluster_themes(
    classified: list[ClassifiedReview],
    seed_themes: list[str],
    llm: object,  # LLMClient | StubLLMClient
) -> dict[str, str]:
    """Return a mapping {raw_label: canonical_label} for all unique themes.

    If the mapping for a label is empty or missing, the original label is kept.
    """
    raw_themes = sorted({c.theme for c in classified})
    if not raw_themes:
        return {}

    theme_str = ", ".join(f'"{t}"' for t in raw_themes)
    seed_str = ", ".join(f'"{t}"' for t in seed_themes)
    prompt = (
        f"Canonical themes: [{seed_str}]\n\n"
        f"Map each of these raw labels: [{theme_str}]\n\n"
        'Return a JSON object: {"mappings": {"raw_label": "canonical_or_same", ...}}'
    )

    try:
        result: ThemeMapping = llm.structured_output(  # type: ignore[union-attr]
            ThemeMapping,
            [{"role": "user", "content": prompt}],
            system=_SYSTEM_PROMPT,
            max_tokens=512,
        )
        mapping = result.mappings
    except Exception as exc:
        log.warning("cluster_themes LLM call failed: %s — using identity mapping", exc)
        mapping = {}

    # Fill any gaps with identity (keep original label)
    for t in raw_themes:
        if t not in mapping or not mapping[t]:
            mapping[t] = t

    log.info("cluster_themes: mapped %d raw labels", len(mapping))
    return mapping


def apply_theme_map(
    classified: list[ClassifiedReview],
    theme_map: dict[str, str],
) -> list[ClassifiedReview]:
    """Return a new list with each review's theme replaced by its canonical form."""
    return [r.model_copy(update={"theme": theme_map.get(r.theme, r.theme)}) for r in classified]
