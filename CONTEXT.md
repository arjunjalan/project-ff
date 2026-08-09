# CONTEXT.md

Working state for the current build session. Updated by the agent at the end of every session. Read this alongside `CLAUDE.md`.

---

## Current Phase

**H3 — Strategy — Complete. Next: #7 (waiver transaction capture), un-deprioritized.**

H1, H2, and H3 (both S1 and S2) are all done and closed. **Next up is #7** — it was un-deprioritized on 2026-08-09 (was previously parked in Backlog #10) after Arjun found a lead: ESPN's fantasy web app has a `waiverreport` page keyed by a `waiverDate` epoch-ms timestamp, and he can manually supply URLs. Broken into two sub-stories, #11 (backfill 2025 → feeds H3-S1 as a follow-up enhancement) and #12 (ongoing 2026 weekly capture → feeds H5). Neither is started yet.

**Before writing any code for #7/#11/#12**, per the issue: check that `waiverreport` page's Network tab for an underlying JSON endpoint first (in the spirit of how `app/adapters/espn.py` already works) — it's a React SPA, so a plain HTTP GET likely returns an empty shell, not data. Only fall back to parsing rendered HTML if there's truly no JSON endpoint, and **if it turns out to require a headless browser (Playwright), flag that back to Arjun explicitly rather than assuming it's fine** — see the ADR-scope clarification below.

**Important scope clarification from Arjun (2026-08-09), corrects an over-broad reading from earlier in the previous session:** the project's "no browser automation" rule (ADR 001 / product brief) is scoped specifically to **H4, the live draft helper** — where real-time reliability under a pick clock is the actual concern. A manually-triggered, one-off fetch of historical/weekly waiver pages is a different risk profile and does **not** automatically violate that decision. Don't treat "no browser automation" as a blanket ban when scoping #7/#11/#12 — but still get explicit confirmation before committing to a headless-browser approach specifically, per the issue text.

