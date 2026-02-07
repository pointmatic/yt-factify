# features.md — yt-factify (Python)

This document defines **what** yt-factify does — its requirements, inputs, outputs, and expected behavior — without prescribing implementation details. It is the source of truth for project scope. For architecture and module design, see [`tech_spec.md`](tech_spec.md). For the implementation plan, see [`stories.md`](stories.md).

---

## Project Goal

yt-factify is a tool that extracts structured, auditable information from YouTube video transcripts. It uses an LLM as a **proposal engine** to identify facts, direct quotes, opinions, claims, and predictions, then anchors every extracted item to an exact transcript span. The tool also classifies the video's category, detects slant/bias, and provides a credibility assessment of each extracted item — all while remaining transparent and traceable.

yt-factify is both a **Python library** (for programmatic use) and a **CLI tool** (for interactive and scripted use).

### Core Requirements

1. **Transcript ingestion** — Accept a YouTube video URL or video ID, fetch the transcript via [`yt-fetch`](https://github.com/pointmatic/yt-fetch), and normalize it into a canonical internal format with timestamped segments.
2. **Item extraction** — Use an LLM to extract structured items from the transcript. Each item is one of the following types:
   - `direct_quote` — an exact substring of the transcript, attributed to a speaker if identifiable.
   - `transcript_fact` — a factual claim made in the video, anchored to a transcript span.
   - `general_knowledge` — a widely accepted fact referenced or implied in the video.
   - `speaker_opinion` — a subjective statement, value judgment, or editorial position.
   - `unverified_claim` — a claim presented as fact but lacking sufficient support.
   - `prediction` — a forward-looking statement about future events or outcomes.
3. **Transcript anchoring** — Every extracted item must reference the exact transcript text span (start/end timestamps and verbatim text) that supports it. Direct quotes must be exact substring matches of the transcript.
4. **Video categorization** — Classify the video into one or more categories: `news`, `entertainment`, `music_video`, `comedy_satire`, `interview`, `documentary`, `tutorial`, `opinion_editorial`, `political_speech`, `panel_discussion`, or `other`. The category influences extraction behavior and output interpretation.
5. **Slant and bias detection** — Assess the overall slant or bias of the video. Produce a structured bias profile that includes:
   - A primary bias label (e.g., `left_leaning`, `right_leaning`, `neutral`, `religious`, `scientific_materialist`, `libertarian`, `authoritarian`, etc.).
   - A confidence score.
   - A short rationale citing specific transcript evidence.
   - Detection of implicit bias by omission (one-sided framing, missing counter-perspectives).
6. **Belief/value system modules** — Support pluggable modules that describe distinct worldviews or belief systems. Each module has a label, a description of what that system believes, and a set of assumptions. These modules are used to flag when a claim relies on assumptions specific to a particular worldview rather than being universally accepted. Module definitions follow a standard template so they can be authored independently (e.g., by an LLM given the template).
7. **Credibility classification** — For each extracted item, provide a credibility assessment using the LLM's general knowledge:
   - `well_established` — widely corroborated and non-controversial.
   - `credible` — plausible and consistent with known information.
   - `disputed` — subject to active debate or conflicting evidence.
   - `dubious` — contradicts well-established knowledge or relies on unsubstantiated assumptions.
   - `unassessable` — insufficient information to judge.
   - Include a short rationale and, if applicable, which belief/value system module(s) are relevant.
8. **Provenance and auditability** — Every output must be fully traceable:
   - Transcript hash (SHA-256 of the normalized transcript).
   - Per-segment hashes.
   - Model identifier and version used for extraction.
   - Prompt templates used.
   - All intermediate artifacts preserved in the output bundle.

### Operational Requirements

1. **Error handling** — Fail explicitly and informatively. If the transcript cannot be fetched, the LLM returns malformed output, or a quote does not match the transcript, the tool must report the error clearly rather than silently degrading.
2. **Logging** — Provide structured logging at configurable levels (DEBUG, INFO, WARNING, ERROR). Log key pipeline stages: ingestion, segmentation, extraction, validation, classification, and output rendering.
3. **Configuration** — Support configuration via environment variables, a config file, and CLI flags, with a clear precedence order (CLI > env > config file > defaults).
4. **Idempotency** — Given the same transcript, LLM model, and configuration, the tool should produce deterministic results (temperature=0, fixed chunking, stable prompt templates).

### Quality Requirements

1. **Schema validation** — All LLM outputs must conform to a strict JSON schema. If validation fails, the run fails with a clear error.
2. **Quote verification** — Every `direct_quote` must be verified as an exact substring of the transcript. Non-matching quotes are rejected.
3. **Timestamp bounds checking** — Extracted items must reference valid timestamp ranges that exist in the transcript.
4. **Hashing for drift detection** — Transcript and segment hashes allow detection of changes if the same video is processed again later.

### Usability Requirements

1. **CLI interface** — A command-line tool that accepts a YouTube URL or video ID and produces structured output (JSON by default, with optional human-readable summary).
2. **Library API** — A Python API that exposes the same functionality programmatically, returning typed Pydantic models.
3. **Output formats** — JSON (primary), with optional human-readable Markdown summary.
4. **Progress feedback** — The CLI should provide progress indicators for long-running operations (transcript fetch, LLM calls).

### Non-goals

1. **External source verification** — v1 does not retrieve or check external sources (web search, databases, etc.) to verify claims. Credibility is assessed using the LLM's general knowledge only.
2. **Speaker diarization** — v1 does not perform audio-based speaker identification. Speaker attribution is limited to what can be inferred from transcript text (e.g., interview format markers, self-identification).
3. **Audio/video processing** — The tool operates on transcripts only; it does not download, process, or analyze audio or video streams.
4. **Content generation** — yt-factify extracts and classifies; it does not generate summaries, articles, or narratives from the extracted data.
5. **Real-time processing** — The tool processes one video at a time in batch mode; streaming/real-time analysis is out of scope.
6. **PII detection/redaction** — Deferred to a future version.
7. **Stance evolution tracking** — Detecting when a speaker changes their position on a topic during the video (e.g., starts skeptical but becomes convinced). Topic threads capture *what* is discussed and *when*, but tracking *how positions shift* within a thread is deferred to a future version.

---

## Inputs

### Required

| Input | Description | Example |
|-------|-------------|---------|
| YouTube video URL or ID | Identifies the video to process | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` or `dQw4w9WgXcQ` |

### Optional

| Input | Description | Default |
|-------|-------------|---------|
| LLM model identifier | Which model to use for extraction | Configurable default |
| Belief/value system modules | Paths to module definition files to load | Built-in defaults |
| Output format | `json` or `markdown` | `json` |
| Output path | Where to write results | stdout |
| Config file path | Path to YAML/TOML config file | `~/.config/yt-factify/config.toml` |
| Log level | Logging verbosity | `INFO` |

---

## Outputs

### Primary Output: Extraction Result (JSON)

The primary output is a JSON document conforming to a strict schema. Top-level structure:

```json
{
  "video": {
    "video_id": "string",
    "title": "string (if available)",
    "url": "string",
    "transcript_hash": "string (SHA-256)",
    "fetched_at": "ISO 8601 timestamp"
  },
  "classification": {
    "categories": ["string"],
    "bias_profile": {
      "primary_label": "string",
      "confidence": 0.0,
      "rationale": "string",
      "implicit_bias_notes": ["string"]
    }
  },
  "items": [
    {
      "id": "string (unique within this result)",
      "type": "direct_quote | transcript_fact | general_knowledge | speaker_opinion | unverified_claim | prediction",
      "content": "string (the extracted text or claim)",
      "speaker": "string | null",
      "transcript_evidence": {
        "video_id": "string",
        "start_ms": 0,
        "end_ms": 0,
        "text": "string (exact transcript span)"
      },
      "credibility": {
        "label": "well_established | credible | disputed | dubious | unassessable",
        "confidence": 0.0,
        "rationale": "string",
        "relevant_belief_systems": ["string"]
      },
      "belief_system_flags": [
        {
          "module_label": "string",
          "note": "string (why this item relates to this belief system)"
        }
      ]
    }
  ],
  "topic_threads": [
    {
      "label": "string (short identifier, e.g., 'ai_safety')",
      "display_name": "string (human-readable name)",
      "summary": "string (1-2 sentence description)",
      "item_ids": ["string (references to items in this thread)"],
      "timeline": [
        {
          "start_ms": 0,
          "end_ms": 0
        }
      ]
    }
  ],
  "audit": {
    "model_id": "string",
    "model_version": "string",
    "prompt_templates_hash": "string",
    "processing_timestamp": "ISO 8601 timestamp",
    "segment_hashes": ["string"],
    "yt_factify_version": "string"
  }
}
```

### Optional Output: Markdown Summary

A human-readable report organized by section:

- **Video Info** — title, URL, categories, bias profile.
- **Topic Overview** — topic threads with timelines showing when each topic appears and recurs.
- **Key Facts** — items of type `transcript_fact` and `general_knowledge`, grouped by credibility.
- **Direct Quotes** — notable quotes with speaker attribution and timestamps.
- **Opinions & Perspectives** — `speaker_opinion` items with bias context.
- **Unverified Claims** — items flagged as `unverified_claim` or `dubious`.
- **Predictions** — forward-looking statements.
- **Belief System Notes** — items flagged as relying on specific worldview assumptions.

---

## Functional Requirements

### FR-1: Transcript Ingestion

The tool accepts a YouTube video URL or video ID, invokes `yt-fetch` to retrieve the transcript, and normalizes it into timestamped segments. The normalized transcript is hashed (SHA-256) for provenance. If the transcript cannot be fetched, the tool exits with a clear error message and non-zero exit code.

### FR-2: Transcript Segmentation

The normalized transcript is split into segments suitable for LLM processing. Segmentation respects sentence boundaries where possible and targets segments of approximately 30–60 seconds of video. Each segment receives a unique hash.

### FR-3: Item Extraction

For each segment (or group of segments), the tool sends a structured prompt to the LLM requesting extraction of items. The LLM must return JSON conforming to the item schema. The prompt includes:
- The transcript segment text with timestamps.
- The item type definitions and schema.
- Instructions to anchor every item to exact transcript text.
- Instructions not to paraphrase or editorialize.

### FR-4: Quote Verification

After extraction, every `direct_quote` item is programmatically verified:
- The `transcript_evidence.text` must be an exact substring of the corresponding transcript segment(s).
- The `start_ms` and `end_ms` must fall within valid transcript timestamp ranges.
- Items that fail verification are either rejected (removed from output) or downgraded to `unverified_claim` with a note, depending on configuration.

### FR-5: Video Categorization

The tool classifies the video into one or more categories based on transcript content. Classification is performed by the LLM using the full transcript (or a representative sample for very long videos). The result includes a primary category and optional secondary categories.

### FR-6: Slant and Bias Detection

The tool produces a bias profile for the video. This includes:
- A primary bias label from a defined taxonomy.
- A confidence score (0.0–1.0).
- A rationale citing specific transcript evidence.
- Notes on implicit bias by omission — topics or perspectives conspicuously absent.
- Detection of polarized language patterns (effusive praise, harsh criticism, one-sided framing).

The bias taxonomy is extensible. Default labels include but are not limited to: `left_leaning`, `right_leaning`, `centrist`, `neutral`, `religious`, `scientific_materialist`, `libertarian`, `authoritarian`, `populist`, `corporate`, `activist`.

### FR-7: Belief/Value System Module Support

The tool supports loading belief/value system module definitions from files. Each module follows a standard template:

```json
{
  "label": "string (short identifier, e.g., 'scientific_materialism')",
  "display_name": "string (human-readable name)",
  "description": "string (what this system believes)",
  "core_assumptions": ["string (key assumptions of this worldview)"],
  "example_claims": ["string (claims that rely on this worldview)"]
}
```

During extraction, the LLM is provided with loaded module definitions and asked to flag items whose truth value depends on assumptions specific to a particular worldview. This prevents the LLM's own training biases from silently coloring the output.

### FR-8: Credibility Classification

Each extracted item receives a credibility label based on the LLM's general knowledge (no external lookups). The classification includes:
- A label from the credibility taxonomy (`well_established`, `credible`, `disputed`, `dubious`, `unassessable`).
- A confidence score (0.0–1.0).
- A short rationale.
- References to relevant belief/value system modules, if applicable.

### FR-9: Topic Threading

After extraction, the tool clusters extracted items into **topic threads** — named groups of items that share a common subject. This captures the conversational structure of videos where topics are introduced, revisited, and deepened over time.

Each topic thread includes:
- A short label (e.g., `ai_safety`) and human-readable display name (e.g., "AI Safety Concerns").
- A 1–2 sentence summary of the thread.
- References to the extracted items belonging to this thread (an item may belong to multiple threads).
- A timeline showing the time ranges where this topic appears in the video, revealing revisitation patterns.

Topic threading is performed by the LLM as a post-extraction analysis pass. The LLM receives all validated extracted items and clusters them by subject. For v1, threads are a flat list (no hierarchical sub-topics). Items may belong to zero or more threads.

### FR-10: Output Rendering

The tool renders the extraction result in the requested format:
- **JSON** (default): the full structured output conforming to the schema.
- **Markdown**: a human-readable summary report (see Outputs section).

Output is written to stdout by default, or to a specified file path.

### FR-11: Audit Bundle

Every run produces an audit trail as part of the output, including:
- Transcript hash and segment hashes.
- Model identifier and version.
- Hash of the prompt templates used.
- Processing timestamp.
- yt-factify version.

This allows any output to be audited: *"Was this produced from this transcript, using this model, with these prompts?"*

### FR-12: Graceful Request Management

The tool must manage its interactions with external services (YouTube transcript APIs and LLM APIs) responsibly and resiliently:

- **Rate-limit awareness** — When an external service signals that requests are arriving too quickly, the tool must slow down automatically rather than failing or flooding the service with retries.
- **Adaptive pacing** — Under sustained rate pressure, the tool should progressively reduce its request rate. When pressure subsides, it should cautiously return to a higher throughput.
- **No thundering herd** — When multiple concurrent requests are rate-limited simultaneously, the tool must coordinate its retry behavior globally rather than having each request independently retry at the same time.
- **Progress visibility** — During long-running extractions, the tool should report progress (percentage complete and estimated time remaining) so the user knows the pipeline is advancing, especially when the request rate has been reduced.
- **Informative diagnostics** — When transcript fetching fails, the tool should provide actionable guidance based on available context (e.g., whether the video was uploaded recently and captions may not yet be available).
- **Configurable concurrency** — The user should be able to control the maximum number of concurrent requests to match their API plan's limits.

---

## Configuration

### Precedence (highest to lowest)

1. CLI flags
2. Environment variables (prefixed with `YT_FACTIFY_`)
3. Config file (`~/.config/yt-factify/config.toml` by default)
4. Built-in defaults

### Key Configuration Options

| Option | Env Var | CLI Flag | Default | Description |
|--------|---------|----------|---------|-------------|
| LLM model | `YT_FACTIFY_MODEL` | `--model` | (required or configured) | Model identifier for extraction |
| LLM API base URL | `YT_FACTIFY_API_BASE` | `--api-base` | Provider default | Base URL for the LLM API |
| LLM API key | `YT_FACTIFY_API_KEY` | `--api-key` | — | API key (prefer env var) |
| Temperature | `YT_FACTIFY_TEMPERATURE` | `--temperature` | `0.0` | LLM temperature for determinism |
| Output format | `YT_FACTIFY_FORMAT` | `--format` | `json` | `json` or `markdown` |
| Output path | — | `--output` / `-o` | stdout | File path for output |
| Config file | — | `--config` | `~/.config/yt-factify/config.toml` | Path to config file |
| Log level | `YT_FACTIFY_LOG_LEVEL` | `--log-level` | `INFO` | Logging verbosity |
| Belief system modules dir | `YT_FACTIFY_MODULES_DIR` | `--modules-dir` | Built-in modules | Directory containing module JSON files |
| Quote mismatch behavior | `YT_FACTIFY_QUOTE_MISMATCH` | `--quote-mismatch` | `reject` | `reject` or `downgrade` |
| Segment duration target | `YT_FACTIFY_SEGMENT_SECONDS` | `--segment-seconds` | `45` | Target segment length in seconds |

---

## Testing Requirements

1. **Unit tests** — Cover all data models, schema validation, quote verification logic, segmentation, and configuration loading.
2. **Integration tests** — Test the full pipeline with fixture transcripts and mocked LLM responses.
3. **Golden tests** — Maintain a set of fixture transcripts with expected outputs; run in CI to detect regressions.
4. **Edge case tests** — Empty transcripts, single-segment transcripts, transcripts with no identifiable facts, malformed LLM responses, quote mismatches.
5. **Minimum coverage** — 80% line coverage for core modules.

---

## Security and Compliance Notes

1. **API keys** — LLM API keys must never be logged or included in output. Prefer environment variables over CLI flags for secrets.
2. **No data exfiltration** — The tool sends transcript text to the configured LLM API and nowhere else. No telemetry, no analytics.
3. **License compliance** — All source files carry the Apache-2.0 header. Third-party dependencies must have compatible licenses.

---

## Performance Notes

1. **LLM calls** — The primary bottleneck. Segment-level extraction can be parallelized (concurrent API calls) with configurable concurrency limits.
2. **Rate limiting** — Respect LLM API rate limits. Implement configurable retry with exponential backoff.
3. **Caching** — Cache normalized transcripts and segment hashes to avoid redundant fetches. LLM results may optionally be cached keyed by (segment_hash, model_id, prompt_hash).
4. **Long videos** — For very long transcripts (>2 hours), the tool should handle segmentation gracefully without exceeding memory limits.

---

## Acceptance Criteria

The project is considered complete when:

1. A user can run `yt-factify <youtube-url>` and receive a valid JSON output containing categorized, anchored, credibility-assessed items.
2. Every `direct_quote` in the output is a verified exact substring of the transcript.
3. Every item includes `transcript_evidence` with valid timestamps and text.
4. The output includes a video categorization and bias profile.
5. Belief/value system modules can be loaded and influence the output.
6. The library API exposes the same functionality with typed Pydantic models.
7. The audit bundle is complete and allows full traceability.
8. All tests pass with ≥80% coverage on core modules.
9. The tool handles errors gracefully with informative messages.
10. Configuration works via CLI flags, environment variables, and config file with correct precedence.
