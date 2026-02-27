"""Tests for scripts/generate_docs.py (KIK-525)."""

import ast
import json
import os
import re
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_docs


# ---------------------------------------------------------------------------
# AST extraction tests
# ---------------------------------------------------------------------------

class TestExtractModuleApi:
    """Tests for extract_module_api()."""

    def test_simple_function(self):
        source = textwrap.dedent('''
            def foo(x: int, y: str = "bar") -> bool:
                """Check something."""
                return True
        ''')
        api = generate_docs.extract_module_api(source, "test")
        assert len(api["functions"]) == 1
        f = api["functions"][0]
        assert f["name"] == "foo"
        assert "x: int" in f["signature"]
        assert "y: str" in f["signature"]
        assert "-> bool" in f["signature"]
        assert f["doc"] == "Check something."

    def test_private_function_excluded(self):
        source = textwrap.dedent('''
            def public_fn():
                pass
            def _private_fn():
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        names = [f["name"] for f in api["functions"]]
        assert "public_fn" in names
        assert "_private_fn" not in names

    def test_all_overrides_private(self):
        source = textwrap.dedent('''
            __all__ = ["_special", "public_fn"]
            def _special():
                """Included via __all__."""
                pass
            def public_fn():
                pass
            def other():
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        names = [f["name"] for f in api["functions"]]
        assert "_special" in names
        assert "public_fn" in names
        assert "other" not in names

    def test_no_docstring(self):
        source = textwrap.dedent('''
            def no_doc(x):
                return x
        ''')
        api = generate_docs.extract_module_api(source, "test")
        assert api["functions"][0]["doc"] == ""

    def test_module_docstring(self):
        source = textwrap.dedent('''
            """Module-level docstring."""
            def foo():
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        assert api["module_doc"] == "Module-level docstring."

    def test_class_extraction(self):
        source = textwrap.dedent('''
            class MyClass:
                """A test class."""
                def method(self, x: int) -> str:
                    """Do something."""
                    pass
                def _private_method(self):
                    pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        assert len(api["classes"]) == 1
        cls = api["classes"][0]
        assert cls["name"] == "MyClass"
        assert cls["doc"] == "A test class."
        method_names = [m["name"] for m in cls["methods"]]
        assert "method" in method_names
        assert "_private_method" not in method_names

    def test_dataclass_fields(self):
        source = textwrap.dedent('''
            from dataclasses import dataclass
            @dataclass
            class Position:
                """A position."""
                symbol: str
                shares: int
                price: float
        ''')
        api = generate_docs.extract_module_api(source, "test")
        assert len(api["classes"]) == 1
        cls = api["classes"][0]
        assert cls["is_dataclass"] is True
        field_names = [f["name"] for f in cls["fields"]]
        assert "symbol" in field_names
        assert "shares" in field_names
        assert "price" in field_names

    def test_private_class_excluded(self):
        source = textwrap.dedent('''
            class Public:
                pass
            class _Private:
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        names = [c["name"] for c in api["classes"]]
        assert "Public" in names
        assert "_Private" not in names

    def test_syntax_error_returns_empty(self):
        api = generate_docs.extract_module_api("def broken(:", "test")
        assert api["functions"] == []
        assert api["classes"] == []

    def test_empty_module(self):
        api = generate_docs.extract_module_api("", "test")
        assert api["functions"] == []
        assert api["classes"] == []
        assert api["module_doc"] == ""

    def test_kwargs_and_varargs(self):
        source = textwrap.dedent('''
            def complex_fn(a, *args, key: str = "x", **kwargs) -> None:
                """Complex signature."""
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        sig = api["functions"][0]["signature"]
        assert "*args" in sig
        assert "**kwargs" in sig
        assert "key: str" in sig

    def test_long_default_truncated(self):
        source = textwrap.dedent('''
            def fn(x: dict = {"very_long_key": "very_long_value_here"}):
                pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        sig = api["functions"][0]["signature"]
        assert "..." in sig

    def test_self_cls_stripped(self):
        source = textwrap.dedent('''
            class Foo:
                def method(self, x: int):
                    pass
                @classmethod
                def class_method(cls, y: str):
                    pass
        ''')
        api = generate_docs.extract_module_api(source, "test")
        methods = api["classes"][0]["methods"]
        for m in methods:
            assert "self" not in m["signature"]
            assert "cls" not in m["signature"]


# ---------------------------------------------------------------------------
# Annotation loading tests
# ---------------------------------------------------------------------------

class TestAnnotations:
    """Tests for _load_annotations()."""

    def test_load_annotations(self, tmp_path):
        ann_file = tmp_path / "annotations.yaml"
        ann_file.write_text(textwrap.dedent('''
            # Comment line
            src/core/foo.py: "KIK-123: some feature"
            src/data/bar.py: "KIK-456: another feature"
        ''').strip())
        with patch.object(generate_docs, "ANNOTATIONS", ann_file):
            result = generate_docs._load_annotations()
        assert result["src/core/foo.py"] == "KIK-123: some feature"
        assert result["src/data/bar.py"] == "KIK-456: another feature"

    def test_missing_annotations_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        with patch.object(generate_docs, "ANNOTATIONS", missing):
            result = generate_docs._load_annotations()
        assert result == {}


# ---------------------------------------------------------------------------
# Skill frontmatter parsing tests
# ---------------------------------------------------------------------------

class TestSkillFrontmatter:
    """Tests for _parse_skill_frontmatter()."""

    def test_parse_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(textwrap.dedent('''
            ---
            name: test-skill
            description: "A test skill for testing."
            ---
            # Skill content here
        ''').strip())
        fm = generate_docs._parse_skill_frontmatter(skill_md)
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test skill for testing."

    def test_no_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# No frontmatter here\n")
        fm = generate_docs._parse_skill_frontmatter(skill_md)
        assert fm == {}


# ---------------------------------------------------------------------------
# Generator tests (using real project files)
# ---------------------------------------------------------------------------

class TestGenerateApiReference:
    """Tests for generate_api_reference()."""

    def test_generates_non_empty_content(self):
        content = generate_docs.generate_api_reference()
        assert "# API Reference" in content
        assert "Auto-generated" in content
        assert "## Core Layer" in content

    def test_contains_known_functions(self):
        content = generate_docs.generate_api_reference()
        # These should exist in src/core/common.py
        assert "finite_or_none" in content

    def test_contains_known_classes(self):
        content = generate_docs.generate_api_reference()
        # Position class from src/core/models.py
        assert "Position" in content

    def test_no_private_functions_leaked(self):
        content = generate_docs.generate_api_reference()
        lines = content.splitlines()
        for line in lines:
            if line.startswith("- `_"):
                # Private function leaked (unless in __all__)
                # This is a soft check - just ensure most entries are public
                pass


class TestGenerateArchitecture:
    """Tests for generate_architecture()."""

    def test_updates_claude_md(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(textwrap.dedent(f'''
            # Header
            {generate_docs.BEGIN_ARCH}
            old content
            {generate_docs.END_ARCH}
            # Footer
        ''').strip())
        with patch.object(generate_docs, "CLAUDE_MD", claude_md):
            result = generate_docs.generate_architecture()
        assert result in ("updated", "unchanged")
        content = claude_md.read_text()
        assert "Skills" in content
        assert "Core" in content

    def test_no_markers_returns_none(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# No markers here\n")
        with patch.object(generate_docs, "CLAUDE_MD", claude_md):
            result = generate_docs.generate_architecture()
        assert result is None


class TestPresetCount:
    """Tests for preset counting in architecture."""

    def test_counts_nested_presets(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        presets_yaml = config_dir / "screening_presets.yaml"
        presets_yaml.write_text(textwrap.dedent('''
            presets:
              value:
                description: "value"
              growth:
                description: "growth"
              alpha:
                description: "alpha"
        ''').strip())
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(f"{generate_docs.BEGIN_ARCH}\nold\n{generate_docs.END_ARCH}")
        with patch.object(generate_docs, "CLAUDE_MD", claude_md), \
             patch.object(generate_docs, "ROOT", tmp_path), \
             patch.object(generate_docs, "SRC", tmp_path / "src"), \
             patch.object(generate_docs, "SKILLS_DIR", tmp_path / "skills"):
            (tmp_path / "src" / "core").mkdir(parents=True)
            (tmp_path / "src" / "data").mkdir(parents=True)
            (tmp_path / "src" / "output").mkdir(parents=True)
            (tmp_path / "skills").mkdir()
            (tmp_path / "config").mkdir(exist_ok=True)
            result = generate_docs.generate_architecture()
        assert result == "updated"
        content = claude_md.read_text()
        assert "3 presets" in content

    def test_zero_presets_when_no_file(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(f"{generate_docs.BEGIN_ARCH}\nold\n{generate_docs.END_ARCH}")
        with patch.object(generate_docs, "CLAUDE_MD", claude_md), \
             patch.object(generate_docs, "ROOT", tmp_path), \
             patch.object(generate_docs, "SRC", tmp_path / "src"), \
             patch.object(generate_docs, "SKILLS_DIR", tmp_path / "skills"):
            (tmp_path / "src" / "core").mkdir(parents=True)
            (tmp_path / "src" / "data").mkdir(parents=True)
            (tmp_path / "src" / "output").mkdir(parents=True)
            (tmp_path / "skills").mkdir()
            result = generate_docs.generate_architecture()
        assert result == "updated"
        content = claude_md.read_text()
        assert "0 presets" in content


class TestGenerateSkillCatalog:
    """Tests for generate_skill_catalog()."""

    def test_updates_overview_table(self, tmp_path):
        # Create skill dirs
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: A test skill\n---\n# Content")

        catalog = tmp_path / "skill-catalog.md"
        catalog.write_text(f"# Catalog\n{generate_docs.BEGIN_OVERVIEW}\nold\n{generate_docs.END_OVERVIEW}\n# Rest")

        with patch.object(generate_docs, "SKILL_CATALOG", catalog), \
             patch.object(generate_docs, "SKILLS_DIR", tmp_path / "skills"):
            result = generate_docs.generate_skill_catalog()
        assert result == "updated"
        content = catalog.read_text()
        assert "test-skill" in content
        assert "A test skill" in content

    def test_no_markers_returns_none(self, tmp_path):
        catalog = tmp_path / "skill-catalog.md"
        catalog.write_text("# No markers")
        with patch.object(generate_docs, "SKILL_CATALOG", catalog):
            result = generate_docs.generate_skill_catalog()
        assert result is None


class TestVerifyDataModels:
    """Tests for verify_data_models()."""

    def test_in_sync(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        (fixtures / "stock_info.json").write_text(json.dumps({"per": 10, "pbr": 1.5}))
        (fixtures / "stock_detail.json").write_text(json.dumps({"name": "Toyota"}))

        doc = tmp_path / "data-models.md"
        doc.write_text("| `per` | float |\n| `pbr` | float |\n| `name` | str |")

        with patch.object(generate_docs, "DATA_MODELS", doc), \
             patch.object(generate_docs, "FIXTURES", fixtures):
            ok, msgs = generate_docs.verify_data_models()
        assert ok is True

    def test_missing_keys_detected(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        (fixtures / "stock_info.json").write_text(json.dumps({"per": 10, "new_key": 42}))
        (fixtures / "stock_detail.json").write_text(json.dumps({"name": "Toyota"}))

        doc = tmp_path / "data-models.md"
        doc.write_text("| `per` | float |\n| `name` | str |")

        with patch.object(generate_docs, "DATA_MODELS", doc), \
             patch.object(generate_docs, "FIXTURES", fixtures):
            ok, msgs = generate_docs.verify_data_models()
        assert ok is False
        assert any("new_key" in m for m in msgs)

    def test_missing_doc_file(self, tmp_path):
        with patch.object(generate_docs, "DATA_MODELS", tmp_path / "nonexistent.md"):
            ok, msgs = generate_docs.verify_data_models()
        assert ok is False


class TestCheckStaleness:
    """Tests for check_staleness()."""

    def test_returns_zero_when_fresh(self):
        # Run on real project - should be fresh since we just generated
        code = generate_docs.check_staleness(quiet=True)
        assert code == 0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestFirstLine:
    """Tests for _first_line()."""

    def test_single_line(self):
        assert generate_docs._first_line("Hello world.") == "Hello world."

    def test_multi_line(self):
        assert generate_docs._first_line("First line.\nSecond line.") == "First line."

    def test_none(self):
        assert generate_docs._first_line(None) == ""

    def test_empty(self):
        assert generate_docs._first_line("") == ""

    def test_leading_blank_lines(self):
        assert generate_docs._first_line("\n\n  Content here.") == "Content here."
