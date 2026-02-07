# Belief/Value System Modules

Belief/value system modules are JSON files that describe distinct worldviews or belief systems. They are used by yt-factify to flag when an extracted claim relies on assumptions specific to a particular worldview rather than being universally accepted.

## Module Schema

Each module is a JSON file conforming to this schema:

```json
{
  "label": "string — short identifier, e.g. 'scientific_materialism'",
  "display_name": "string — human-readable name, e.g. 'Scientific Materialism'",
  "description": "string — what this system believes",
  "core_assumptions": [
    "string — key assumptions of this worldview"
  ],
  "example_claims": [
    "string — claims that rely on this worldview (optional)"
  ]
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `label` | Yes | Short `snake_case` identifier used in output references |
| `display_name` | Yes | Human-readable name for display |
| `description` | Yes | 1–3 sentence description of the worldview |
| `core_assumptions` | Yes | List of key assumptions (at least 1) |
| `example_claims` | No | Example claims that depend on this worldview |

## Built-in Modules

This directory ships with three built-in modules:

- **`scientific_materialism.json`** — Empirical evidence, the scientific method, and naturalistic explanations
- **`religious_theism.json`** — Theistic worldview, divine authority, and faith-based reasoning
- **`political_progressivism.json`** — Progressive political values and social justice

These are loaded automatically during pipeline execution.

## Authoring a New Module

### Step-by-Step

1. Create a new `.json` file in this directory (or a custom modules directory).
2. Fill in all required fields following the schema above.
3. The `core_assumptions` should be specific enough that the LLM can determine whether a claim depends on them.
4. The `example_claims` field is optional but helps the LLM understand the boundary of the worldview.

### Template

Copy this template and fill in the values:

```json
{
  "label": "my_worldview",
  "display_name": "My Worldview",
  "description": "A brief 1-3 sentence description of what this worldview holds to be true.",
  "core_assumptions": [
    "First key assumption that distinguishes this worldview.",
    "Second key assumption.",
    "Third key assumption."
  ],
  "example_claims": [
    "An example claim that someone holding this worldview might make.",
    "Another example claim."
  ]
}
```

### Tips for Effective Modules

- **Be specific** in `core_assumptions` — vague assumptions produce vague flags.
- **Use 3–5 assumptions** for best results. Too few may miss relevant claims; too many may over-flag.
- **Include `example_claims`** — they help the LLM calibrate what counts as worldview-dependent.
- **Use `snake_case`** for the `label` field — it appears in machine-readable output.
- **Test your module** by running an extraction and checking the "Belief System Notes" section.

### Validation

Module files are validated on load. A valid module must have:

- A non-empty `label` (string)
- A non-empty `display_name` (string)
- A non-empty `description` (string)
- At least one entry in `core_assumptions` (list of strings)

Invalid module files are logged as warnings and skipped — they do not cause the pipeline to fail.

## Loading Modules

- **Built-in modules** are loaded automatically from this directory via `get_builtin_modules()`.
- **Custom modules** can be loaded from any directory via `load_belief_modules(path)` or the `--modules-dir` CLI flag.
- Custom modules are loaded **in addition to** built-in modules, not as replacements.

### CLI

```bash
yt-factify extract VIDEO --modules-dir /path/to/my/modules
```

### Config File

```toml
modules_dir = "/path/to/my/modules"
```

### Library API

```python
from yt_factify import extract, AppConfig

config = AppConfig(model="gpt-4o-mini", modules_dir="/path/to/my/modules")
result = await extract("VIDEO_ID", config=config)
```
