"""Deterministic fixture data for VIKI retrieval eval.

FACT_FIXTURES  — MemoryRecord seeds covering job outreach, founder signals,
                 follow-ups, and noise.  source_type_hint drives noise exclusion.
FOUNDER_FIXTURES — FounderProfile seeds for the VC intelligence layer.
"""
from __future__ import annotations

# Job outreach within 90 days (case 1 expected hits)
# Noise records carry source_type_hint that InMemoryStore excludes pre-scoring.
FACT_FIXTURES: list[dict] = [
    # --- Job outreach (within 90-day temporal window) ---
    {
        "id": "fixture_job_google",
        "content": "Google recruiter approached me about a Staff Engineer job opportunity",
        "source_type_hint": "gmail_direct_outreach",
        "age_days": 15,
        "metadata": {"fact_type": "JOB_OPPORTUNITY", "company": "Google"},
    },
    {
        "id": "fixture_job_stripe",
        "content": "Stripe recruiter contacted me about a job opening for Senior Engineer",
        "source_type_hint": "gmail_direct_outreach",
        "age_days": 30,
        "metadata": {"fact_type": "JOB_OPPORTUNITY", "company": "Stripe"},
    },
    {
        "id": "fixture_job_acme",
        "content": "Acme Corp hiring manager approached me for a job as Engineering Manager",
        "source_type_hint": "gmail_direct_outreach",
        "age_days": 7,
        "metadata": {"fact_type": "JOB_OPPORTUNITY", "company": "Acme"},
    },
    # --- Job outreach OUTSIDE 90-day window (must not appear in case 1 results) ---
    {
        "id": "fixture_job_microsoft",
        "content": "Old recruiter email from Microsoft about SDE role",
        "source_type_hint": "gmail_direct_outreach",
        "age_days": 120,
        "metadata": {"fact_type": "JOB_OPPORTUNITY", "company": "Microsoft"},
    },
    # --- Noise records (excluded via source_type_hint in InMemoryStore) ---
    {
        "id": "fixture_noise_newsletter",
        "content": "Weekly digest: top AI news and job openings this week",
        "source_type_hint": "gmail_newsletter",
        "age_days": 2,
        "metadata": {"fact_type": "NEWSLETTER"},
    },
    {
        "id": "fixture_noise_job_alert",
        "content": "LinkedIn Jobs alert: 47 new Software Engineer roles matching your profile",
        "source_type_hint": "gmail_job_alert",
        "age_days": 1,
        "metadata": {"fact_type": "JOB_ALERT"},
    },
    # --- Founder signals (case 2 expected hits) ---
    {
        "id": "fixture_founder_alice_raising",
        "content": (
            "Alice Chen from Acme AI is raising a $2M seed round. "
            "She reached out asking for an intro to Sequoia."
        ),
        "source_type_hint": None,
        "age_days": 5,
        "metadata": {"fact_type": "FOUNDER_SIGNAL", "company": "Acme AI"},
    },
    {
        "id": "fixture_founder_alice_deck",
        "content": (
            "Acme AI pitch deck arrived. They are targeting Series A next year "
            "but doing a seed bridge now."
        ),
        "source_type_hint": None,
        "age_days": 7,
        "metadata": {"fact_type": "FOUNDER_SIGNAL", "company": "Acme AI"},
    },
    # --- Follow-up records (case 3 expected hits, within 7 days) ---
    {
        "id": "fixture_followup_bob",
        "content": (
            "Bob from DataStream followed up on our meeting. "
            "He sent over the term sheet for review."
        ),
        "source_type_hint": None,
        "age_days": 1,
        "metadata": {"fact_type": "FOLLOW_UP"},
    },
    {
        "id": "fixture_followup_carol",
        "content": (
            "Carol followed up about the partnership discussion. "
            "She wants to reconnect this week."
        ),
        "source_type_hint": None,
        "age_days": 2,
        "metadata": {"fact_type": "FOLLOW_UP"},
    },
]

# Founder seeds for the VC intelligence layer.
# signal_age_days drives last_contact_date which feeds recency_score.
FOUNDER_FIXTURES: list[dict] = [
    {
        "statement": "Alice Chen from Acme AI raising $2M seed round in deeptech",
        "entities": {"company": "Acme AI", "person": "Alice Chen", "stage": "seed"},
        "domain": "deeptech",
        "signal_age_days": 5,
        "signal_type": "meeting_requested",  # urgency=0.8 → score ≈ 0.67
    },
    {
        "statement": "Bob Rao from FinStack looking for angel investors, fintech pre-seed",
        "entities": {"company": "FinStack", "person": "Bob Rao", "stage": "pre-seed"},
        "domain": "fintech",
        "signal_age_days": 45,
        "signal_type": "outreach",  # urgency=0.1, recency=0.5 → score ≈ 0.30
    },
    {
        "statement": "Charlie Wu from OldDeal exploring fundraise options, saas idea stage",
        "entities": {"company": "OldDeal", "person": "Charlie Wu", "stage": "idea"},
        "domain": "saas",
        "signal_age_days": 200,
        "signal_type": "outreach",  # urgency=0.1, recency=0.2 → score ≈ 0.18
    },
]
