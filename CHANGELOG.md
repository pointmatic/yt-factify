# Changelog

All notable changes to yt-factify are documented in this file.

## [0.5.7] — 2026-02-07

### Throttle Tuning & Concurrency Controls
- **Stochastic jitter** on dispatch timing — concurrent requests no longer fire at the same instant, reducing burst-then-stall patterns
- **Raised base backoff** from 5 s to 15 s (sequence: 15 s, 30 s, 60 s) — better aligned with per-minute token budgets
- **`--initial-concurrency` CLI flag** — start conservative and let the throttle organically promote to max after sustained success
- **`--max-concurrency` CLI flag** — cap the ceiling for users who prefer steady trickle over burst-stall
- New `initial_concurrent_requests` config field (env: `YT_FACTIFY_INITIAL_CONCURRENT`)
- 8 new tests (312 total)

## [0.5.6] — 2026-02-07

### Transcript Fetch Resilience
- Bypass `yt-fetch` disk cache: set `force_transcript=True` and `force_metadata=True` so transcripts are always fetched fresh from YouTube
- Add retry with 5 s delay for transient YouTube blocks (`transcript=None` with no explicit errors)
- Hard failures with explicit error messages fail immediately without retry
- Log `transcript_fetch_retry` warning on transient retry

## [0.5.5] — 2026-02-07

### Adaptive Rate Throttle
- New `AdaptiveThrottle` class in `src/yt_factify/throttle.py` — global coordination of all concurrent LLM requests
- Token-bucket dispatch: controls concurrency and minimum interval between API calls
- **Deceleration:** When 3+ rate-limit failures occur in a 60s sliding window, halves concurrency and doubles dispatch interval
- **Reacceleration:** After 60s cooling period with zero failures, steps concurrency back up by 1 (never exceeds safe ceiling)
- Progress reporting: logs % complete, ETA, current concurrency, and dispatch interval at 10% intervals
- Integrated into all LLM call sites: `llm_completion`, `extract_items`, `classify_video`, `assess_credibility`, `cluster_topic_threads`
- Pipeline instantiates a shared throttle and passes it through all stages
- Backward compatible: all throttle parameters are optional (defaults to simple semaphore when absent)
- 20 new tests (304 total)

## [0.5.4] — 2026-02-07

### Transcript Fetch Diagnostics
- Updated `yt-fetch` dependency to v0.5.2 (fixes `transcript=None` and `metadata=None` bugs)
- Added `VideoMetadata` model for video metadata passthrough (title, channel, upload date)
- `RawTranscript` now carries optional `metadata` from yt-fetch
- Upload-date heuristic in transcript error messages:
  - <24h: "captions may not be available yet"
  - 1–7 days: "auto-generated captions may still be processing"
  - >7 days: "may lack captions or they may be disabled"
- Split error handling: `success=False` vs `transcript=None` now have distinct messages
- Pipeline now populates `VideoInfo.title` from yt-fetch metadata
- Added `languages` config field (default: `["en"]`) and `--language` CLI flag (repeatable)
- 8 new tests (284 total)

## [0.5.3] — 2026-02-06

### Rate-Limit Resilience
- Added shared `llm_completion()` helper in `src/yt_factify/llm.py`
- Exponential backoff on rate-limit errors (5s → 120s cap, up to 6 retries)
- Retry-after hint parsing from provider error messages
- Integrated into all LLM call sites: extraction, classification, credibility, topic clustering
- Removed direct `litellm` imports from downstream modules

## [0.5.2] — 2026-02-06

### Release Polish
- Created `CHANGELOG.md`
- Final verification of all acceptance criteria
- Full test suite passing (276 tests, 96% coverage)

## [0.5.1] — 2026-02-06

### Documentation
- Created comprehensive `README.md` with installation, quick start, configuration reference, belief system module guide, output format docs, and development instructions
- Expanded `src/yt_factify/modules/README.md` with built-in modules list, copy-paste template, authoring tips, validation rules, and loading examples

## [0.4.1] — 2026-02-06

### Testing & Quality
- Added golden test fixtures: short news clip, long interview, opinion/editorial transcripts
- Added golden pipeline tests verifying classification, audit bundles, evidence, and topic threads
- Added edge case tests: empty transcript, single segment, no facts, malformed LLM response, all quotes rejected, very long transcript (>2 hours)
- Achieved 96% line coverage (core modules 94–100%)
- Ran `mypy --strict` with 0 errors
- Applied `ruff format` across all source and test files

## [0.3.2] — 2026-02-06

### Library API
- Added public API: `extract()` (async) and `extract_sync()` (sync wrapper)
- Re-exported `AppConfig`, `ExtractionResult`, `PipelineError`, `render_json`, `render_markdown` from package root
- Added module-level docstring with usage examples

## [0.3.1] — 2026-02-06

### CLI Extract Command
- Implemented `extract` CLI command with full pipeline integration
- Added CLI flags: `--model`, `--format`, `--output`, `--config`, `--log-level`, `--modules-dir`, `--quote-mismatch`, `--segment-seconds`, `--api-base`, `--api-key`, `--temperature`
- YouTube URL parsing (full URL, short URL, plain video ID)
- Exit codes: 0 (success), 1 (general), 2 (transcript), 3 (LLM), 4 (validation)
- Output to stdout or file

## [0.2.2] — 2026-02-06

### Output Rendering
- Added `render_json()` for JSON serialization of `ExtractionResult`
- Added `render_markdown()` with sections: Video Info, Topic Overview, Key Facts, Direct Quotes, Opinions & Perspectives, Unverified Claims, Predictions, Belief System Notes
- Added `write_output()` with atomic file writes (write to temp, then rename)

## [0.2.1] — 2026-02-06

### Pipeline Orchestration
- Implemented `run_pipeline()` — async orchestration of the full extraction flow
- Pipeline stages: fetch transcript → normalize → segment → load modules → classify video → extract items → validate → assess credibility → cluster topics → build audit bundle
- `PipelineError` with informative messages for each stage failure

## [0.1.2] — 2026-02-06

### Extraction & Analysis
- LLM-based item extraction with structured prompts and JSON parsing
- Video classification (categories + bias profile) via LLM
- Credibility assessment for extracted items
- Topic thread clustering with timeline derivation
- Belief/value system module loading (built-in + custom directories)
- Transcript-anchored validation: quote verification, timestamp bounds checking
- Built-in belief system modules: scientific materialism, religious theism, political progressivism

## [0.1.1] — 2026-02-06

### Foundation
- Pydantic v2 data models: `ExtractionResult`, `ExtractedItem`, `TopicThread`, `VideoInfo`, `VideoClassification`, `AuditBundle`, `CredibilityAssessment`, `BeliefSystemFlag`, `TranscriptEvidence`
- Transcript ingestion via `yt-fetch`: fetch, normalize, segment
- Configuration system with CLI > env > file > defaults precedence
- Structured logging via `structlog`
- LLM prompt templates for extraction, classification, credibility, and topic threading
- Project scaffolding with `pyproject.toml`, MPL-2.0 license
