# CONTEXT.md

Working state for the current build session. Updated by the agent at the end of every session. Read this alongside `CLAUDE.md`.

---

## Current Phase

**H3 — Strategy — S1 done, S2 in progress**

H1 (foundation) and H2 (research agent) shipped Aug 9, well inside the original 7-day target. H3-S1 (season retrospective) is done. H3-S2 (personal draft strategy synthesis) is being built now. H4 (live draft helper) is the hard deadline — Sep 3, 2026.

---

## H3 — Strategy — In Progress

- [x] #8 H3-S1 — Season retrospective (commit `aef687b`)
- [ ] #9 H3-S2 — Personal ADP / draft strategy synthesis — in progress this session
- [x] #7 Transaction-level history for the retrospective — deprioritized to Backlog (#10), not pursued

---

## H1 + H2 — Complete

- [x] #1 H1 — Foundation: ESPN adapter, JSON persistence, FastAPI skeleton (commit `ed222a4`)
- [x] #2 H2 — Research: materiality-filtered pre-draft research agent (commit `04f9168`)

---

## Session Notes

### 2026-08-09 — H3-S2 — Personal draft strategy synthesis (in progress)
- `app/models/league.py`: added `LeagueSettings` (team_count, scoring_type, points_per_reception, playoff_team_count, keeper_count, position_slot_counts) and `League.settings`.
- `app/adapters/espn.py`: `_to_league_settings()` extracts PPR from `scoring_format` (finds the `REC` row), filters `position_slot_counts` to non-zero slots only.
- `app/services/strategy_service.py`: `StrategyService` combines this year's league settings, last year's retrospective (via `RetrospectiveService`, year-1, gracefully handles `ValueError` if not synced), and current materiality-filtered news (via `ResearchService`, filtered to `material=True` only) into one LLM synthesis call. Explicit prompt instruction not to fabricate rankings/news when inputs are thin.
- `app/routers/strategy.py`: `GET /strategy/{year}`.
- Real league settings confirmed live: 12-team H2H_POINTS, full PPR (1.0 pt/reception), 1 QB/2 RB/2 WR/1 TE/1 FLEX/1 D/ST/1 K, 4 bench, 1 IR, no keepers, FAAB waivers ($100 budget).
- Scope call: v1 is a narrative synthesis (targets/sleepers/roster-construction guidance named within prose), not a full ranked ADP over ~200 players — no expert-rankings data source is ingested yet, so a full ranked board would be ungrounded LLM guessing rather than synthesis over trusted inputs. Revisit if a rankings source gets added later.
- User manually pasted ESPN's Draft Recap page (`.input/draft_recap`, gitignored) — diffed byte-for-byte against the API-pulled 2025 draft data for "Shiznits" (all 13 picks matched exactly), confirming H1's draft-pull adapter is fully accurate.
- User also wanted ESPN's waiver/transaction report (issue #7) pulled programmatically; declined — that page requires an authenticated session WebFetch can't use, and cookie-authenticated HTML scraping is exactly what the project's ADR rules out (no browser automation/DOM scraping of ESPN). Paste-into-`.input/` remains the sanctioned path for data ESPN's API doesn't expose.

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
