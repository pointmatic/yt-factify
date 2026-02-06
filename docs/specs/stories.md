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

### Story B.f: v0.1.6 Belief/Value System Modules [Planned]

Module loading and integration with extraction/credibility.

- [ ] Create `src/yt_factify/belief_systems.py`
  - [ ] `load_belief_modules()` — loads JSON files from a directory, validates against schema
  - [ ] `get_builtin_modules()` — returns built-in default modules
  - [ ] Invalid files logged and skipped
- [ ] Create `src/yt_factify/modules/README.md` explaining module authoring
- [ ] Create 2–3 built-in module JSON files (e.g., `scientific_materialism.json`, `religious_theism.json`, `political_progressivism.json`)
- [ ] Create `tests/test_belief_systems.py`
  - [ ] Test loading valid modules
  - [ ] Test invalid module file is skipped with warning
  - [ ] Test built-in modules load correctly
  - [ ] Test module schema validation
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: all belief system tests pass

### Story B.g: v0.1.7 Topic Threading [Planned]

Cluster extracted items into topic threads to capture conversational structure.

- [ ] Add `TopicTimeSpan` and `TopicThread` models to `src/yt_factify/models.py`
- [ ] Add `topic_threads` field to `ExtractionResult`
- [ ] Create `src/yt_factify/prompts/topics.py`
  - [ ] System prompt for topic clustering (item grouping by subject)
  - [ ] `build_topic_threading_messages()` accepting items list
- [ ] Create `src/yt_factify/topics.py`
  - [ ] `cluster_topic_threads()` — async, calls LLM to cluster items by topic
  - [ ] Parses LLM response, validates item IDs against input
  - [ ] Derives timeline from `transcript_evidence` timestamps of member items
  - [ ] Retries once on malformed JSON, raises `TopicClusteringError` on failure
  - [ ] Handles edge case: very few items (< 3) returns empty list
- [ ] Create `tests/fixtures/llm_responses/` topic threading response fixture
- [ ] Create `tests/test_topics.py`
  - [ ] Test topic clustering with mocked LLM
  - [ ] Test timeline derivation from item timestamps
  - [ ] Test unknown item IDs are skipped
  - [ ] Test malformed JSON handling (retry, then error)
  - [ ] Test few-items edge case
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: all topic threading tests pass

---

## Phase C: Pipeline & Orchestration

### Story C.a: v0.2.1 Pipeline Orchestration [Planned]

Wire all services together into the full extraction pipeline.

- [ ] Create `src/yt_factify/pipeline.py`
  - [ ] `run_pipeline()` — async, orchestrates the full flow:
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
  - [ ] Proper error handling at each stage with informative messages
- [ ] Create `tests/test_pipeline.py`
  - [ ] Test full pipeline with fixture transcript and mocked LLM
  - [ ] Test pipeline error handling (transcript fetch failure, LLM failure, validation failure)
  - [ ] Test audit bundle is complete
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: all pipeline tests pass

### Story C.b: v0.2.2 Output Rendering [Planned]

JSON and Markdown output rendering.

- [ ] Create `src/yt_factify/rendering.py`
  - [ ] `render_json()` — serialize `ExtractionResult` to JSON string
  - [ ] `render_markdown()` — human-readable Markdown summary with sections:
    - Video Info, Topic Overview, Key Facts, Direct Quotes, Opinions & Perspectives, Unverified Claims, Predictions, Belief System Notes
  - [ ] Atomic file writes (write to temp, then rename)
- [ ] Create `tests/fixtures/expected_outputs/` with golden output files
- [ ] Create `tests/test_rendering.py`
  - [ ] Test JSON output matches schema
  - [ ] Test Markdown output contains expected sections
  - [ ] Test atomic write (file exists only after success)
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: all rendering tests pass

---

## Phase D: CLI & Library API

### Story D.a: v0.3.1 CLI Extract Command [Planned]

Wire the pipeline into the CLI `extract` command.

- [ ] Update `src/yt_factify/cli.py`
  - [ ] Implement `extract` command: parse video URL/ID, load config, run pipeline, render output
  - [ ] Add all CLI flags from tech spec (`--model`, `--format`, `--output`, `--modules-dir`, etc.)
  - [ ] Progress indicators via Rich (transcript fetch, extraction, validation)
  - [ ] Exit codes: 0 (success), 1 (general), 2 (transcript), 3 (LLM), 4 (validation)
  - [ ] Write output to stdout or file per `--output` flag
