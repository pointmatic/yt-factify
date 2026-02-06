# tech_spec.md — yt-factify (Python)

This document defines **how** yt-factify is built — architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns. For requirements and scope, see [`features.md`](features.md). For the implementation plan, see [`stories.md`](stories.md).

---

## Runtime & Tooling

| Concern | Choice |
|---------|--------|
| Language | Python 3.14+ |
| Package manager | pip with `pyproject.toml` (PEP 621) |
| Virtual env | venv (managed via direnv/pyve) |
| Linter / formatter | Ruff |
| Type checker | mypy (strict mode) |
| Test runner | pytest |
| Coverage | pytest-cov (target ≥80% on core modules) |
| Task runner | Makefile or just scripts in `pyproject.toml` |

---

## Dependencies

### Runtime

| Package | Version | Purpose |
|---------|---------|---------|
| `yt-fetch` | ≥0.1.0 | Fetch YouTube transcripts and metadata |
| `litellm` | ≥1.0 | Provider-agnostic LLM API access (OpenAI, Anthropic, Gemini, local, etc.) |
| `pydantic` | ≥2.0 | Data models, validation, JSON schema generation |
| `click` | ≥8.0 | CLI framework |
| `rich` | ≥13.0 | CLI progress indicators, formatted output |
| `tomli` | ≥2.0 | TOML config file parsing (stdlib `tomllib` on 3.11+, but explicit for clarity) |
| `structlog` | ≥24.0 | Structured logging |

### Development

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | ≥8.0 | Test runner |
| `pytest-cov` | ≥5.0 | Coverage reporting |
| `ruff` | ≥0.8 | Linting and formatting |
| `mypy` | ≥1.13 | Static type checking |
| `pytest-asyncio` | ≥0.24 | Async test support (for concurrent LLM calls) |

### System

| Dependency | Purpose |
|------------|---------|
| Python 3.14+ | Runtime |

---

## Package Structure

```
yt-factify/
├── LICENSE                          # MPL-2.0
├── README.md                        # Project overview, install, usage
├── pyproject.toml                   # Package metadata, deps, tool config
├── Makefile                         # Dev tasks: lint, test, format, typecheck
├── docs/
│   ├── guides/
│   │   └── project_guide.md         # LLM project creation guide
│   └── specs/
│       ├── concept.md               # Original concept
│       ├── loose_feature_and_tech_ideas.md
│       ├── features.md              # Requirements (what)
│       ├── tech_spec.md             # Architecture (how) — this file
│       └── stories.md               # Implementation plan
├── src/
│   └── yt_factify/
│       ├── __init__.py              # Public API re-exports, __version__
│       ├── __main__.py              # python -m yt_factify entry point
│       ├── cli.py                   # Click CLI definition
│       ├── config.py                # Configuration loading (CLI > env > file > defaults)
│       ├── models.py                # All Pydantic data models
│       ├── transcript.py            # Transcript ingestion, normalization, segmentation, hashing
│       ├── extraction.py            # LLM-based item extraction (prompt building, response parsing)
│       ├── validation.py            # Quote verification, schema validation, timestamp checks
│       ├── classification.py        # Video categorization, bias/slant detection, credibility
│       ├── topics.py                # Topic thread clustering (post-extraction)
│       ├── belief_systems.py        # Belief/value system module loading and management
│       ├── rendering.py             # Output rendering (JSON, Markdown)
│       ├── pipeline.py              # Orchestrates the full extraction pipeline
│       ├── prompts/                  # Prompt template directory
│       │   ├── __init__.py          # Prompt loading utilities
│       │   ├── extraction.py        # Item extraction prompt templates
│       │   ├── classification.py    # Categorization + bias prompt templates
│       │   ├── credibility.py       # Credibility assessment prompt templates
│       │   └── topics.py            # Topic threading prompt templates
│       ├── modules/                  # Built-in belief/value system modules
│       │   └── README.md            # How to author new modules
│       └── logging.py               # Structured logging setup
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── fixtures/                    # Test fixture data
│   │   ├── transcripts/             # Sample transcript JSON files
│   │   ├── llm_responses/           # Mocked LLM response JSON files
│   │   └── expected_outputs/        # Golden test expected outputs
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_transcript.py
│   ├── test_extraction.py
│   ├── test_validation.py
│   ├── test_classification.py
│   ├── test_topics.py
│   ├── test_belief_systems.py
│   ├── test_rendering.py
│   ├── test_pipeline.py
│   └── test_cli.py
└── .gitignore
```

---

## Key Component Design

### `transcript.py` — Transcript Ingestion & Segmentation

