# stories.md — yt-factify (Python)

This document breaks the yt-factify project into an ordered sequence of small, independently completable stories grouped into phases. Stories are organized by phase and reference modules defined in [`tech_spec.md`](tech_spec.md). Requirements come from [`features.md`](features.md).

Stories are numbered using the scheme `<Phase>.<letter>` (e.g., A.a, A.b, B.a). Each story that produces code changes includes a semver version number, bumped incrementally. Stories with no code changes (e.g., documentation-only) omit the version. Each story is suffixed with `[Planned]` initially and changed to `[Done]` when completed.

---

## Phase A: Foundation

### Story A.a: v0.0.1 Hello World [Done]

Minimal runnable artifact — a CLI that prints a greeting and version.

- [x] Create `pyproject.toml` with project metadata, dependencies (click, rich), and entry point `yt-factify`
  - [x] Set license to `MPL-2.0`, author to Pointmatic
  - [x] Configure Ruff and mypy in `pyproject.toml`
- [x] Create `src/yt_factify/__init__.py` with `__version__ = "0.0.1"`
- [x] Create `src/yt_factify/__main__.py` for `python -m yt_factify`
- [x] Create `src/yt_factify/cli.py` with a Click group and `version` command
- [x] Create `Makefile` with targets: `install`, `lint`, `format`, `typecheck`, `test`
- [x] Install package in dev mode and verify: `yt-factify version` prints `0.0.1`
- [x] Add MPL-2.0 copyright header to all new source files
- [x] Verify: `yt-factify version` outputs version string

### Story A.b: v0.0.2 Configuration & Logging [Done]

Set up the configuration system and structured logging.

- [x] Create `src/yt_factify/config.py` with `AppConfig` Pydantic model
  - [x] Implement config loading: CLI overrides > env vars (`YT_FACTIFY_*`) > TOML file > defaults
  - [x] Support `--config` flag for custom config file path
- [x] Create `src/yt_factify/logging.py` with structlog setup
  - [x] Configurable log level (DEBUG, INFO, WARNING, ERROR)
  - [x] JSON-compatible structured output
- [x] Wire config and logging into `cli.py`
  - [x] Add shared CLI options (`--log-level`, `--config`)
- [x] Create `tests/test_config.py`
  - [x] Test precedence: CLI > env > file > defaults
  - [x] Test env var parsing with `YT_FACTIFY_` prefix
  - [x] Test missing config file handled gracefully
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: `yt-factify extract --help` shows all config options

### Story A.c: v0.0.3 Data Models [Done]

Define all Pydantic models from the tech spec.

- [x] Create `src/yt_factify/models.py` with all enums and models:
  - [x] `ItemType`, `CredibilityLabel`, `VideoCategory`, `QuoteMismatchBehavior`
  - [x] `TranscriptSegmentRaw`, `RawTranscript`, `NormalizedSegment`, `NormalizedTranscript`, `TranscriptSegment`
  - [x] `TranscriptEvidence`, `BeliefSystemFlag`, `CredibilityAssessment`, `ExtractedItem`
  - [x] `BiasProfile`, `VideoClassification`
  - [x] `BeliefSystemModule`
  - [x] `VideoInfo`, `AuditBundle`, `ValidationResult`, `ExtractionResult`
- [x] Create `tests/test_models.py`
  - [x] Test model construction with valid data
  - [x] Test validation rejects invalid data (bad confidence ranges, missing fields)
  - [x] Test JSON serialization round-trip
  - [x] Test enum values match spec
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all model tests pass

---

## Phase B: Core Services

### Story B.a: v0.1.1 Transcript Ingestion & Normalization [Done]

Fetch transcripts via yt-fetch and normalize them.

- [x] Add `yt-fetch` to runtime dependencies in `pyproject.toml`
- [x] Create `src/yt_factify/transcript.py`
  - [x] `fetch_transcript()` — calls `yt_fetch.fetch_video()`, returns `RawTranscript`
  - [x] `normalize_transcript()` — strips whitespace, normalizes Unicode, computes SHA-256 hash
  - [x] `segment_transcript()` — splits into segments targeting ~45s, respects sentence boundaries
  - [x] Custom exceptions: `TranscriptFetchError`, `EmptyTranscriptError`
