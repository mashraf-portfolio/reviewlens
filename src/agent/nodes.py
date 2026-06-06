"""LangGraph node functions — exactly 8 nodes per §2.1 of the design doc.

Node order:
    plan → fetch → triage → classify → cluster → quantify → diagnose → critique

Conditional edges:
    triage  → classify  (enough usable reviews)
            → fetch     (retry: insufficient data after filtering)
    critique → END      (report meets quality bar)
             → fetch    (retry: hallucination or low-confidence synthesis detected)

Both retry paths are bounded by max_fetch_loops and CostMeter.ceiling_usd.
"""


def plan_node(state):
    """Build a run plan: resolve storefronts, date windows, and taxonomy to use.

    TODO:
    - Call LLMClient with config.models.planner to produce a RunPlan
    - Validate plan against config constraints (storefronts, recency_window_months)
    - Store plan in state.run_plan
    """
    raise NotImplementedError


def fetch_node(state):
    """Fetch raw reviews from all enabled sources for the current plan.

    TODO:
    - Call sources.registry.get_sources(config) for each enabled source
    - Merge new results into state.raw_reviews, deduplicating by review ID
    - Increment state.fetch_loop_count; raise if > config.max_fetch_loops
    - Check CostMeter has budget remaining before proceeding
    """
    raise NotImplementedError


def triage_node(state):
    """Filter and quality-gate the fetched reviews; decide whether to proceed.

    TODO:
    - Apply recency_window_months cutoff
    - Remove duplicates and spam/bot reviews
    - Return routing signal: "classify" if len >= min_n_floor, else "fetch"
    - Store filtered reviews in state.triaged_reviews
    """
    raise NotImplementedError


def classify_node(state):
    """Classify each triaged review against the taxonomy themes.

    TODO:
    - Use LLMClient with config.models.classifier
    - Batch reviews to stay under token limits
    - Use structured_output() to produce ClassifiedReview(review_id, themes, sentiment)
    - Store results in state.classified
    """
    raise NotImplementedError


def cluster_node(state):
    """Group classified reviews into named theme clusters.

    TODO:
    - Group ClassifiedReviews by primary theme
    - Sub-cluster by semantic similarity within each theme
    - Assign a short human-readable label to each cluster
    - Produce list[Cluster(theme, label, review_ids, representative_quotes)]
    - Store results in state.clusters
    """
    raise NotImplementedError


def quantify_node(state):
    """Compute statistical significance of cluster volume changes over time.

    TODO:
    - Use statsmodels proportion z-test or chi-squared on theme counts
    - Compare current recency_window vs prior equal-length window
    - Produce QuantStats(theme, count, pct, delta_pct, p_value, significant)
    - Store results in state.stats
    """
    raise NotImplementedError


def diagnose_node(state):
    """Run pipeline diagnostics and surface coverage/quality warnings.

    TODO:
    - Call diagnosis.coverage_check for storefronts below min_n_floor
    - Call diagnosis.theme_distribution to detect collapsed/skewed taxonomy
    - Attach DiagnosticsReport to state.diagnostics
    - Log warnings but do not abort — critique_node decides retry
    """
    raise NotImplementedError


def critique_node(state):
    """Self-critique the synthesised report; decide whether to accept or retry.

    TODO:
    - Use LLMClient with config.models.synth to score the draft report
    - Check for hallucinations, unsupported claims, and low-confidence themes
    - Return routing signal: "end" if quality bar met, else "fetch" to retry
    - On "fetch" retry, attach critique notes to state for plan_node context
    - Increment and check fetch_loop_count + CostMeter before allowing retry
    """
    raise NotImplementedError