```python
def fetch_transcript(video_id: str, config: AppConfig) -> RawTranscript:
    """Fetch transcript via yt-fetch and return raw data.

    Calls yt_fetch.fetch_video() to retrieve transcript segments.
    Raises TranscriptFetchError if the video or transcript is unavailable.
    """

def normalize_transcript(raw: RawTranscript) -> NormalizedTranscript:
    """Normalize raw transcript into canonical format.

    - Strips extraneous whitespace.
    - Normalizes Unicode.
    - Computes SHA-256 hash of the full normalized text.
    - Computes per-segment hashes.
    """

def segment_transcript(
    transcript: NormalizedTranscript,
    target_seconds: int = 45,
) -> list[TranscriptSegment]:
    """Split transcript into segments for LLM processing.

    Targets approximately `target_seconds` per segment.
    Respects sentence boundaries where possible.
    Each segment gets a unique hash.
    """
```

**Edge cases:**
- Empty transcript → raise `EmptyTranscriptError`.
- Transcript with no timestamps → treat as single segment with `start_ms=0`.
- Very short video (< target_seconds) → single segment.

### `extraction.py` — LLM-Based Item Extraction

```python
async def extract_items(
    segments: list[TranscriptSegment],
    categories: list[VideoCategory],
    belief_modules: list[BeliefSystemModule],
    config: AppConfig,
) -> list[ExtractedItem]:
    """Extract structured items from transcript segments via LLM.

    For each segment (or batch of segments), builds a prompt and calls
    the LLM via litellm.acompletion(). Parses the JSON response and
    validates against the item schema.

    Supports concurrent extraction with configurable parallelism.
    """

def build_extraction_prompt(
    segment: TranscriptSegment,
    categories: list[VideoCategory],
    belief_modules: list[BeliefSystemModule],
) -> list[dict]:
    """Build the chat messages for item extraction.

    Returns a list of message dicts (system, user) suitable for
    litellm.completion().
    """
```

**Edge cases:**
- LLM returns malformed JSON → retry once, then raise `ExtractionError`.
- LLM returns items not matching schema → reject invalid items, log warnings.
- Empty segment → skip with a log message.

### `validation.py` — Post-Extraction Validation

```python
def validate_items(
    items: list[ExtractedItem],
    transcript: NormalizedTranscript,
    config: AppConfig,
) -> ValidationResult:
    """Validate extracted items against the transcript.

    Checks:
    - direct_quote text is an exact substring of transcript.
    - Timestamp bounds are valid.
    - All required fields are present and well-typed (via Pydantic).

    Returns ValidationResult with accepted items, rejected items,
    and downgraded items (depending on quote_mismatch config).
    """

def verify_quote(
    quote_text: str,
    transcript: NormalizedTranscript,
    start_ms: int,
    end_ms: int,
) -> bool:
    """Check that quote_text is an exact substring within the given time range."""
```

### `classification.py` — Video Categorization & Bias Detection

```python
async def classify_video(
    transcript: NormalizedTranscript,
    config: AppConfig,
) -> VideoClassification:
    """Classify video category and detect bias/slant via LLM.

    For very long transcripts, uses a representative sample
    (first, middle, last segments + random sample).
    """

async def assess_credibility(
    items: list[ExtractedItem],
    belief_modules: list[BeliefSystemModule],
    config: AppConfig,
) -> list[ExtractedItem]:
    """Add credibility assessments to extracted items via LLM.

    Returns items with credibility field populated.
    """
```

### `topics.py` — Topic Thread Clustering

```python
async def cluster_topic_threads(
    items: list[ExtractedItem],
    config: AppConfig,
) -> list[TopicThread]:
    """Cluster extracted items into topic threads via LLM.

    Receives all validated extracted items and asks the LLM to identify
    recurring topics and group items by subject. Items may belong to
    multiple threads. The timeline for each thread is derived from the
    transcript_evidence timestamps of its member items.

    For v1, threads are a flat list (no hierarchical sub-topics).
    """
```

**Edge cases:**
- Very few items (< 3) → return a single thread or empty list.
- LLM returns item IDs not in the input → skip with a warning.
- LLM returns malformed JSON → retry once, then raise `TopicClusteringError`.

### `belief_systems.py` — Module Loading

```python
def load_belief_modules(modules_dir: Path) -> list[BeliefSystemModule]:
    """Load belief/value system module definitions from JSON files.

    Each file must conform to the BeliefSystemModule schema.
    Invalid files are logged and skipped.
    """

def get_builtin_modules() -> list[BeliefSystemModule]:
    """Return the built-in set of belief/value system modules."""
```