- [x] Create `tests/fixtures/transcripts/` with at least 2 sample transcript JSON files
- [x] Create `tests/test_transcript.py`
  - [x] Test normalization (whitespace, Unicode, hashing)
  - [x] Test segmentation (target duration, sentence boundaries, single-segment edge case)
  - [x] Test empty transcript raises `EmptyTranscriptError`
  - [x] Test fetch with mocked yt-fetch
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all transcript tests pass

### Story B.b: v0.1.2 Prompt Templates [Done]

Create the prompt template system and extraction prompts.

- [x] Create `src/yt_factify/prompts/__init__.py` with prompt loading utilities
  - [x] `hash_prompts()` — computes SHA-256 of concatenated prompt templates for audit
  - [x] `ChatMessage` type alias, `_system_msg()`, `_user_msg()` helpers
- [x] Create `src/yt_factify/prompts/extraction.py`
  - [x] System prompt defining item types, schema, and anchoring rules
  - [x] User prompt template accepting transcript segment text and timestamps
  - [x] `build_extraction_messages()` — returns list of message dicts for litellm
- [x] Create `src/yt_factify/prompts/classification.py`
  - [x] System prompt for video categorization
  - [x] System prompt for bias/slant detection
  - [x] `build_classification_messages()` and `build_bias_messages()`
- [x] Create `src/yt_factify/prompts/credibility.py`
  - [x] System prompt for credibility assessment
  - [x] `build_credibility_messages()` accepting items and belief modules
- [x] Create basic tests for prompt building (correct structure, no empty messages)
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: prompt tests pass

### Story B.c: v0.1.3 LLM Extraction [Done]

Implement LLM-based item extraction using litellm.

- [x] Add `litellm` to runtime dependencies in `pyproject.toml`
- [x] Create `src/yt_factify/extraction.py`
  - [x] `extract_items()` — async, processes segments concurrently with semaphore
  - [x] `_extract_segment()` — builds prompt, calls `litellm.acompletion()`, parses JSON response
  - [x] Validates response against `ExtractedItem` schema
  - [x] Retries once on malformed JSON or schema failure
  - [x] Raises `ExtractionError` on persistent failure
- [x] Create `tests/fixtures/llm_responses/` with sample extraction responses
- [x] Create `tests/test_extraction.py`
  - [x] Test prompt building with mock segments
  - [x] Test response parsing with valid fixture data
  - [x] Test malformed JSON handling (retry, then error)
  - [x] Test schema validation failure handling
  - [x] Test concurrency limiting
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all extraction tests pass

### Story B.d: v0.1.4 Validation [Done]

Post-extraction validation — quote verification, timestamp checks.

- [x] Create `src/yt_factify/validation.py`
  - [x] `validate_items()` — returns `ValidationResult` with accepted/rejected/downgraded items
  - [x] `verify_quote()` — exact substring match within timestamp range
  - [x] Timestamp bounds checking against transcript
  - [x] Behavior controlled by `quote_mismatch` config (reject or downgrade)
- [x] Create `tests/test_validation.py`
  - [x] Test exact quote match (pass)
  - [x] Test quote mismatch (reject mode)
  - [x] Test quote mismatch (downgrade mode)
  - [x] Test invalid timestamp bounds
  - [x] Test non-quote items pass through without quote check
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all validation tests pass

### Story B.e: v0.1.5 Classification & Credibility [Done]

Video categorization, bias detection, and credibility assessment.

- [x] Create `src/yt_factify/classification.py`
  - [x] `classify_video()` — async, calls LLM for category + bias profile
  - [x] `assess_credibility()` — async, adds credibility labels to items
  - [x] For long transcripts, samples representative segments (first, middle, last + random)
- [x] Create `tests/fixtures/llm_responses/` classification and credibility response fixtures
- [x] Create `tests/test_classification.py`
  - [x] Test category classification with mocked LLM
  - [x] Test bias profile generation with mocked LLM
  - [x] Test credibility assessment with mocked LLM
  - [x] Test long transcript sampling logic
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all classification tests pass

### Story B.f: v0.1.6 Belief/Value System Modules [Done]

