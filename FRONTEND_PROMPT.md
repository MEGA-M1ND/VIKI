# VIKI Frontend — Build Prompt for Emergent

> Copy everything below the line into Emergent.

---

## ROLE

You are a senior product designer + frontend engineer. Build a **stunning, demo-ready web frontend** for **VIKI — a "Company Brain" that turns a VC's noisy inbox into ranked, queryable intelligence.** This is for a **live hackathon demo in front of judges**, so it must look like a funded seed-stage product, not a prototype. Polish, motion, and a clear narrative beat feature-count.

## THE PRODUCT (what VIKI does)

VIKI ingests a VC investor's emails/notes, extracts structured facts, and answers natural-language questions over them with **hybrid retrieval** (semantic + keyword search fused via Reciprocal Rank Fusion), **temporal filtering** ("lately" = last 30 days), **source-type weighting** (direct outreach ranks far above newsletters), and **noise rejection** (newsletters, job alerts, digests are filtered out). It also maintains a **VC intelligence layer**: a ranked list of founders with a computed `signal_score` (recency + frequency + urgency of their fundraising signals).

**The killer demo moment:** the investor types *"which companies approached me for a job lately"* — and VIKI returns Google, Stripe, Acme with zero newsletter noise, each with a relevance score, source type, and age. The metric that proves it works: **Precision@5 = 0.80, noise rate = 0.00.**

## TECH STACK (required)

- **React + TypeScript + Vite**
- **Tailwind CSS** for styling
- **Framer Motion** for animation
- **shadcn/ui** for base components (buttons, cards, inputs, dialogs, tabs, badges, skeletons)
- **Recharts** for any charts
- **lucide-react** for icons
- A typed `api.ts` client wrapping `fetch`, base URL from `VITE_API_BASE_URL` (default `http://localhost:8000`)
- **Mock mode**: a `VITE_USE_MOCKS=true` flag that serves realistic in-memory fixtures so the UI is fully demoable with the backend off (critical — never let the demo depend on a live server)

## DESIGN LANGUAGE

- **Dark-first**, sophisticated. Near-black background (`#0A0A0F`), elevated surfaces in subtle slate, **electric violet→cyan gradient** as the signature accent. Think Linear × Vercel × Perplexity.
- Typography: Inter (or Geist). Tight, confident. Big hero numbers.
- **Glassmorphism** on floating panels (backdrop blur, 1px hairline borders).
- **Micro-interactions everywhere**: staggered list reveals, animated score bars filling on mount, hover lift on cards, a subtle gradient aurora drifting in the background, smooth page transitions.
- **Empty, loading, and error states** must all be designed — skeleton shimmers, not spinners.
- Fully **responsive**; looks great on a projector (test at 1920×1080).
- Respect `prefers-reduced-motion`.

## SCREENS / LAYOUT

A persistent left sidebar (VIKI wordmark + gradient logo mark, nav, tenant switcher) and a main content area with 4 routes:

### 1. Ask (the hero screen, default route)
A Perplexity-style conversational search.
- Centered hero on empty state: gradient "VIKI" wordmark, tagline *"Your inbox, ranked."*, a large pill search input, and 4 clickable **example query chips** (use the demo queries below).
- On submit: input animates to the top, a **thinking indicator** appears (animated gradient dots), then the **synthesized answer** streams in as a glassy card.
- Below the answer: a **"Sources" / ranked results** section — each result is a row/card showing: the fact text, an animated **relevance score bar** (0–1), a **source-type badge** (color-coded: `direct outreach` = green, `newsletter`/`digest` = muted gray, `reply thread` = blue), and a **relative age** ("7d ago") with a small clock icon.
- A subtle **"temporal filter active: last 30 days"** chip when the query implies a time window.
- Keyboard: Enter submits, Shift+Enter newline, `/` focuses input.

### 2. Founders (VC intelligence)
A ranked leaderboard of founders.
- Each founder = a card: name, company, **stage badge** (idea / pre-seed / seed / series-a / series-b+), domain tag, location, last-contact age, and a prominent **signal score** rendered as both a number and a radial/bar gauge with the gradient fill.
- **Filter bar**: min score slider, stage dropdown, domain dropdown — filtering animates the list (Framer layout animations).
- Sort by signal score desc by default. Top founder gets a subtle "🔥 hot" glow.

### 3. Pipeline / Deals
A kanban-ish or grouped-list view of deals by `deal_stage` (cold → warm → active → portfolio → passed), each card showing company, raise amount, last activity, next action.

### 4. Ingest / Live Demo Control
A control panel for the demo operator:
- A big **"Ingest Inbox"** button that calls the ingest endpoint and shows an animated stat readout (fetched / extracted / ingested / skipped) with count-up numbers.
- A small **"Eval Scorecard"** widget showing the headline proof metrics as animated stat cards: **Precision@5: 0.80**, **Noise Rate: 0.00**, **Mean P@5: 0.93** — these are the numbers judges remember. Make them gorgeous.

## API CONTRACT (match exactly — backend is FastAPI)

Base URL: `http://localhost:8000`. All VC endpoints require either an `X-Tenant-ID` header or `?tenant_id=` query param (use `demo`).

