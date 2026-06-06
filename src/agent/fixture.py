"""Offline fixture corpus — 40 reviews across USim, Airalo, and Holafly.

Dates are recent enough to fall inside a 12-month recency window.
Themes are spread across the seed taxonomy to exercise the full pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sources.models import AppTarget, FetchPlan, Review

# ---------------------------------------------------------------------------
# 40 reviews: 20 USim, 12 Airalo, 8 Holafly
# ---------------------------------------------------------------------------

_REVIEWS_RAW: list[dict] = [
    # -------- USim (20) --------
    {
        "id": "u01",
        "app": "USim",
        "rating": 1,
        "title": "App crashes at login",
        "body": "Keeps crashing when I try to activate my eSIM. Unusable.",
        "date": "2025-11-01",
    },
    {
        "id": "u02",
        "app": "USim",
        "rating": 2,
        "title": "Refund nightmare",
        "body": "Charged twice and support never responded to my refund request.",
        "date": "2025-11-03",
    },
    {
        "id": "u03",
        "app": "USim",
        "rating": 5,
        "title": "Worked perfectly",
        "body": "Activated in minutes in Japan. Excellent speeds.",
        "date": "2025-11-05",
    },
    {
        "id": "u04",
        "app": "USim",
        "rating": 1,
        "title": "No signal in Germany",
        "body": "Paid for coverage that simply did not work in Berlin.",
        "date": "2025-11-07",
    },
    {
        "id": "u05",
        "app": "USim",
        "rating": 2,
        "title": "Support ghosted me",
        "body": "Three emails, zero replies. Very disappointing customer service.",
        "date": "2025-11-09",
    },
    {
        "id": "u06",
        "app": "USim",
        "rating": 3,
        "title": "UI confusing",
        "body": "Could not find where to install the profile. Took 40 mins.",
        "date": "2025-11-11",
    },
    {
        "id": "u07",
        "app": "USim",
        "rating": 1,
        "title": "Wrong charge",
        "body": "Billed for 10 GB but only got 1 GB. Requesting chargeback.",
        "date": "2025-11-13",
    },
    {
        "id": "u08",
        "app": "USim",
        "rating": 5,
        "title": "Best travel SIM",
        "body": "Used in 5 countries without a hitch. Highly recommend.",
        "date": "2025-11-15",
    },
    {
        "id": "u09",
        "app": "USim",
        "rating": 2,
        "title": "App hangs on Android",
        "body": "Loading spinner never stops. Had to sideload an older APK.",
        "date": "2025-11-17",
    },
    {
        "id": "u10",
        "app": "USim",
        "rating": 1,
        "title": "Activation failed",
        "body": "QR code scan keeps failing. Spent an hour with no resolution.",
        "date": "2025-11-19",
    },
    {
        "id": "u11",
        "app": "USim",
        "rating": 4,
        "title": "Good value",
        "body": "Cheaper than roaming. Minor UI quirks but solid overall.",
        "date": "2025-11-21",
    },
    {
        "id": "u12",
        "app": "USim",
        "rating": 1,
        "title": "Refund ignored",
        "body": "Submitted refund 3 weeks ago. Still pending. Unacceptable.",
        "date": "2025-11-23",
    },
    {
        "id": "u13",
        "app": "USim",
        "rating": 2,
        "title": "Terrible coverage",
        "body": "Edge speeds in Paris. Useless for video calls.",
        "date": "2025-11-25",
    },
    {
        "id": "u14",
        "app": "USim",
        "rating": 5,
        "title": "Saved my trip",
        "body": "Last-minute eSIM. Activated in 2 minutes. Life saver.",
        "date": "2025-11-27",
    },
    {
        "id": "u15",
        "app": "USim",
        "rating": 3,
        "title": "Slow support",
        "body": "Support eventually helped but took 4 days to respond.",
        "date": "2025-11-29",
    },
    {
        "id": "u16",
        "app": "USim",
        "rating": 1,
        "title": "Sign-up broken",
        "body": "Email verification loop. Never got past account creation.",
        "date": "2025-12-01",
    },
    {
        "id": "u17",
        "app": "USim",
        "rating": 2,
        "title": "App UI outdated",
        "body": "Looks like it was designed in 2015. Hard to navigate.",
        "date": "2025-12-03",
    },
    {
        "id": "u18",
        "app": "USim",
        "rating": 4,
        "title": "Works in SE Asia",
        "body": "Thailand, Vietnam, Cambodia — all fine. Happy customer.",
        "date": "2025-12-05",
    },
    {
        "id": "u19",
        "app": "USim",
        "rating": 1,
        "title": "Double-charged",
        "body": "Two transactions for one eSIM. Disputed with my bank.",
        "date": "2025-12-07",
    },
    {
        "id": "u20",
        "app": "USim",
        "rating": 3,
        "title": "Decent but not great",
        "body": "Coverage ok, app mediocre. Would try a competitor next time.",
        "date": "2025-12-09",
    },
    # -------- Airalo (12) --------
    {
        "id": "a01",
        "app": "Airalo",
        "rating": 5,
        "title": "Seamless activation",
        "body": "Set up in under a minute. Great speeds across Europe.",
        "date": "2025-11-02",
    },
    {
        "id": "a02",
        "app": "Airalo",
        "rating": 4,
        "title": "Very convenient",
        "body": "No physical SIM needed. Worked great in Japan.",
        "date": "2025-11-04",
    },
    {
        "id": "a03",
        "app": "Airalo",
        "rating": 2,
        "title": "Poor US coverage",
        "body": "Only 3G in rural areas. Not worth the premium price.",
        "date": "2025-11-06",
    },
    {
        "id": "a04",
        "app": "Airalo",
        "rating": 5,
        "title": "Excellent service",
        "body": "Support chat resolved my issue in minutes. Impressed.",
        "date": "2025-11-08",
    },
    {
        "id": "a05",
        "app": "Airalo",
        "rating": 3,
        "title": "App glitchy",
        "body": "eSIM profile disappeared after iOS update. Had to reinstall.",
        "date": "2025-11-10",
    },
    {
        "id": "a06",
        "app": "Airalo",
        "rating": 5,
        "title": "Go-to travel eSIM",
        "body": "Used for 3 years. Never had a problem. Top tier.",
        "date": "2025-11-12",
    },
    {
        "id": "a07",
        "app": "Airalo",
        "rating": 1,
        "title": "Refund refused",
        "body": "Did not work in South Korea. Refused a refund. Awful.",
        "date": "2025-11-14",
    },
    {
        "id": "a08",
        "app": "Airalo",
        "rating": 4,
        "title": "Good speeds",
        "body": "50 Mbps average in Spain. Worth every penny.",
        "date": "2025-11-16",
    },
    {
        "id": "a09",
        "app": "Airalo",
        "rating": 5,
        "title": "Easy to use",
        "body": "Clean app design, instant activation. Recommended.",
        "date": "2025-11-18",
    },
    {
        "id": "a10",
        "app": "Airalo",
        "rating": 2,
        "title": "Pricing confusing",
        "body": "Hidden fees make it more expensive than advertised.",
        "date": "2025-11-20",
    },
    {
        "id": "a11",
        "app": "Airalo",
        "rating": 4,
        "title": "Worked in Africa",
        "body": "Good coverage in Kenya and Tanzania. Pleasantly surprised.",
        "date": "2025-11-22",
    },
    {
        "id": "a12",
        "app": "Airalo",
        "rating": 3,
        "title": "Hit or miss",
        "body": "Works well in cities but rural coverage is weak.",
        "date": "2025-11-24",
    },
    # -------- Holafly (8) --------
    {
        "id": "h01",
        "app": "Holafly",
        "rating": 5,
        "title": "Unlimited data hero",
        "body": "Truly unlimited. Streamed Netflix in Italy. Perfect.",
        "date": "2025-11-03",
    },
    {
        "id": "h02",
        "app": "Holafly",
        "rating": 1,
        "title": "Charged but no eSIM",
        "body": "Payment went through. QR code never arrived. No refund given.",
        "date": "2025-11-05",
    },
    {
        "id": "h03",
        "app": "Holafly",
        "rating": 4,
        "title": "Good for Europe",
        "body": "Worked well in France, Italy, and Germany.",
        "date": "2025-11-07",
    },
    {
        "id": "h04",
        "app": "Holafly",
        "rating": 5,
        "title": "Excellent coverage",
        "body": "Fast 4G everywhere I went in Portugal.",
        "date": "2025-11-09",
    },
    {
        "id": "h05",
        "app": "Holafly",
        "rating": 2,
        "title": "Slow speeds",
        "body": "Throttled after a few GB. 'Unlimited' is misleading.",
        "date": "2025-11-11",
    },
    {
        "id": "h06",
        "app": "Holafly",
        "rating": 1,
        "title": "Refund denied",
        "body": "eSIM never connected. Asked for refund. Told no.",
        "date": "2025-11-13",
    },
    {
        "id": "h07",
        "app": "Holafly",
        "rating": 5,
        "title": "Highly recommended",
        "body": "Third trip using Holafly. Never a problem. 5 stars.",
        "date": "2025-11-15",
    },
    {
        "id": "h08",
        "app": "Holafly",
        "rating": 3,
        "title": "Activation email late",
        "body": "Waited 30 minutes for the QR code. Made me nervous at the airport.",
        "date": "2025-11-17",
    },
]


def make_fixture_reviews() -> list[Review]:
    """Return the 40-review fixture corpus as Review objects."""
    reviews = []
    for r in _REVIEWS_RAW:
        date = datetime.fromisoformat(r["date"]).replace(tzinfo=UTC)
        reviews.append(
            Review(
                id=r["id"],
                source="appstore",
                app=r["app"],
                country="us",
                rating=r["rating"],
                title=r["title"],
                body=r["body"],
                date=date,
            )
        )
    return reviews


def make_fixture_plan() -> FetchPlan:
    """Return a FetchPlan referencing the three fixture apps."""
    return FetchPlan(
        targets=[
            AppTarget(name="USim", app_store_id="6502586159", countries=["us"]),
            AppTarget(name="Airalo", app_store_id="1475911720", countries=["us"]),
            AppTarget(name="Holafly", app_store_id="1498987433", countries=["us"]),
        ],
        max_pages=1,
        enabled_sources=["appstore"],
    )