Module loading and integration with extraction/credibility.

- [x] Create `src/yt_factify/belief_systems.py`
  - [x] `load_belief_modules()` — loads JSON files from a directory, validates against schema
  - [x] `get_builtin_modules()` — returns built-in default modules via `importlib.resources`
  - [x] Invalid files logged and skipped
- [x] Create `src/yt_factify/modules/README.md` explaining module authoring
- [x] Create 3 built-in module JSON files: `scientific_materialism.json`, `religious_theism.json`, `political_progressivism.json`
- [x] Create `tests/test_belief_systems.py`
  - [x] Test loading valid modules
  - [x] Test invalid module file is skipped with warning
  - [x] Test built-in modules load correctly
  - [x] Test module schema validation
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all belief system tests pass

### Story B.g: v0.1.7 Topic Threading [Done]

Cluster extracted items into topic threads to capture conversational structure.

- [x] Add `TopicTimeSpan` and `TopicThread` models to `src/yt_factify/models.py`
- [x] Add `topic_threads` field to `ExtractionResult`
- [x] Create `src/yt_factify/prompts/topics.py`
  - [x] System prompt for topic clustering (item grouping by subject)
  - [x] `build_topic_threading_messages()` accepting items list
- [x] Create `src/yt_factify/topics.py`
  - [x] `cluster_topic_threads()` — async, calls LLM to cluster items by topic
  - [x] Parses LLM response, validates item IDs against input
  - [x] Derives timeline from `transcript_evidence` timestamps of member items
  - [x] Retries once on malformed JSON, raises `TopicClusteringError` on failure
  - [x] Handles edge case: very few items (< 3) returns empty list
- [x] Create `tests/fixtures/llm_responses/` topic threading response fixture
- [x] Create `tests/test_topics.py`
  - [x] Test topic clustering with mocked LLM
  - [x] Test timeline derivation from item timestamps
  - [x] Test unknown item IDs are skipped
  - [x] Test malformed JSON handling (retry, then error)
  - [x] Test few-items edge case
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all topic threading tests pass

---

## Phase C: Pipeline & Orchestration

### Story C.a: v0.2.1 Pipeline Orchestration [Done]

Wire all services together into the full extraction pipeline.

- [x] Create `src/yt_factify/pipeline.py`
  - [x] `run_pipeline()` — async, orchestrates the full flow:
    1. Fetch and normalize transcript
    2. Segment transcript
    3. Load belief/value system modules
    4. Classify video (category + bias)
    5. Extract items from segments (concurrent)
    6. Validate items
    7. Assess credibility
    8. Cluster topic threads
    9. Build audit bundle
    10. Return `ExtractionResult`
  - [x] Proper error handling at each stage with informative messages
- [x] Create `tests/test_pipeline.py`
  - [x] Test full pipeline with fixture transcript and mocked LLM
  - [x] Test pipeline error handling (transcript fetch failure, LLM failure, validation failure)
  - [x] Test audit bundle is complete
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all pipeline tests pass

### Story C.b: v0.2.2 Output Rendering [Done]

JSON and Markdown output rendering.

- [x] Create `src/yt_factify/rendering.py`
  - [x] `render_json()` — serialize `ExtractionResult` to JSON string
  - [x] `render_markdown()` — human-readable Markdown summary with sections:
    - Video Info, Topic Overview, Key Facts, Direct Quotes, Opinions & Perspectives, Unverified Claims, Predictions, Belief System Notes
  - [x] Atomic file writes (write to temp, then rename)
- [x] Create `tests/test_rendering.py`
  - [x] Test JSON output matches schema
  - [x] Test Markdown output contains expected sections
  - [x] Test atomic write (file exists only after success)
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: all rendering tests pass

---

## Phase D: CLI & Library API

### Story D.a: v0.3.1 CLI Extract Command [Done]

Wire the pipeline into the CLI `extract` command.

- [x] Update `src/yt_factify/cli.py`
  - [x] Implement `extract` command: parse video URL/ID, load config, run pipeline, render output
  - [x] Add all CLI flags from tech spec (`--model`, `--format`, `--output`, `--modules-dir`, etc.)
  - [x] Exit codes: 0 (success), 1 (general), 2 (transcript), 3 (LLM), 4 (validation)
  - [x] Write output to stdout or file per `--output` flag