```
POST /ask
  body: { "query": string, "tenant_id"?: string, "limit"?: number }
  200:  { "answer": string, "sources": string[], "hit_count": number }
  503 when no LLM configured → show a friendly "LLM not connected, showing retrieved results" fallback

GET /vc/founders?tenant_id=demo&min_score=&stage=&domain=
  200: FounderProfile[]  (sorted by signal_score desc)

GET /vc/deals?tenant_id=demo&stage=&since=
  200: DealOpportunity[]  (sorted by last_activity_date desc)

GET /vc/signals?tenant_id=demo&founder_id=&since=
  200: FundSignal[]  (sorted by signal_date desc)

POST /ingest/run
  body: { "source": "gmail", "lookback_hours": 48, "dry_run": false }
  200:  { source, fetched, normalized, ingested, skipped, failed, errors, started_at }

GET /ingest/status → { [source]: IngestRunResponse }
GET /health → health status
```

### Type shapes

```ts
type FounderProfile = {
  id: string;                 // uuid
  tenant_id: string;
  full_name: string;
  company_name: string;
  stage: "idea" | "pre-seed" | "seed" | "series-a" | "series-b+";
  domain: string;             // "fintech" | "deeptech" | "saas" | ...
  location: string;
  last_contact_date: string;  // ISO datetime
  signal_score: number;       // 0..1
  raw_signals: string[];
  source_doc_ids: string[];
  created_at: string;
  updated_at: string;
};

type DealOpportunity = {
  id: string; tenant_id: string; founder_id: string;
  company_name: string;
  deal_stage: "cold" | "warm" | "active" | "passed" | "portfolio";
  raise_amount_usd: number | null;
  last_activity_date: string;
  next_action: string | null;
  source_doc_ids: string[];
};

type FundSignal = {
  id: string; tenant_id: string;
  signal_type: "outreach" | "follow_up" | "deck_shared" | "meeting_requested" | "term_sheet" | "pass";
  founder_id: string | null;
  company_name: string;
  signal_date: string;
  raw_text: string;
  confidence: number;
};

type AskResponse = { answer: string; sources: string[]; hit_count: number };
```

> ⚠️ The `/ask` response only returns `answer`, `sources` (string[]), and `hit_count`. The rich per-result data (score bar, source-type badge, age) you want for the ranked results UI is **not** in this payload yet. For the demo, **render the ranked results from MOCK fixtures** (see below) so the UI is visually complete, and wire `answer`/`hit_count` from the live endpoint when available. Design the result-row component so it can later bind to a richer backend response without rework.

## MOCK FIXTURES (use these verbatim for the showcase)

Seed mock mode with this so the demo always looks perfect:

**Ask — "which companies approached me for a job lately" (temporal: last 30 days):**
- "Acme Corp hiring manager approached me for a job as Engineering Manager" — score 0.95, `direct outreach`, 7d
- "Google recruiter approached me about a Staff Engineer job opportunity" — score 0.92, `direct outreach`, 15d
- "Stripe recruiter contacted me about a job opening for Senior Engineer" — score 0.88, `direct outreach`, 30d
- (Excluded by VIKI — show a collapsed "2 noisy results filtered" affordance): "Weekly digest: top AI news and job openings", "LinkedIn Jobs alert: 47 new roles"
- Answer: *"Three companies reached out about roles in the last 30 days: Acme Corp (Engineering Manager), Google (Staff Engineer), and Stripe (Senior Engineer). Newsletter and job-alert noise was filtered out."*

**Founders:**
- Alice Chen — Acme AI — seed — deeptech — SF — signal_score 0.67 — last contact 5d — 🔥
- Bob Rao — FinStack — pre-seed — fintech — NYC — signal_score 0.30 — last contact 45d
- Charlie Wu — OldDeal — idea — saas — Austin — signal_score 0.18 — last contact 200d

**Deals:** invent 4–5 plausible deals across stages tied to the founders above.

**Eval scorecard:** Precision@5 = 0.80, Noise Rate = 0.00, Mean P@5 = 0.93, Tests passing = 98.

## DEMO NARRATIVE (build the UI to support this 90-second flow)

1. Land on **Ask** — clean hero, judges see the wordmark.
2. Click the chip *"which companies approached me for a job lately"* → thinking dots → answer streams → ranked results fan in with score bars filling → the **"2 noisy results filtered"** chip lands the differentiator.
3. Jump to **Founders** → Alice Chen glows at top with 0.67 → tweak the min-score slider → list re-animates.
4. Jump to **Ingest** → hit "Ingest Inbox" → counters count up → **Eval Scorecard** shows 0.80 / 0.00 and a one-line caption: *"Precision@5 0.80, zero noise — VIKI is shippable."*

## DELIVERABLES

- Complete Vite + React + TS project, `npm install && npm run dev` runs clean.
- `.env.example` with `VITE_API_BASE_URL` and `VITE_USE_MOCKS`.
- A `mocks/` module with the fixtures above and a toggle so the entire app works offline.
- Reusable components: `ScoreBar`, `SourceBadge`, `StageBadge`, `RelativeTime`, `StatCard`, `ThinkingDots`, `ResultRow`, `FounderCard`.
- README with run instructions and a "Demo script" section reproducing the 90-second flow.
- Accessible (keyboard nav, focus rings, aria labels), responsive, reduced-motion safe.

## CONSTRAINTS

- No backend changes — consume the API exactly as specified.
- Don't invent endpoints that aren't listed; use mocks for anything the API doesn't expose.
- Keep dependencies lean; no heavyweight UI kits beyond shadcn/ui.
- Every async state needs a designed loading + error + empty variant.

**Make it the kind of UI that makes a judge say "wait, you built this in a weekend?" Prioritize the Ask screen and the Eval Scorecard — those win the room.**