- [ ] Create `tests/test_cli.py`
  - [ ] Test `extract` with mocked pipeline (JSON output)
  - [ ] Test `extract` with `--format markdown`
  - [ ] Test `extract` with `--output` file
  - [ ] Test exit codes for various failure modes
  - [ ] Test `--help` output
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: `yt-factify extract <video-id> --model <model>` produces valid JSON output (with mocked deps)

### Story D.b: v0.3.2 Library API [Planned]

Expose the public Python API.

- [ ] Update `src/yt_factify/__init__.py`
  - [ ] Re-export: `extract`, `ExtractionResult`, `AppConfig`, `render_json`, `render_markdown`
  - [ ] `extract()` — async convenience function wrapping `run_pipeline()`
  - [ ] Optional sync wrapper for non-async callers
- [ ] Add library API usage examples to docstrings
- [ ] Create integration test for library API
  - [ ] Test `await extract(video_id)` returns `ExtractionResult`
  - [ ] Test with custom `AppConfig`
- [ ] Add MPL-2.0 header to all new/modified source files
- [ ] Verify: library API works as documented in tech spec

---

## Phase E: Testing & Quality

### Story E.a: v0.4.1 Golden Tests & Edge Cases [Planned]

Comprehensive test coverage with golden fixtures and edge cases.

- [ ] Create at least 3 golden test fixtures:
  - [ ] Short news clip transcript
  - [ ] Long interview transcript (>30 minutes)
  - [ ] Opinion/editorial transcript with strong bias
- [ ] Create corresponding mocked LLM responses and expected outputs
- [ ] Add golden tests to `tests/test_pipeline.py`
  - [ ] Compare pipeline output against expected output (ignoring variable fields like timestamps)
- [ ] Add edge case tests across modules:
  - [ ] Empty transcript
  - [ ] Single-segment transcript
  - [ ] Transcript with no identifiable facts
  - [ ] Malformed LLM response (partial JSON, wrong schema)
  - [ ] All quotes fail verification
  - [ ] Very long transcript (>2 hours simulated)
- [ ] Verify: ≥80% line coverage on core modules (`transcript`, `extraction`, `validation`, `classification`, `pipeline`)
- [ ] Add MPL-2.0 header to all new source files

### Story E.b: Type Checking & Linting Cleanup [Planned]

Ensure full type safety and code quality.

- [ ] Run `mypy --strict` on all source files and fix any errors
- [ ] Run `ruff check` and `ruff format` and fix any issues
- [ ] Ensure all public functions have docstrings
- [ ] Verify: `make lint`, `make typecheck`, `make test` all pass cleanly

---

## Phase F: Documentation & Release

### Story F.a: v0.5.1 README & Documentation [Planned]

Project documentation for users and contributors.

- [ ] Create `README.md` with:
  - [ ] Project description and purpose
  - [ ] Installation instructions
  - [ ] Quick start (CLI and library examples)
  - [ ] Configuration reference
  - [ ] Belief system module authoring guide
  - [ ] Output format documentation
  - [ ] Development setup instructions
  - [ ] License notice
- [ ] Update `src/yt_factify/modules/README.md` with complete module authoring guide and template
- [ ] Add MPL-2.0 header to all new source files
- [ ] Verify: README examples are accurate and runnable

### Story F.b: v0.5.2 Release Polish [Planned]

Final checks and prototype release.

- [ ] Bump version to `0.5.2` in `pyproject.toml` and `__init__.py`
- [ ] Create `CHANGELOG.md` summarizing all changes from v0.1.0 to v1.0.0
- [ ] Run full test suite: `make test`
- [ ] Run linter and type checker: `make lint`, `make typecheck`
- [ ] Verify all acceptance criteria from `features.md` are met:
  - [ ] `yt-factify extract <url>` produces valid JSON
  - [ ] Direct quotes are verified substrings
  - [ ] All items have transcript evidence
  - [ ] Video categorization and bias profile present
  - [ ] Belief system modules loadable and functional
  - [ ] Library API works with typed models
  - [ ] Audit bundle complete
  - [ ] ≥80% test coverage
  - [ ] Errors handled gracefully
  - [ ] Config precedence correct
- [ ] Tag release