### `pipeline.py` — Orchestration

```python
async def run_pipeline(
    video_id: str,
    config: AppConfig,
) -> ExtractionResult:
    """Run the full yt-factify extraction pipeline.

    Steps:
    1. Fetch and normalize transcript.
    2. Segment transcript.
    3. Classify video (category + bias).
    4. Load belief/value system modules.
    5. Extract items from segments (concurrent).
    6. Validate items (quote verification, timestamp checks).
    7. Assess credibility of validated items.
    8. Cluster topic threads from validated items.
    9. Build audit bundle.
    10. Return ExtractionResult.
    """
```

### `rendering.py` — Output Rendering

```python
def render_json(result: ExtractionResult) -> str:
    """Render ExtractionResult as JSON string."""

def render_markdown(result: ExtractionResult) -> str:
    """Render ExtractionResult as human-readable Markdown summary."""
```

### `config.py` — Configuration

```python
def load_config(
    cli_overrides: dict | None = None,
    config_path: Path | None = None,
) -> AppConfig:
    """Load configuration with precedence: CLI > env > file > defaults.

    Reads environment variables prefixed with YT_FACTIFY_.
    Reads TOML config file if it exists.
    Merges with CLI overrides.
    Validates the final config via Pydantic.
    """
```

### `cli.py` — CLI Interface

```python
@click.group()
def cli() -> None:
    """yt-factify: Extract facts and quotes from YouTube videos."""

@cli.command()
@click.argument("video", type=str)
@click.option("--model", help="LLM model identifier")
@click.option("--format", "output_format", type=click.Choice(["json", "markdown"]), default="json")
@click.option("--output", "-o", type=click.Path(), help="Output file path (default: stdout)")
@click.option("--config", "config_path", type=click.Path(exists=True), help="Config file path")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), default="INFO")
@click.option("--modules-dir", type=click.Path(exists=True), help="Belief system modules directory")
@click.option("--quote-mismatch", type=click.Choice(["reject", "downgrade"]), default="reject")
@click.option("--segment-seconds", type=int, default=45)
@click.option("--api-base", help="LLM API base URL")
@click.option("--api-key", help="LLM API key (prefer env var YT_FACTIFY_API_KEY)")
@click.option("--temperature", type=float, default=0.0)
def extract(video: str, **kwargs) -> None:
    """Extract facts, quotes, and claims from a YouTube video."""

@cli.command()
def version() -> None:
    """Print yt-factify version."""
```

---

## Data Models

All models are defined in `models.py` using Pydantic v2.

### Core Enums

```python
from enum import StrEnum

class ItemType(StrEnum):
    DIRECT_QUOTE = "direct_quote"
    TRANSCRIPT_FACT = "transcript_fact"
    GENERAL_KNOWLEDGE = "general_knowledge"
    SPEAKER_OPINION = "speaker_opinion"
    UNVERIFIED_CLAIM = "unverified_claim"
    PREDICTION = "prediction"

class CredibilityLabel(StrEnum):
    WELL_ESTABLISHED = "well_established"
    CREDIBLE = "credible"
    DISPUTED = "disputed"
    DUBIOUS = "dubious"
    UNASSESSABLE = "unassessable"

class VideoCategory(StrEnum):
    NEWS = "news"
    ENTERTAINMENT = "entertainment"
    MUSIC_VIDEO = "music_video"
    COMEDY_SATIRE = "comedy_satire"
    INTERVIEW = "interview"
    DOCUMENTARY = "documentary"
    TUTORIAL = "tutorial"
    OPINION_EDITORIAL = "opinion_editorial"
    POLITICAL_SPEECH = "political_speech"
    PANEL_DISCUSSION = "panel_discussion"
    OTHER = "other"

class QuoteMismatchBehavior(StrEnum):
    REJECT = "reject"
    DOWNGRADE = "downgrade"
```

### Transcript Models

```python
from pydantic import BaseModel, Field
from datetime import datetime

class TranscriptSegmentRaw(BaseModel):
    """A single segment from yt-fetch transcript output."""
    text: str
    start_ms: int
    end_ms: int

class RawTranscript(BaseModel):
    """Raw transcript as received from yt-fetch."""
    video_id: str
    segments: list[TranscriptSegmentRaw]
    language: str | None = None

class NormalizedSegment(BaseModel):
    """A normalized transcript segment with hash."""
    text: str
    start_ms: int
    end_ms: int
    hash: str  # SHA-256 of normalized text

class NormalizedTranscript(BaseModel):
    """Normalized transcript with full-text hash."""
    video_id: str
    full_text: str
    hash: str  # SHA-256 of full normalized text
    segments: list[NormalizedSegment]
    language: str | None = None

class TranscriptSegment(BaseModel):
    """A segment prepared for LLM processing (may span multiple NormalizedSegments)."""
    text: str
    start_ms: int
    end_ms: int
    hash: str
    source_segment_indices: list[int]
```