- [x] Create `tests/test_cli.py`
  - [x] Test `extract` with mocked pipeline (JSON output)
  - [x] Test `extract` with `--format markdown`
  - [x] Test `extract` with `--output` file
  - [x] Test exit codes for various failure modes
  - [x] Test `--help` output
  - [x] Test URL parsing (full URL, short URL, plain ID)
- [x] Add MPL-2.0 header to all new source files
- [x] Verify: `yt-factify extract <video-id> --model <model>` produces valid JSON output (with mocked deps)

### Story D.b: v0.3.2 Library API [Done]

Expose the public Python API.

- [x] Update `src/yt_factify/__init__.py`
  - [x] Re-export: `extract`, `ExtractionResult`, `AppConfig`, `render_json`, `render_markdown`, `PipelineError`
  - [x] `extract()` — async convenience function wrapping `run_pipeline()`
  - [x] `extract_sync()` — sync wrapper for non-async callers
- [x] Add library API usage examples to module docstring
- [x] Create `tests/test_library_api.py`
  - [x] Test `await extract(video_id)` returns `ExtractionResult`
  - [x] Test with custom `AppConfig`
  - [x] Test with default config
  - [x] Test `extract_sync()` returns `ExtractionResult`
  - [x] Test error propagation
  - [x] Test re-exports are importable
  - [x] Test rendering from public API
- [x] Add MPL-2.0 header to all new/modified source files
- [x] Verify: library API works as documented in tech spec

---

## Phase E: Testing & Quality

### Story E.a: v0.4.1 Golden Tests & Edge Cases [Done]

Comprehensive test coverage with golden fixtures and edge cases.

- [x] Create at least 3 golden test fixtures:
  - [x] Short news clip transcript (`short_news_clip.json`)
  - [x] Long interview transcript (`long_interview.json` — existing)
  - [x] Opinion/editorial transcript (`opinion_editorial.json`)
- [x] Create `tests/test_golden_and_edge_cases.py` with golden + edge case tests
  - [x] Golden: news clip pipeline, classification, audit, evidence, topics
  - [x] Golden: interview pipeline, credibility, URL
  - [x] Golden: opinion/editorial pipeline, bias profile, JSON roundtrip
- [x] Add edge case tests:
  - [x] Empty transcript raises PipelineError
  - [x] Single-segment transcript succeeds
  - [x] Transcript with no identifiable facts → empty items
  - [x] Malformed LLM response → extraction failure propagates
  - [x] All quotes fail verification → empty items
  - [x] Very long transcript (>2 hours, 500 segments) succeeds
- [x] Verify: ≥80% line coverage — achieved **96%** overall, core modules 94–100%
- [x] Add MPL-2.0 header to all new source files

### Story E.b: Type Checking & Linting Cleanup [Done]

Ensure full type safety and code quality.

