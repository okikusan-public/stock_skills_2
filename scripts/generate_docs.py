#!/usr/bin/env python3
"""Auto-generate documentation from source code (KIK-525).

Usage:
    python3 scripts/generate_docs.py api-reference       # docs/api-reference.md
    python3 scripts/generate_docs.py architecture         # CLAUDE.md Architecture section
    python3 scripts/generate_docs.py test-count           # development.md test count
    python3 scripts/generate_docs.py skill-catalog        # docs/skill-catalog.md overview table
    python3 scripts/generate_docs.py data-models-verify   # Verify docs/data-models.md
    python3 scripts/generate_docs.py all                  # Run all generators
    python3 scripts/generate_docs.py check [--quiet]      # Check staleness (exit 0/1)
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
DOCS = ROOT / "docs"
CLAUDE_MD = ROOT / "CLAUDE.md"
DEV_MD = ROOT / ".claude" / "rules" / "development.md"
SKILL_CATALOG = DOCS / "skill-catalog.md"
API_REF = DOCS / "api-reference.md"
DATA_MODELS = DOCS / "data-models.md"
ANNOTATIONS = ROOT / "config" / "module_annotations.yaml"
FIXTURES = ROOT / "tests" / "fixtures"
SKILLS_DIR = ROOT / ".claude" / "skills"

# Markers
BEGIN_ARCH = "<!-- BEGIN AUTO-GENERATED ARCHITECTURE -->"
END_ARCH = "<!-- END AUTO-GENERATED ARCHITECTURE -->"
BEGIN_OVERVIEW = "<!-- BEGIN AUTO-GENERATED OVERVIEW -->"
END_OVERVIEW = "<!-- END AUTO-GENERATED OVERVIEW -->"


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------

def _first_line(docstring: str | None) -> str:
    """Return first non-empty line of a docstring."""
    if not docstring:
        return ""
    for line in docstring.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _format_arg(arg: ast.arg) -> str:
    """Format a single function argument."""
    name = arg.arg
    if arg.annotation:
        return f"{name}: {ast.unparse(arg.annotation)}"
    return name


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Format function signature as compact string."""
    args = node.args
    parts = []

    # Regular args (skip 'self'/'cls')
    all_args = args.args[:]
    if all_args and all_args[0].arg in ("self", "cls"):
        all_args = all_args[1:]

    # Defaults are right-aligned
    n_defaults = len(args.defaults)
    n_args = len(all_args)
    for i, arg in enumerate(all_args):
        formatted = _format_arg(arg)
        default_idx = i - (n_args - n_defaults)
        if default_idx >= 0:
            default = ast.unparse(args.defaults[default_idx])
            # Truncate long defaults
            if len(default) > 20:
                default = "..."
            formatted += f"={default}"
        parts.append(formatted)

    # *args
    if args.vararg:
        parts.append(f"*{_format_arg(args.vararg)}")
    elif args.kwonlyargs:
        parts.append("*")

    # keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        formatted = _format_arg(arg)
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = ast.unparse(args.kw_defaults[i])
            if len(default) > 20:
                default = "..."
            formatted += f"={default}"
        parts.append(formatted)

    # **kwargs
    if args.kwarg:
        parts.append(f"**{_format_arg(args.kwarg)}")

    sig = ", ".join(parts)

    # Return type
    ret = ""
    if node.returns:
        ret = f" -> {ast.unparse(node.returns)}"

    return f"({sig}){ret}"


def _is_dataclass(node: ast.ClassDef) -> bool:
    """Check if class has @dataclass decorator."""
    for dec in node.decorator_list:
        name = ""
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Attribute):
            name = dec.attr
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                name = dec.func.id
            elif isinstance(dec.func, ast.Attribute):
                name = dec.func.attr
        if name == "dataclass":
            return True
    return False