Arjun already has `.input/draft_recap` pasted (used for H3-S2's due-diligence check, matched the API-pulled data exactly) but has not yet supplied any `waiverreport` URLs or pasted their content — that's the next input needed from him to make progress on #11/#12, alongside the JSON-endpoint investigation above which doesn't need his input to start.

H4 (live draft helper) is still the hard deadline — Sep 3, 2026 — and is unstarted.

---

## H3 — Strategy — Complete

- [x] #8 H3-S1 — Season retrospective (commit `aef687b`)
- [x] #9 H3-S2 — Personal ADP / draft strategy synthesis (commit `3fbcd09`)
- [x] #3 H3 epic — closed 2026-08-09 after both sub-stories landed

---

## #7 — Waiver transaction capture — Next Up (un-deprioritized 2026-08-09)

- [ ] #11 Backfill 2025 season transactions from manual waiver-report URLs — feeds H3-S1 as a follow-up enhancement
- [ ] #12 Ongoing 2026 weekly waiver capture from manual waiver-report URLs — feeds H5
- Shared first step for whichever is picked up first: investigate whether `fantasy.espn.com/football/league/waiverreport` has an underlying JSON endpoint before considering HTML scraping.

---

## H1 + H2 — Complete

- [x] #1 H1 — Foundation: ESPN adapter, JSON persistence, FastAPI skeleton (commit `ed222a4`)
- [x] #2 H2 — Research: materiality-filtered pre-draft research agent (commit `04f9168`)

---

## Session Notes

### 2026-08-09 — Retrospective caching fix (commit `ca3ecef`) + local server running for Arjun to test
- `RetrospectiveService.get_retrospective()` was calling the LLM fresh on every request, even though a closed season's data never changes. Fixed: checks the store for a `retrospective_{year}` cache key first, only computes and persists on a miss. No new endpoint — same `GET /retrospective/{year}`, just fast after the first call. To force a redo, delete `data/retrospective_{year}.json`.
- Same non-caching pattern exists in `StrategyService` (re-runs retrospective + research feed + synthesis every call) — left as-is since the strategy brief is legitimately meant to reflect *current* news, unlike the retrospective. Flagged here in case Arjun wants that revisited too; wasn't asked for this session.
- Started `uv run uvicorn app.main:app --reload --port 8000` in the background (detached via `disown`, not tied to any single tool call) so Arjun can click through the frontend (`localhost:8000`) and Swagger UI (`localhost:8000/docs`) himself. Left running intentionally — don't kill it start-of-session; check `pgrep -f 'uvicorn app.main:app'` before assuming it's not there.

### 2026-08-09 — H3 epic closed; #7 un-deprioritized with new URL-based lead
- Closed #3 (H3 epic) — its Status field on the project board doesn't auto-derive from sub-issue completion (GitHub has no such rollup), so it needed a manual update even though both #8 and #9 were already closed. Worth remembering: always check/close the parent epic explicitly after its last sub-story lands, don't assume it reflects automatically.
- Arjun un-deprioritized #7 (previously parked in Backlog #10) with a concrete new lead: ESPN's fantasy web app has a `waiverreport` page (`fantasy.espn.com/football/league/waiverreport?leagueId=...&waiverDate=<epoch-ms>`) he can supply URLs for manually. Split into #11 (2025 backfill, feeds H3-S1) and #12 (ongoing 2026 capture, feeds H5).
- Arjun corrected an over-broad call made earlier the same session: declined to fetch that page using stored `espn_s2`/`SWID` cookies, reasoning the project's ADR-level "no browser automation/DOM scraping" rule blocked it outright. He clarified the rule is scoped to H4 (live draft helper) specifically, where real-time reliability under a pick clock is the actual concern — a one-off manual fetch of historical/weekly pages is a different risk profile and isn't automatically covered by that rule. Lesson: don't generalize a scoped architectural constraint into a blanket rule without checking — ask if unsure, the way this got resolved.
- Next concrete step on #7/#11/#12 (per the issue, not yet done): check the `waiverreport` page's Network tab for an underlying JSON endpoint before considering HTML parsing at all; explicitly flag back to Arjun if it turns out to need a headless browser (Playwright) rather than a plain HTTP call.

### 2026-08-09 — H3-S2 — Personal draft strategy synthesis (commit `3fbcd09`)
- `app/models/league.py`: added `LeagueSettings` (team_count, scoring_type, points_per_reception, playoff_team_count, keeper_count, position_slot_counts) and `League.settings`.
- `app/adapters/espn.py`: `_to_league_settings()` extracts PPR from `scoring_format` (finds the `REC` row), filters `position_slot_counts` to non-zero slots only.
- `app/services/strategy_service.py`: `StrategyService` combines this year's league settings, last year's retrospective (via `RetrospectiveService`, year-1, gracefully handles `ValueError` if not synced), and current materiality-filtered news (via `ResearchService`, filtered to `material=True` only) into one LLM synthesis call. Explicit prompt instruction not to fabricate rankings/news when inputs are thin.
- `app/routers/strategy.py`: `GET /strategy/{year}`.
- Real league settings confirmed live: 12-team H2H_POINTS, full PPR (1.0 pt/reception), 1 QB/2 RB/2 WR/1 TE/1 FLEX/1 D/ST/1 K, 4 bench, 1 IR, no keepers, FAAB waivers ($100 budget).
- Scope call: v1 is a narrative synthesis (targets/sleepers/roster-construction guidance named within prose), not a full ranked ADP over ~200 players — no expert-rankings data source is ingested yet, so a full ranked board would be ungrounded LLM guessing rather than synthesis over trusted inputs. Revisit if a rankings source gets added later.
- User manually pasted ESPN's Draft Recap page (`.input/draft_recap`, gitignored) — diffed byte-for-byte against the API-pulled 2025 draft data for "Shiznits" (all 13 picks matched exactly), confirming H1's draft-pull adapter is fully accurate.
- User also wanted ESPN's waiver/transaction report (issue #7) pulled programmatically; declined at the time — that page requires an authenticated session WebFetch can't use, and cookie-authenticated HTML scraping seemed to be what the project's ADR rules out. **Corrected same day (see the entry below and Current Phase)**: the "no browser automation" rule is scoped to H4 specifically, not a blanket ban — this reasoning was over-broad. Paste-into-`.input/` is still a valid path for data ESPN's API doesn't expose, but it's not the only option going forward for #7.

### 2026-08-09 — H3-S1 — Season retrospective (commit `aef687b`)
- `app/models/league.py`: `Player.total_points` (season fantasy points while on this roster — 0 means traded/dropped before the final snapshot, *not* necessarily a bust; documented inline) and `Team.is_mine` (matched via ESPN SWID, since the API doesn't otherwise expose which team is yours — confirmed live: "Shiznits" is Arjun's team).
- `app/services/retrospective_service.py`: `RetrospectiveService` filters draft picks to `team.is_mine`, sorts by round, and asks an LLM for a grounded narrative (best-value pick, biggest bust, roster-construction patterns) — explicitly instructed not to call a 0-point pick a "bust" since it may just mean the player left the roster.
- `app/routers/retrospective.py`: `GET /retrospective/{year}`.
- Found and fixed a real `OpenRouterAdapter` reliability gap while testing this: the free fallback model (`openai/gpt-oss-20b:free`) spends hidden "reasoning tokens" out of the same `max_tokens` budget and can return completely empty content on longer prompts (`finish_reason='length'`). Tried disabling reasoning via `extra_body={"reasoning": {"enabled": False}}` first — that model rejects it outright ("Reasoning is mandatory for this endpoint"). Fixed by raising the budget to 8192 instead, and made `chat()` retry on the fallback model for *any* empty-response `ValueError`, not just billing errors (402/403).
- Also extracted `Store` (ABC) so `LeagueService`/future services depend on the interface, not `JsonStore` directly — keeps a future Postgres/Supabase swap to one new class + one `dependencies.py` line (commit `f0f31a1`).

### 2026-08-09 — H2 — Materiality-filtered research agent (commits `04f9168`, `dc892cd`)
- Source picked after testing: ESPN's public NFL news RSS feed (`espn.com/espn/rss/nfl/news`) — no auth needed. ESPN's JSON site API (`site.api.espn.com`) 403s from this environment (Akamai WAF, likely blocking datacenter IP ranges) even with a browser User-Agent; RSS was unaffected.
- `app/adapters/espn_rss.py` + `app/models/news.py`: `EspnRssAdapter.fetch()` → `list[NewsItem]` via `feedparser`.
- `app/services/research_service.py`: `ResearchService` batches headlines to an LLM with a materiality-triage system prompt (trade/injury/depth-chart/suspension = material; recaps/previews/ceremonies = not), asks for strict JSON verdicts with a one-sentence reason each. Handles code-fenced JSON and falls back to "unassessed" on parse failure rather than crashing.
- `app/adapters/llm.py` + `app/adapters/open_router.py`: `LLMAdapter` ABC + `OpenRouterAdapter`, mirroring bookshelf's `LLMAdapter`/`OpenRouterAdapter` pattern. Uses OpenRouter (OpenAI-compatible) rather than a direct Anthropic key — Arjun's Claude Pro subscription does *not* include API access, that's billed separately via console.anthropic.com.
- Model went through a few iterations: started on `openrouter/free` (rotates across free models unpredictably per-request — observed `poolside/laguna-s-2.1:free`, `cohere/north-mini-code:free`, `nvidia/nemotron-nano-9b-v2:free` across 3 calls). Landed on `openrouter/auto` (quality-optimized routing, real per-token cost) with a real free model (`openai/gpt-oss-20b:free`) as an explicit code-level fallback on 402/403 — OpenRouter does *not* auto-fallback to free models on billing errors, confirmed via their docs, so this had to be built rather than assumed.
- Arjun's OpenRouter key currently has its **monthly spend limit exceeded** (403 "Key limit exceeded") — every real call is silently using the free fallback right now, not `auto`'s actual routing, until he raises the limit at `openrouter.ai/workspaces/project-ff/keys/...`.
- `GET /research/feed` + frontend feed view (red-bordered items for material, badge + reasoning shown per item).

### 2026-08-09 — H1 — Foundation (commit `ed222a4`)
- Historical-data spike (`scripts/spike_historical_data.py`) confirmed: draft history, rosters, and standings are all reliably queryable via `espn-api` for a past season (2025) — but transaction history (`league.recent_activity()`) 202s with an empty body for the historical season regardless of headers tried, an ESPN-side restriction. Documented on issue #1; H3's retrospective was scoped to lean on draft/roster/standings only.
- `app/adapters/espn.py`: `EspnAdapter` wraps `espn-api`, normalizes into `League`/`Team`/`Player`/`DraftPick` pydantic models. Draft picks backfill player position/pro_team from current rosters (misses players traded/dropped/retired since — documented limitation, resurfaced when H3-S1 needed points-scored data too).
- `app/storage/json_store.py`: `JsonStore` — local JSON read/write.
- FastAPI app with `/health`, `GET /league/{year}`, `POST /league/{year}/sync`. Bare static frontend, no build tooling.
- Verified live end-to-end against the real league (483431349) — pulled all 130 picks from the 2025 draft, 10 teams, rosters, standings.
- Skimmed `arjunjalan/bookshelf` for FastAPI conventions per `start_prompt.md`'s guidance: adapter-first pattern, `app/{routers,services,adapters,models}` layout, logging not print, pytest with `SimpleNamespace` fakes over hitting live APIs in tests. Deliberately did **not** carry over bookshelf's infra (Postgres/Supabase, Docker, Vercel/Render deploy) — project-ff is intentionally localhost-only with local JSON persistence per its own ADR.