- [x] Run `mypy --strict` on all source files — **0 errors**
- [x] Run `ruff check` — **0 errors**
- [x] Run `ruff format` — **23 files reformatted**, all now consistent
- [x] All public functions have docstrings
- [x] Verify: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` all pass cleanly

---

## Phase F: Documentation & Release

### Story F.a: v0.5.1 README & Documentation [Done]

Project documentation for users and contributors.

- [x] Create `README.md` with:
  - [x] Project description and purpose
  - [x] Installation instructions
  - [x] Quick start (CLI and library examples — async, sync, rendering)
  - [x] Configuration reference (config file, env vars, CLI options, exit codes)
  - [x] Belief system module authoring guide
  - [x] Output format documentation (JSON structure, Markdown sections)
  - [x] Development setup instructions (tests, linting, type checking)
  - [x] Project structure overview
  - [x] License notice
- [x] Update `src/yt_factify/modules/README.md` with:
  - [x] Built-in modules list
  - [x] Copy-paste template
  - [x] Tips for effective modules
  - [x] Validation rules
  - [x] Loading examples (CLI, config, library API)
- [x] Verify: README examples are accurate and match actual CLI/API

### Story F.b: v0.5.2 Release Polish [Done]

Final checks and prototype release.

- [x] Bump version to `0.5.2` in `pyproject.toml` and `__init__.py`
- [x] Create `CHANGELOG.md` summarizing all changes from v0.1.1 to v0.5.2
- [x] Run full test suite: 276 passed, 96% coverage
- [x] Run linter and type checker: `ruff check`, `ruff format`, `mypy --strict` — all clean
- [x] Verify all acceptance criteria from `features.md` are met:
  - [x] `yt-factify extract <url>` produces valid JSON (tested via CLI tests)
  - [x] Direct quotes are verified substrings (validation module + tests)
  - [x] All items have transcript evidence (model constraints + tests)
  - [x] Video categorization and bias profile present (classification module + tests)
  - [x] Belief system modules loadable and functional (3 built-in, custom dir support)
  - [x] Library API works with typed models (`extract()`, `extract_sync()`, re-exports)
  - [x] Audit bundle complete (model_id, version, hashes, timestamps)
  - [x] ≥80% test coverage — achieved **96%**
  - [x] Errors handled gracefully (exit codes, PipelineError, structured logging)
  - [x] Config precedence correct (CLI > env > file > defaults)
- [x] Tag release (manual step)

### Story F.c: v0.5.3 Rate-Limit Resilience [Done]

Centralized LLM call helper with robust rate-limit handling.

- [x] Create shared `src/yt_factify/llm.py` module
  - [x] `llm_completion()` async helper wrapping `litellm.acompletion`
  - [x] Exponential backoff on rate-limit errors (5s → 10s → 20s → … → 120s cap)
  - [x] Up to 6 rate-limit retries (independent of parse/transient retries)
  - [x] Retry-after hint parsing from provider error messages
  - [x] Structured logging at each retry and exhaustion point
- [x] Integrate `llm_completion()` into all LLM call sites:
  - [x] `_extract_segment` in `extraction.py`
  - [x] `classify_video` in `classification.py`
  - [x] `assess_credibility` in `classification.py`
  - [x] `cluster_topic_threads` in `topics.py`
- [x] Remove direct `import litellm` from `extraction.py`, `classification.py`, `topics.py`
- [x] Update all test mocks to target `yt_factify.llm.litellm`
- [x] Bump version to `0.5.3`
- [x] Update `CHANGELOG.md`
- [x] Verify: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` — all pass (276 tests)

---

## Phase G: CI/CD

### Story G.a: v0.6.1 GitHub Actions CI [Planned]

Set up continuous integration with GitHub Actions.

- [ ] Create `.github/workflows/ci.yml`
  - [ ] Trigger on push to `main` and on pull requests
  - [ ] Matrix: Python 3.14 on ubuntu-latest
  - [ ] Steps: checkout, install dependencies, `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest --cov`
  - [ ] Upload coverage report to Codecov (or Coveralls)
  - [ ] Fail the workflow if coverage drops below 80%
- [ ] Add Codecov (or Coveralls) integration
  - [ ] Create account and link repository
  - [ ] Add `CODECOV_TOKEN` to repository secrets (if required)
  - [ ] Add `codecov.yml` config with coverage threshold
- [ ] Update `README.md` badges
  - [ ] Replace static coverage badge with dynamic Codecov/Coveralls badge
  - [ ] Add CI status badge (passing/failing)
- [ ] Verify: push triggers workflow, badges update automatically

### Story G.b: v0.6.2 Release Automation [Planned]

Automate version tagging and release publishing.

- [ ] Create `.github/workflows/release.yml`
  - [ ] Trigger on version tag push (`v*`)
  - [ ] Run full test suite before publishing
  - [ ] Build sdist and wheel via `python -m build`
  - [ ] Publish to PyPI via `twine` (or trusted publisher)
  - [ ] Create GitHub Release with changelog entry
- [ ] Add `PYPI_TOKEN` to repository secrets
- [ ] Add `Makefile` with convenience targets:
  - [ ] `make test` — run pytest with coverage
  - [ ] `make lint` — ruff check + ruff format --check
  - [ ] `make typecheck` — mypy --strict
  - [ ] `make ci` — lint + typecheck + test (mirrors CI)
- [ ] Verify: tagging `v0.6.2` triggers build, test, and publish
