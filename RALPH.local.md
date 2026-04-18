There is already a brainstorm document on docs/brainstorms/social-media-organizer.md

There is already a plan document on docs/plans/2026-04-13-001-feat-social-media-organizer-telegram-bot-plan.md

## Current status

- Step 1 (ce-brainstorm): DONE — docs/brainstorms/social-media-organizer.md
- Step 2 (ce-plan): DONE — docs/plans/2026-04-13-001-feat-social-media-organizer-telegram-bot-plan.md
- Step 3 (ce-work): DONE — all 14 units implemented, 147 tests passing (all green)
- Step 4 (ce-review): DONE — review findings applied and committed (commit: 5aa062f)
- Step 5 (ce-compound): DONE — solution doc written + Phase 3 reviewer ran + two additional fixes applied and committed (bfade4b)

## What was implemented

All 14 plan units are complete:

- Unit 1: Project scaffolding (pyproject.toml, config.py, directory layout)
- Unit 2: SQLAlchemy models (User, Subject, Post, Reminder, HeuristicProfile, StrategyNote, ImportBatch)
- Unit 3: Alembic async migrations (initial schema)
- Unit 4: bot/main.py — Dispatcher wiring, AllowlistMiddleware, SessionMiddleware, FSM storage
- Unit 5: APScheduler setup (build_scheduler, SchedulerService, synchronous SQLAlchemyJobStore)
- Unit 6: ChromaDB VectorStore wrapper (asyncio.to_thread throughout)
- Unit 7: PredictionService (SentenceTransformer embeddings, DBSCAN clustering, LLM enrichment)
- Unit 8: Heuristics (recency, cooldown, strategy_align, novelty, platform_fit, jitter) + HeuristicRegistry
- Unit 9: SuggestionEngine (epsilon-greedy, NoSubjectAvailableError)
- Unit 10: /start handler + User/HeuristicProfile seed, FSM-backed SqliteStorage
- Unit 11: /idea, /pool, /posted handlers
- Unit 12: /schedule handler + reminder_fire_handler
- Unit 13: /import handler + ImportService + platform importers (Instagram, TikTok, Threads, GenericCsv)
- Unit 14: /strategy, /settings handlers + Docker/Nginx config

## Review findings applied (ce-review commit 5aa062f)

- P0: All 9 routers now registered in build_dispatcher()
- P0: All services created and injected into dp.data with keys matching handler parameter names
- P1: APScheduler fire function is now a closure (_fire_reminder) that captures injected deps and resolves user_id from DB at fire time
- P1: Added missing sched:post: callback handler
- P1: asyncio.create_task now has done_callback for cluster_import exceptions
- P2: ZIP path traversal guard added to _extract()
- P2: doc.file_size is not None check (was falsy — bypassed on size=0)
- P2: _finalize_post/_finalize_post_msg deduplicated via _save_post() helper
- P2: data_dir exposed as public property on ImportService
- P3: datetime.utcnow → datetime.now(timezone.utc) in import_batch.py

## ce-compound progress (COMPLETE)

Solution doc created and finalized:
  docs/solutions/integration-issues/missing-router-and-service-wiring-2026-04-14.md

Phase 3 (Kieran Python reviewer) completed. Two additional fixes applied:
- ZIP traversal: str.startswith → Path.is_relative_to() (sibling-dir bypass was real)
- done_callback: lambda (called t.exception() twice) → named function with walrus operator

All committed in bfade4b.

## What didn't work / avoid

- Parallel external research agents simultaneously → rate limit hits. Use sequential agents if limits active.
- ce-review sub-agents hit rate limits during review (returned 0 tokens). Review was done inline by orchestrator.
- Session Historian also hit rate limits in ce-compound Phase 1.
- APScheduler 3.x does NOT have AsyncSQLAlchemyJobStore (that is 4.x only). Use synchronous SQLAlchemyJobStore with sqlite:/// URL.
- Aiogram DI: dp["scheduler_svc"] will NOT inject into handlers with parameter name scheduler_service. Keys must match exactly.
- Do not start APScheduler before asyncio.run() — must start inside on_startup hook to share the event loop.

## Stale doc to fix

docs/brainstorms/social-media-organizer.md §3 references AsyncSQLAlchemyJobStore — this class does not exist in APScheduler 3.x. Consider running ce:compound-refresh on it or manually correcting that section.

## Next steps if continuing

- Verify the Kieran Python reviewer (Phase 3) findings and update solution doc if needed
- Run ce:compound-refresh on brainstorm doc to fix AsyncSQLAlchemyJobStore reference
- Consider deploying to VPS to test webhook mode end-to-end
- The bot is feature-complete and tested — ready for real use