def extract_module_api(source: str, module_path: str) -> dict:
    """Extract public API from a Python source string.

    Returns dict with keys: module_doc, functions, classes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"module_doc": "", "functions": [], "classes": []}

    # Check for __all__
    all_names = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        all_names = set()
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.add(elt.value)

    module_doc = _first_line(ast.get_docstring(tree))

    functions = []
    classes = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            # Skip private unless in __all__
            if name.startswith("_") and (all_names is None or name not in all_names):
                continue
            if all_names is not None and name not in all_names:
                continue
            sig = _format_signature(node)
            doc = _first_line(ast.get_docstring(node))
            functions.append({"name": name, "signature": sig, "doc": doc, "line": node.lineno})

        elif isinstance(node, ast.ClassDef):
            name = node.name
            if name.startswith("_") and (all_names is None or name not in all_names):
                continue
            if all_names is not None and name not in all_names:
                continue
            class_doc = _first_line(ast.get_docstring(node))
            is_dc = _is_dataclass(node)

            fields = []
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name not in ("__init__",):
                        continue
                    if item.name == "__init__":
                        continue
                    msig = _format_signature(item)
                    mdoc = _first_line(ast.get_docstring(item))
                    methods.append({"name": item.name, "signature": msig, "doc": mdoc})
                elif is_dc and isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fname = item.target.id
                    ftype = ast.unparse(item.annotation) if item.annotation else ""
                    fields.append({"name": fname, "type": ftype})

            classes.append({
                "name": name,
                "doc": class_doc,
                "is_dataclass": is_dc,
                "fields": fields,
                "methods": methods,
                "line": node.lineno,
            })

    return {"module_doc": module_doc, "functions": functions, "classes": classes}


# ---------------------------------------------------------------------------
# Annotation loading
# ---------------------------------------------------------------------------

def _load_annotations() -> dict[str, str]:
    """Load module annotations from YAML (simple key: value format)."""
    if not ANNOTATIONS.exists():
        return {}
    result = {}
    for line in ANNOTATIONS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([^:]+):\s*"?(.+?)"?\s*$', line)
        if m:
            result[m.group(1).strip()] = m.group(2).strip()
    return result


# ---------------------------------------------------------------------------
# Target: api-reference
# ---------------------------------------------------------------------------

def _collect_modules(base: Path) -> list[tuple[str, Path]]:
    """Collect all .py modules under base, sorted by dotted path."""
    modules = []
    for py_file in sorted(base.rglob("*.py")):
        rel = py_file.relative_to(ROOT)
        # Skip __pycache__
        if "__pycache__" in str(rel):
            continue
        # Convert path to dotted module name
        parts = list(rel.with_suffix("").parts)
        dotted = ".".join(parts)
        modules.append((dotted, py_file))
    return modules


def generate_api_reference() -> str:
    """Generate docs/api-reference.md content."""
    lines = [
        "# API Reference",
        "",
        "> Auto-generated by `scripts/generate_docs.py`. Do not edit manually.",
        "",
    ]

    layers = [
        ("Core", SRC / "core"),
        ("Data", SRC / "data"),
        ("Output", SRC / "output"),
    ]

    annotations = _load_annotations()

    for layer_name, layer_path in layers:
        if not layer_path.exists():
            continue
        lines.append(f"## {layer_name} Layer")
        lines.append("")

        for dotted, py_file in _collect_modules(layer_path):
            rel_str = str(py_file.relative_to(ROOT))

            # Skip empty __init__.py (just re-exports)
            source = py_file.read_text(errors="replace")
            api = extract_module_api(source, dotted)

            # Skip modules with no public API and no doc
            if not api["functions"] and not api["classes"] and not api["module_doc"]:
                continue
            # Skip __init__.py that only re-export (no own functions/classes)
            if py_file.name == "__init__.py" and not api["functions"] and not api["classes"]:
                continue

            # Section header
            annotation = annotations.get(rel_str, "")
            ann_suffix = f" ({annotation})" if annotation else ""
            lines.append(f"### {dotted}{ann_suffix}")
            lines.append("")
            if api["module_doc"]:
                lines.append(f"{api['module_doc']}")
                lines.append("")

            # Functions
            for func in api["functions"]:
                doc_part = f" — {func['doc']}" if func["doc"] else ""
                lines.append(f"- `{func['name']}{func['signature']}`{doc_part}")

            # Classes
            for cls in api["classes"]:
                lines.append("")
                lines.append(f"#### class {cls['name']}")
                if cls["doc"]:
                    lines.append(f"{cls['doc']}")
                lines.append("")

                if cls["fields"]:
                    lines.append("| Field | Type |")
                    lines.append("|:---|:---|")
                    for f in cls["fields"]:
                        lines.append(f"| `{f['name']}` | `{f['type']}` |")
                    lines.append("")

                if cls["methods"]:
                    for m in cls["methods"]:
                        doc_part = f" — {m['doc']}" if m["doc"] else ""
                        lines.append(f"- `{m['name']}{m['signature']}`{doc_part}")

            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Target: architecture (CLAUDE.md)
# ---------------------------------------------------------------------------

def _list_modules_for_layer(layer_path: Path, annotations: dict) -> str:
    """List modules in a layer with annotations."""
    if not layer_path.exists():
        return ""

    parts = []
    # Group by subpackage
    subdirs = sorted([d for d in layer_path.iterdir() if d.is_dir() and not d.name.startswith("_")])
    standalone = sorted([f for f in layer_path.iterdir() if f.suffix == ".py" and f.name != "__init__.py" and not f.name.startswith("_")])

    # Subdirectories first
    for d in subdirs:
        rel = str(d.relative_to(ROOT)) + "/__init__.py"
        ann = annotations.get(rel, "")
        name = d.name + "/"
        if ann:
            parts.append(f"{name} ({ann})")
        else:
            parts.append(name)

    # Standalone files
    for f in standalone:
        rel = str(f.relative_to(ROOT))
        ann = annotations.get(rel, "")
        name = f.stem
        if ann:
            parts.append(f"{name} ({ann})")
        else:
            parts.append(name)

    return ", ".join(parts)


def generate_architecture() -> str | None:
    """Generate Architecture section for CLAUDE.md. Returns None if no markers found."""
    content = CLAUDE_MD.read_text()
    if BEGIN_ARCH not in content:
        return None

    annotations = _load_annotations()

    # Count skills
    skill_count = len(list(SKILLS_DIR.glob("*/SKILL.md"))) if SKILLS_DIR.exists() else 0

    # Count presets (nested under 'presets:' key, expects 2-space YAML indent)
    presets_file = ROOT / "config" / "screening_presets.yaml"
    preset_count = 0
    if presets_file.exists():
        in_presets = False
        for line in presets_file.read_text().splitlines():
            if re.match(r"^presets:", line):
                in_presets = True
                continue
            if in_presets and re.match(r"^ {2}\w[\w-]*:", line):
                preset_count += 1
            elif in_presets and re.match(r"^\w", line):
                break

    core_mods = _list_modules_for_layer(SRC / "core", annotations)
    data_mods = _list_modules_for_layer(SRC / "data", annotations)
    output_mods = _list_modules_for_layer(SRC / "output", annotations)

    block = f"""```
Skills (.claude/skills/*/SKILL.md → scripts/*.py) — {skill_count}スキル
Core   (src/core/) — {core_mods}
Data   (src/data/) — {data_mods}
Output (src/output/) — {output_mods}

Config: config/screening_presets.yaml ({preset_count} presets), config/exchanges.yaml (60+ regions)
Rules:  .claude/rules/ (graph-context, intent-routing, workflow, development, screening, portfolio, testing)
Docs:   docs/ (architecture, neo4j-schema, skill-catalog, api-reference, data-models)
```"""

    # Replace between markers
    pattern = re.compile(
        re.escape(BEGIN_ARCH) + r".*?" + re.escape(END_ARCH),
        re.DOTALL,
    )
    new_section = f"{BEGIN_ARCH}\n{block}\n{END_ARCH}"
    new_content = pattern.sub(new_section, content)

    if new_content != content:
        CLAUDE_MD.write_text(new_content)
        return "updated"
    return "unchanged"


# ---------------------------------------------------------------------------
# Target: test-count
# ---------------------------------------------------------------------------

def generate_test_count() -> str | None:
    """Update test count in development.md."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--co", "-q"],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT),
        )
        output = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    # Parse "N tests collected" or "N test collected"
    m = re.search(r"(\d+)\s+tests?\s+collected", output)
    if not m:
        return None

    count = int(m.group(1))

    content = DEV_MD.read_text()
    new_content = re.sub(
        r"約\d+テスト",
        f"約{count}テスト",
        content,
    )
    if new_content != content:
        DEV_MD.write_text(new_content)
        return f"updated to {count}"
    return f"unchanged ({count})"