### Extraction Models

```python
class TranscriptEvidence(BaseModel):
    """Links an extracted item to its transcript source."""
    video_id: str
    start_ms: int
    end_ms: int
    text: str  # Exact transcript span

class BeliefSystemFlag(BaseModel):
    """Flags an item as relying on a specific worldview."""
    module_label: str
    note: str

class CredibilityAssessment(BaseModel):
    """Credibility assessment for an extracted item."""
    label: CredibilityLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    relevant_belief_systems: list[str] = Field(default_factory=list)

class ExtractedItem(BaseModel):
    """A single extracted item (fact, quote, opinion, etc.)."""
    id: str
    type: ItemType
    content: str
    speaker: str | None = None
    transcript_evidence: TranscriptEvidence
    credibility: CredibilityAssessment | None = None
    belief_system_flags: list[BeliefSystemFlag] = Field(default_factory=list)
```

### Classification Models

```python
class BiasProfile(BaseModel):
    """Bias/slant assessment for a video."""
    primary_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    implicit_bias_notes: list[str] = Field(default_factory=list)

class VideoClassification(BaseModel):
    """Video categorization and bias profile."""
    categories: list[VideoCategory]
    bias_profile: BiasProfile
```

### Belief System Module

```python
class BeliefSystemModule(BaseModel):
    """A pluggable worldview/belief system definition."""
    label: str
    display_name: str
    description: str
    core_assumptions: list[str]
    example_claims: list[str] = Field(default_factory=list)
```

### Topic Thread Models

```python
class TopicTimeSpan(BaseModel):
    """A time range where a topic appears in the video."""
    start_ms: int
    end_ms: int

class TopicThread(BaseModel):
    """A named cluster of extracted items sharing a common subject."""
    label: str
    display_name: str
    summary: str
    item_ids: list[str]
    timeline: list[TopicTimeSpan] = Field(default_factory=list)
```

### Output Models

```python
class VideoInfo(BaseModel):
    """Video metadata in the output."""
    video_id: str
    title: str | None = None
    url: str
    transcript_hash: str
    fetched_at: datetime

class AuditBundle(BaseModel):
    """Audit trail for traceability."""
    model_id: str
    model_version: str | None = None
    prompt_templates_hash: str
    processing_timestamp: datetime
    segment_hashes: list[str]
    yt_factify_version: str

class ValidationResult(BaseModel):
    """Result of post-extraction validation."""
    accepted: list[ExtractedItem]
    rejected: list[ExtractedItem] = Field(default_factory=list)
    downgraded: list[ExtractedItem] = Field(default_factory=list)

class ExtractionResult(BaseModel):
    """Top-level output of the yt-factify pipeline."""
    video: VideoInfo
    classification: VideoClassification
    items: list[ExtractedItem]
    topic_threads: list[TopicThread] = Field(default_factory=list)
    audit: AuditBundle
```

### Configuration Model

```python
class AppConfig(BaseModel):
    """Application configuration."""
    model: str
    api_base: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    output_format: str = "json"
    output_path: str | None = None
    config_path: str | None = None
    log_level: str = "INFO"
    modules_dir: str | None = None
    quote_mismatch: QuoteMismatchBehavior = QuoteMismatchBehavior.REJECT
    segment_seconds: int = 45
    max_concurrent_requests: int = 3
    max_retries: int = 3
```

---

## Configuration

Configuration is loaded by `config.py` with the following precedence (highest first):

1. **CLI flags** — passed as a dict of overrides.
2. **Environment variables** — prefixed with `YT_FACTIFY_` (e.g., `YT_FACTIFY_MODEL`, `YT_FACTIFY_API_KEY`).
3. **Config file** — TOML format at `~/.config/yt-factify/config.toml` (or path specified by `--config`).
4. **Built-in defaults** — defined in `AppConfig` model.

Example config file (`config.toml`):

```toml
model = "gpt-4o"
api_base = "https://api.openai.com/v1"
temperature = 0.0
log_level = "INFO"
segment_seconds = 45
quote_mismatch = "reject"
max_concurrent_requests = 3
```

---

## CLI Design

### Subcommands

| Command | Description |
|---------|-------------|
| `yt-factify extract <video>` | Run the full extraction pipeline on a video |
| `yt-factify version` | Print version and exit |

