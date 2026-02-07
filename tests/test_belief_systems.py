# Copyright (c) 2026 Pointmatic
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

"""Tests for yt_factify.belief_systems."""

from __future__ import annotations

import json
from pathlib import Path

from yt_factify.belief_systems import get_builtin_modules, load_belief_modules

# ---------------------------------------------------------------------------
# load_belief_modules
# ---------------------------------------------------------------------------


class TestLoadBeliefModules:
    def test_load_valid_modules(self, tmp_path: Path) -> None:
        module_data = {
            "label": "test_module",
            "display_name": "Test Module",
            "description": "A test worldview.",
            "core_assumptions": ["Assumption one."],
            "example_claims": ["Claim one."],
        }
        (tmp_path / "test_module.json").write_text(json.dumps(module_data), encoding="utf-8")
        modules = load_belief_modules(tmp_path)
        assert len(modules) == 1
        assert modules[0].label == "test_module"
        assert modules[0].display_name == "Test Module"

    def test_multiple_modules_sorted(self, tmp_path: Path) -> None:
        for name in ["beta", "alpha"]:
            data = {
                "label": name,
                "display_name": name.title(),
                "description": f"The {name} worldview.",
                "core_assumptions": ["An assumption."],
            }
            (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        modules = load_belief_modules(tmp_path)
        assert len(modules) == 2
        # Sorted by filename
        assert modules[0].label == "alpha"
        assert modules[1].label == "beta"

    def test_invalid_module_skipped(self, tmp_path: Path) -> None:
        # Valid module
        valid = {
            "label": "good",
            "display_name": "Good",
            "description": "Valid.",
            "core_assumptions": ["Yes."],
        }
        (tmp_path / "good.json").write_text(json.dumps(valid), encoding="utf-8")
        # Invalid JSON
        (tmp_path / "bad_json.json").write_text("not valid json {{{", encoding="utf-8")
        # Valid JSON but missing required fields
        (tmp_path / "bad_schema.json").write_text(
            json.dumps({"label": "incomplete"}), encoding="utf-8"
        )
        modules = load_belief_modules(tmp_path)
        assert len(modules) == 1
        assert modules[0].label == "good"

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        modules = load_belief_modules(tmp_path / "does_not_exist")
        assert modules == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        modules = load_belief_modules(tmp_path)
        assert modules == []

    def test_non_json_files_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("not a module")
        (tmp_path / "notes.md").write_text("# Notes")
        modules = load_belief_modules(tmp_path)
        assert modules == []

    def test_module_schema_validation(self, tmp_path: Path) -> None:
        """Modules with all required fields pass validation."""
        data = {
            "label": "full_module",
            "display_name": "Full Module",
            "description": "Complete module with all fields.",
            "core_assumptions": ["First assumption.", "Second assumption."],
            "example_claims": ["Example claim one.", "Example claim two."],
        }
        (tmp_path / "full.json").write_text(json.dumps(data), encoding="utf-8")
        modules = load_belief_modules(tmp_path)
        assert len(modules) == 1
        m = modules[0]
        assert m.label == "full_module"
        assert len(m.core_assumptions) == 2
        assert len(m.example_claims) == 2

    def test_module_without_example_claims(self, tmp_path: Path) -> None:
        """example_claims is optional and defaults to empty list."""
        data = {
            "label": "minimal",
            "display_name": "Minimal",
            "description": "Minimal module.",
            "core_assumptions": ["One assumption."],
        }
        (tmp_path / "minimal.json").write_text(json.dumps(data), encoding="utf-8")
        modules = load_belief_modules(tmp_path)
        assert len(modules) == 1
        assert modules[0].example_claims == []


# ---------------------------------------------------------------------------
# get_builtin_modules
# ---------------------------------------------------------------------------


class TestGetBuiltinModules:
    def test_builtin_modules_load(self) -> None:
        modules = get_builtin_modules()
        assert len(modules) >= 3

    def test_builtin_modules_have_required_fields(self) -> None:
        modules = get_builtin_modules()
        for m in modules:
            assert m.label
            assert m.display_name
            assert m.description
            assert len(m.core_assumptions) >= 1

    def test_expected_builtin_labels(self) -> None:
        modules = get_builtin_modules()
        labels = {m.label for m in modules}
        assert "scientific_materialism" in labels
        assert "religious_theism" in labels
        assert "political_progressivism" in labels

    def test_builtin_modules_are_valid_pydantic(self) -> None:
        """All built-in modules pass Pydantic validation."""
        modules = get_builtin_modules()
        for m in modules:
            # Re-validate by round-tripping
            data = m.model_dump()
            from yt_factify.models import BeliefSystemModule

            reloaded = BeliefSystemModule.model_validate(data)
            assert reloaded.label == m.label
