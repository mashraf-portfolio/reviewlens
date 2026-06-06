# ReviewLens · Competitive Diagnosis

**No cross-company difference clears the significance bar in this sample. The loudest pain by raw rate is support (10.0 per-100, n=2), reported for orientation only.**

An LLM agent read 40 public reviews across USim and 2 competitors over the last 12 months, classified each into a pain taxonomy, and benchmarked rates per-100-reviews with 95% confidence intervals.

## Top-3 Pains

| Pain | USim per-100 (95% CI) | Field median per-100 | Delta | Evidence |
|------|----------------------|---------------------|-------|----------|
| Support (Negative) | 10.0 (2.8–30.1) | 13.3 | -6.7 vs Airalo | [Directional] |
| Activation (Negative) | 10.0 (2.8–30.1) | 10.0 | -2.5 vs Holafly | [Directional] |
| Refund Billing (Negative) | 10.0 (2.8–30.1) | 10.0 | -2.5 vs Holafly | [Directional] |

## Competitive Read

On value pricing (negative), USim trends lower than Holafly (n=1; small sample — treat as indicative only) [Directional].  
On coverage speed (negative), USim trends lower than Holafly (n=1; small sample — treat as indicative only) [Directional].  
On support (negative), USim trends lower than Airalo (n=2; small sample — treat as indicative only) [Directional].

## Month-One Interventions

- Set a 4-hour first-response SLA; auto-triage tickets by theme (activation, refund) and route to a specialist queue — remove the silence that turns a resolvable issue into a one-star review.
- Deploy an activation watchdog: alert ops when a QR-code scan fails twice, trigger an automated re-delivery, and send a 30-minute check-in message — eliminate silent activation failures before they become refund requests.
- Automate refund-status notifications: confirm receipt within 1 hour and send a resolution update within 48 hours — silence is what escalates a delayed refund into a chargeback dispute.

---

*Sample: 40 reviews (appstore: 40); recency window 12 months; competitors benchmarked: Airalo, Holafly. All rates per-100 reviews with 95% Wilson CIs. Supported = both samples ≥ n-floor AND CIs non-overlapping; Directional = otherwise (thin sample or overlapping intervals).*
