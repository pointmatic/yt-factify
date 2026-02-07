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
| `label` | Yes | Short snake_case identifier used in output references |
| `display_name` | Yes | Human-readable name for display |
| `description` | Yes | 1–3 sentence description of the worldview |
| `core_assumptions` | Yes | List of key assumptions (at least 1) |
| `example_claims` | No | Example claims that depend on this worldview |

## Authoring a New Module

1. Create a new `.json` file in this directory (or a custom modules directory).
2. Fill in all required fields following the schema above.
3. The `core_assumptions` should be specific enough that the LLM can determine whether a claim depends on them.
4. The `example_claims` field is optional but helps the LLM understand the boundary of the worldview.

## Loading Modules

- **Built-in modules** are loaded automatically from this directory via `get_builtin_modules()`.
- **Custom modules** can be loaded from any directory via `load_belief_modules(path)` or the `--modules-dir` CLI flag.
- Invalid module files are logged and skipped — they do not cause the pipeline to fail.