### Shared Flags

All flags for `extract` are listed in the CLI Interface section above.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (config, unexpected failure) |
| 2 | Transcript fetch failed |
| 3 | LLM extraction failed (malformed response, schema violation) |
| 4 | Validation failed (quote mismatches in strict mode) |

---

## Library API

The public API is exposed from `yt_factify.__init__`:

```python
from yt_factify import extract, ExtractionResult, AppConfig

# Minimal usage
result: ExtractionResult = await extract("dQw4w9WgXcQ")

# With configuration
config = AppConfig(model="gpt-4o", api_key="sk-...")
result = await extract("dQw4w9WgXcQ", config=config)

# Access structured data
for item in result.items:
    print(f"[{item.type}] {item.content}")
    print(f"  Evidence: {item.transcript_evidence.text}")
    print(f"  Credibility: {item.credibility.label}")

# Render as markdown
from yt_factify import render_markdown
print(render_markdown(result))
```

The library API is async (`async def extract(...)`) to support concurrent LLM calls. A synchronous wrapper may be provided for convenience.

---

## Cross-Cutting Concerns

### LLM Access (litellm)

All LLM calls go through `litellm.acompletion()`, which provides:
- **Provider agnosticism** — switch between OpenAI, Anthropic, Gemini, local models, etc. by changing the model string.
- **Structured output** — use `response_format` parameter to request JSON output where supported; fall back to prompt-based JSON extraction.
- **Retry with backoff** — litellm has built-in retry support; additionally, yt-factify retries on schema validation failures.

### Retry Strategy

| Failure | Retry? | Strategy |
|---------|--------|----------|
| Transcript fetch (network) | Yes | Handled by yt-fetch (configurable retries) |
| LLM API error (429, 500, 503) | Yes | litellm built-in retry + exponential backoff |
| LLM malformed JSON | Yes | 1 retry with same prompt |
| LLM schema validation failure | Yes | 1 retry with error feedback in prompt |
| Quote verification failure | No | Reject or downgrade per config |

### Rate Limiting

- LLM API rate limits are respected via litellm's built-in rate limiting.
- Concurrent extraction is capped by `max_concurrent_requests` (default: 3) using `asyncio.Semaphore`.

### Logging

- Uses `structlog` for structured, JSON-compatible log output.
- Log levels: DEBUG, INFO, WARNING, ERROR.
- Key events logged: pipeline start/end, transcript fetch, segmentation, each LLM call, validation results, output rendering.
- API keys and secrets are never logged.

### Caching

- **Transcript caching** — handled by yt-fetch (skips already-fetched data).
- **LLM result caching** — optional, keyed by `(segment_hash, model_id, prompt_hash)`. Stored as JSON files in a cache directory. Disabled by default.

### Atomic Writes

- Output files are written atomically: write to a temp file, then rename. This prevents partial output on failure.

### Hashing

- All hashes use SHA-256.
- `transcript.hash` = SHA-256 of the full normalized transcript text.
- `segment.hash` = SHA-256 of the individual segment's normalized text.
- `audit.prompt_templates_hash` = SHA-256 of the concatenated prompt template strings.

---

## Testing Strategy

### Unit Tests

| Module | What's tested |
|--------|---------------|
| `test_models.py` | Pydantic model validation, serialization, edge cases |
| `test_config.py` | Config loading, precedence, env var parsing, defaults |
| `test_transcript.py` | Normalization, segmentation, hashing, edge cases |
| `test_validation.py` | Quote verification, timestamp bounds, schema checks |
| `test_belief_systems.py` | Module loading, validation, built-in modules |
| `test_rendering.py` | JSON and Markdown output rendering |

### Integration Tests

| Test | What's tested |
|------|---------------|
| `test_extraction.py` | Prompt building + mocked LLM response parsing |
| `test_classification.py` | Classification + credibility with mocked LLM |
| `test_topics.py` | Topic thread clustering with mocked LLM |
| `test_pipeline.py` | Full pipeline with fixture transcripts and mocked LLM |
| `test_cli.py` | CLI invocation, flag parsing, output format, exit codes |

### Golden Tests

- Fixture transcripts in `tests/fixtures/transcripts/`.
- Mocked LLM responses in `tests/fixtures/llm_responses/`.
- Expected outputs in `tests/fixtures/expected_outputs/`.
- Golden tests compare pipeline output against expected output (ignoring timestamps and hashes that vary).

### Test Approach

- LLM calls are mocked in all tests (no real API calls in CI).
- `yt-fetch` calls are mocked with fixture transcript data.
- Integration tests verify the full pipeline wiring with mocked external dependencies.
