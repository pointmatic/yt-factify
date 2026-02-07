# yt-factify

Extract auditable facts, quotes, topics, and biases from YouTube transcripts.

[![License: MPL-2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://mozilla.org/MPL/2.0/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Coverage: 96%](https://img.shields.io/badge/coverage-96%25-brightgreen.svg)](https://github.com/pointmatic/yt-factify)

**yt-factify** uses LLMs as a *proposal engine* to extract facts, direct quotes, opinions, claims, and predictions from YouTube transcripts — then validates every item against the original transcript for full auditability.

## Key Principles

- **Everything is anchored** — every fact and quote is traceable to a specific transcript span
- **LLM as proposal engine** — the LLM proposes items; validation confirms them
- **Bias-aware** — videos are classified by category and bias profile
- **Belief system modules** — flag claims that depend on specific worldviews
- **Rate-limit resilient** — adaptive throttle with stochastic jitter decelerates on API rate limits and reaccelerates after cooling; configurable initial and max concurrency via `--initial-concurrency` and `--max-concurrency`
- **Auditable** — every extraction includes a full audit bundle

## Installation

```bash
pip install yt-factify
```

Or install from source:

```bash
git clone https://github.com/pointmatic/yt-factify.git
cd yt-factify
pip install -e ".[dev]"
```

### Requirements

- Python 3.14+
- An LLM API key (e.g., OpenAI, Anthropic, or any provider supported by [litellm](https://github.com/BerriAI/litellm))

## Quick Start

### CLI Usage

```bash
# Extract facts as JSON (default)
yt-factify extract dQw4w9WgXcQ --model gpt-4o-mini

# Extract from a full URL
yt-factify extract "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --model gpt-4o-mini

# Output as Markdown
yt-factify extract dQw4w9WgXcQ --model gpt-4o-mini --format markdown

# Save to a file
yt-factify extract dQw4w9WgXcQ --model gpt-4o-mini --output results.json

# Save to a directory (auto-names as <video_id>.json)
yt-factify extract dQw4w9WgXcQ --model gpt-4o-mini --output results/

# Save markdown to a directory (auto-names as <video_id>.md)
yt-factify extract dQw4w9WgXcQ --model gpt-4o-mini --format markdown --output results/

# Use a custom config file
yt-factify extract dQw4w9WgXcQ --config my-config.toml
```

### Library Usage

**Async:**

```python
from yt_factify import extract, AppConfig

# With defaults (reads config from env/file)
result = await extract("dQw4w9WgXcQ")

# With custom config
config = AppConfig(model="gpt-4o", temperature=0.2)
result = await extract("dQw4w9WgXcQ", config=config)

# Access extracted items
for item in result.items:
    print(f"[{item.type}] {item.content}")
    print(f"  Evidence: {item.transcript_evidence.text}")
```

**Sync:**

```python
from yt_factify import extract_sync, render_json, render_markdown

result = extract_sync("dQw4w9WgXcQ")

# Render as JSON
print(render_json(result))

# Render as Markdown
print(render_markdown(result))
```

## Configuration

Configuration is loaded with the following precedence (highest to lowest):

1. **CLI flags** — e.g., `--model gpt-4o-mini`
2. **Environment variables** — prefixed with `YT_FACTIFY_`
3. **TOML config file** — default: `~/.config/yt-factify/config.toml`
4. **Built-in defaults**

### Config File

Create `~/.config/yt-factify/config.toml`:

```toml
model = "gpt-4o-mini"
temperature = 0.0
output_format = "json"
log_level = "INFO"
segment_seconds = 45
max_concurrent_requests = 3
max_retries = 3
quote_mismatch = "reject"
```

### Environment Variables

| Variable | Config Field | Description |
|----------|-------------|-------------|
| `YT_FACTIFY_MODEL` | `model` | LLM model identifier |
| `YT_FACTIFY_API_BASE` | `api_base` | LLM API base URL |
| `YT_FACTIFY_API_KEY` | `api_key` | LLM API key |
| `YT_FACTIFY_TEMPERATURE` | `temperature` | LLM temperature (default: 0.0) |
| `YT_FACTIFY_FORMAT` | `output_format` | Output format: `json` or `markdown` |
| `YT_FACTIFY_LOG_LEVEL` | `log_level` | Logging level (default: INFO) |
| `YT_FACTIFY_MODULES_DIR` | `modules_dir` | Custom belief system modules directory |
| `YT_FACTIFY_QUOTE_MISMATCH` | `quote_mismatch` | Quote mismatch behavior: `reject` or `downgrade` |
| `YT_FACTIFY_SEGMENT_SECONDS` | `segment_seconds` | Target segment length in seconds (default: 45) |
| `YT_FACTIFY_MAX_CONCURRENT` | `max_concurrent_requests` | Max concurrent LLM requests (default: 3) |
| `YT_FACTIFY_MAX_RETRIES` | `max_retries` | Max LLM retries on failure (default: 3) |

### CLI Options

```
Usage: yt-factify extract [OPTIONS] VIDEO

Options:
  --model TEXT                    LLM model identifier
  --format [json|markdown]        Output format (default: json)
  -o, --output PATH              Output file path (default: stdout)
  --config PATH                  Config file path
  --log-level [DEBUG|INFO|WARNING|ERROR]
                                  Logging verbosity (default: INFO)
  --modules-dir PATH             Belief system modules directory
  --quote-mismatch [reject|downgrade]
                                  Quote mismatch behavior (default: reject)
  --segment-seconds INTEGER      Target segment length in seconds (default: 45)
  --api-base TEXT                LLM API base URL
  --api-key TEXT                 LLM API key (prefer env var)
  --temperature FLOAT            LLM temperature (default: 0.0)
  --help                         Show this message and exit
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Transcript fetch/parse error |
| 3 | LLM error |
| 4 | Validation error |

## Output Formats

### JSON

The default output is a JSON object containing:

- **`video`** — Video metadata (ID, URL, transcript hash, fetch timestamp)
- **`classification`** — Video categories and bias profile
- **`items`** — Extracted items, each with type, content, transcript evidence, and optional credibility assessment
- **`topic_threads`** — Items clustered by topic with timeline spans
- **`audit`** — Audit bundle (model ID, version, prompt hashes, timestamps)

Item types: `direct_quote`, `transcript_fact`, `opinion`, `claim`, `prediction`

### Markdown

Human-readable report with sections:

- **Video Info** — Title, URL, categories, bias profile
- **Topic Overview** — Topic threads with timelines
- **Key Facts** — Extracted transcript facts
- **Direct Quotes** — Verified quotes with timestamps
- **Opinions & Perspectives** — Opinions found in the transcript
- **Unverified Claims** — Claims requiring external verification
- **Predictions** — Forward-looking statements
- **Belief System Notes** — Flags for worldview-dependent claims

## Belief System Modules

Belief system modules are JSON files that describe worldviews. They help yt-factify flag when a claim depends on assumptions specific to a particular belief system.

### Built-in Modules

- `scientific_materialism` — Empirical evidence and naturalistic explanations
- `religious_theism` — Theistic worldview and divine authority
- `political_progressivism` — Progressive political values

### Authoring a Custom Module

Create a JSON file in your modules directory:

```json
{
  "label": "free_market_capitalism",
  "display_name": "Free Market Capitalism",
  "description": "A worldview that holds free markets as the optimal mechanism for resource allocation and economic growth.",
  "core_assumptions": [
    "Free markets naturally tend toward efficient resource allocation.",
    "Government intervention in markets generally reduces overall welfare.",
    "Individual economic freedom is a fundamental right."
  ],
  "example_claims": [
    "Deregulation always leads to economic growth.",
    "The invisible hand of the market corrects imbalances."
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `label` | Yes | Short `snake_case` identifier |
| `display_name` | Yes | Human-readable name |
| `description` | Yes | 1–3 sentence description of the worldview |
| `core_assumptions` | Yes | List of key assumptions (at least 1) |
| `example_claims` | No | Example claims that depend on this worldview |

Load custom modules via CLI:

```bash
yt-factify extract VIDEO --modules-dir /path/to/my/modules
```

Or via config:

```toml
modules_dir = "/path/to/my/modules"
```

See [`src/yt_factify/modules/README.md`](src/yt_factify/modules/README.md) for the full authoring guide.

## Development

### Setup

```bash
git clone https://github.com/pointmatic/yt-factify.git
cd yt-factify
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=yt_factify --cov-report=term-missing
```

### Linting & Type Checking

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy --strict src/
```

### Project Structure

```
src/yt_factify/
├── __init__.py          # Public API: extract(), extract_sync(), re-exports
├── __main__.py          # python -m yt_factify entry point
├── cli.py               # Click CLI commands
├── config.py            # Configuration loading (CLI > env > file > defaults)
├── models.py            # Pydantic v2 data models
├── pipeline.py          # Pipeline orchestration
├── transcript.py        # Transcript fetching, normalization, segmentation
├── extraction.py        # LLM-based item extraction
├── validation.py        # Transcript-anchored validation
├── classification.py    # Video categorization and credibility assessment
├── belief_systems.py    # Belief/value system module loading
├── topics.py            # Topic thread clustering
├── llm.py               # Shared LLM call helper with rate-limit retry
├── throttle.py          # Adaptive rate throttle for LLM API calls
├── rendering.py         # JSON and Markdown output rendering
├── logging.py           # Structured logging setup
├── prompts/             # LLM prompt templates
│   ├── __init__.py
│   ├── classification.py
│   ├── credibility.py
│   ├── extraction.py
│   └── topics.py
└── modules/             # Built-in belief system modules
    ├── README.md
    ├── scientific_materialism.json
    ├── religious_theism.json
    └── political_progressivism.json
```

## License

This project is licensed under the [Mozilla Public License 2.0](https://mozilla.org/MPL/2.0/).

Copyright (c) 2026 Pointmatic