# ---------------------------------------------------------------------------
# Target: skill-catalog overview
# ---------------------------------------------------------------------------

def _parse_skill_frontmatter(skill_md: Path) -> dict:
    """Parse YAML frontmatter from SKILL.md."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm = text[3:end].strip()
    result = {}
    for line in fm.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.+)$", line)
        if m:
            result[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return result


def generate_skill_catalog() -> str | None:
    """Update Overview table in skill-catalog.md."""
    content = SKILL_CATALOG.read_text()
    if BEGIN_OVERVIEW not in content:
        return None

    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = _parse_skill_frontmatter(skill_md)
        name = fm.get("name", skill_dir.name)
        desc = fm.get("description", "")
        skills.append((name, desc))

    table_lines = [
        "| Skill | Description |",
        "|:---|:---|",
    ]
    for name, desc in skills:
        # Truncate long descriptions
        if len(desc) > 80:
            desc = desc[:77] + "..."
        table_lines.append(f"| {name} | {desc} |")

    table = "\n".join(table_lines)

    pattern = re.compile(
        re.escape(BEGIN_OVERVIEW) + r".*?" + re.escape(END_OVERVIEW),
        re.DOTALL,
    )
    new_section = f"{BEGIN_OVERVIEW}\n{table}\n{END_OVERVIEW}"
    new_content = pattern.sub(new_section, content)

    if new_content != content:
        SKILL_CATALOG.write_text(new_content)
        return "updated"
    return "unchanged"


# ---------------------------------------------------------------------------
# Target: data-models-verify
# ---------------------------------------------------------------------------

def verify_data_models() -> tuple[bool, list[str]]:
    """Verify docs/data-models.md against fixtures.

    Returns (ok, messages).
    """
    messages = []

    if not DATA_MODELS.exists():
        return False, ["docs/data-models.md not found"]

    doc_text = DATA_MODELS.read_text()
    # Extract keys from markdown table rows: | `key` |
    doc_keys = set(re.findall(r"\|\s*`(\w+)`\s*\|", doc_text))

    # Check stock_info fixture
    stock_info_path = FIXTURES / "stock_info.json"
    if stock_info_path.exists():
        with open(stock_info_path) as f:
            fixture_keys = set(json.load(f).keys())
        missing = fixture_keys - doc_keys
        extra = doc_keys - fixture_keys
        if missing:
            messages.append(f"stock_info: keys in fixture but not in doc: {sorted(missing)}")
        # Don't report extra (doc may cover stock_detail keys too)

    # Check stock_detail fixture
    stock_detail_path = FIXTURES / "stock_detail.json"
    if stock_detail_path.exists():
        with open(stock_detail_path) as f:
            detail_keys = set(json.load(f).keys())
        missing = detail_keys - doc_keys
        if missing:
            messages.append(f"stock_detail: keys in fixture but not in doc: {sorted(missing)}")

    ok = len(messages) == 0
    if ok:
        messages.append("data-models.md is in sync with fixtures")
    return ok, messages


# ---------------------------------------------------------------------------
# Target: check (staleness detection)
# ---------------------------------------------------------------------------

def check_staleness(quiet: bool = False) -> int:
    """Check if auto-generated docs are stale. Returns exit code 0/1."""
    stale = []

    # 1. api-reference.md
    new_content = generate_api_reference()
    if not API_REF.exists():
        stale.append("api-reference.md: not found (run 'generate_docs.py api-reference')")
    elif API_REF.read_text() != new_content:
        stale.append("api-reference.md: stale")

    # 2. architecture markers
    content = CLAUDE_MD.read_text()
    if BEGIN_ARCH not in content:
        stale.append("CLAUDE.md: no architecture markers")

    # 3. data-models verify
    ok, msgs = verify_data_models()
    if not ok:
        for m in msgs:
            stale.append(f"data-models: {m}")

    if stale:
        if not quiet:
            for s in stale:
                print(f"  ⚠ {s}")
        else:
            print(f"docs: {len(stale)} stale")
        return 1

    if not quiet:
        print("docs: all up to date")
    return 0


# ---------------------------------------------------------------------------
# Target: all
# ---------------------------------------------------------------------------

def run_all():
    """Run all generators."""
    # api-reference
    content = generate_api_reference()
    _write_if_changed(API_REF, content, "api-reference.md")

    # architecture
    result = generate_architecture()
    if result:
        print(f"  CLAUDE.md Architecture: {result}")
    else:
        print("  CLAUDE.md Architecture: no markers found (skipped)")

    # test-count
    result = generate_test_count()
    if result:
        print(f"  development.md test-count: {result}")
    else:
        print("  development.md test-count: failed")

    # skill-catalog
    result = generate_skill_catalog()
    if result:
        print(f"  skill-catalog.md overview: {result}")
    else:
        print("  skill-catalog.md overview: no markers found (skipped)")

    # data-models verify
    ok, msgs = verify_data_models()
    for m in msgs:
        prefix = "✓" if ok else "⚠"
        print(f"  {prefix} {m}")


def _write_if_changed(path: Path, content: str, label: str):
    """Write file only if content differs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        print(f"  {label}: unchanged")
    else:
        path.write_text(content)
        print(f"  {label}: updated")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "api-reference":
        content = generate_api_reference()
        _write_if_changed(API_REF, content, "api-reference.md")

    elif cmd == "architecture":
        result = generate_architecture()
        print(result or "no markers found")

    elif cmd == "test-count":
        result = generate_test_count()
        print(result or "failed")

    elif cmd == "skill-catalog":
        result = generate_skill_catalog()
        print(result or "no markers found")

    elif cmd == "data-models-verify":
        ok, msgs = verify_data_models()
        for m in msgs:
            print(m)
        sys.exit(0 if ok else 1)

    elif cmd == "all":
        run_all()

    elif cmd == "check":
        quiet = "--quiet" in sys.argv
        sys.exit(check_staleness(quiet))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
