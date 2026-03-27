"""Audit: scan backend for potentially dead/unused code.

Run: python -m tests.e2e.audit.check_dead_code
"""

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "app"

# ---------- 1. Unused tool definitions ----------


def check_unused_tools() -> list[dict]:
    """Find tools defined in TOOL_DEFINITIONS but not dispatched in _TOOL_HANDLERS."""
    tools_path = APP_DIR / "agents" / "tools.py"
    if not tools_path.exists():
        return []
    text = tools_path.read_text()

    # Extract tool names from _BASE_TOOL_DEFINITIONS
    defined = set(re.findall(r'"name":\s*"([a-z_]+)"', text))

    # Extract handler names from _TOOL_HANDLERS dict
    handler_block = text.split("_TOOL_HANDLERS")[1] if "_TOOL_HANDLERS" in text else ""
    dispatched = set(re.findall(r'"([a-z_]+)":', handler_block.split("}")[0]))

    unused = defined - dispatched
    return [{"tool": t, "status": "defined_but_not_dispatched"} for t in sorted(unused)]


# ---------- 2. Unused schemas ----------


def check_unused_schemas() -> list[dict]:
    """Find Pydantic schema classes not referenced in routers/ or agents/."""
    schemas_dir = APP_DIR / "schemas"
    if not schemas_dir.exists():
        return []

    # Collect all schema class names with their source file
    schema_classes: list[tuple[str, str]] = []
    for f in schemas_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            m = re.match(r"^class\s+(\w+)\s*\(", line)
            if m:
                schema_classes.append((m.group(1), str(f.relative_to(APP_DIR.parent))))

    # Search areas: routers/, agents/, main.py
    search_dirs = [APP_DIR / "routers", APP_DIR / "agents"]
    search_files = [APP_DIR / "main.py"]

    search_text = ""
    for d in search_dirs:
        if d.exists():
            for f in d.glob("*.py"):
                search_text += f.read_text() + "\n"
    for f in search_files:
        if f.exists():
            search_text += f.read_text() + "\n"

    unused = []
    for cls_name, src_file in schema_classes:
        if cls_name not in search_text:
            unused.append({"schema": cls_name, "file": src_file})
    return unused


# ---------- 3. Unused imports ----------


def check_unused_imports() -> list[dict]:
    """Find imports where the imported name never appears in the rest of the file."""
    results = []

    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        lines = py_file.read_text().splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            # Skip comments
            if stripped.startswith("#"):
                continue

            # Extract imported names
            imported_names = _extract_import_names(stripped)
            rest_of_file = "\n".join(lines[i:])  # lines after the import

            for name in imported_names:
                # Skip _ imports, star imports, and invalid names (parens from multi-line imports)
                if name == "*" or name.startswith("_") or not name.isidentifier():
                    continue
                # Check if name appears anywhere else in the file (excluding this import line)
                # Use word boundary check
                pattern = re.compile(r"\b" + re.escape(name) + r"\b")
                if not pattern.search(rest_of_file):
                    results.append({
                        "file": str(py_file.relative_to(APP_DIR.parent)),
                        "line": i,
                        "import": name,
                    })

    return results


def _extract_import_names(line: str) -> list[str]:
    """Extract the imported symbol names from an import line."""
    # Strip inline comments
    if "#" in line:
        line = line[:line.index("#")].rstrip()
    # from X import A, B, C
    m = re.match(r"from\s+\S+\s+import\s+(.+)", line)
    if m:
        imports_str = m.group(1)
        # Handle "as" aliases
        names = []
        for part in imports_str.split(","):
            part = part.strip().rstrip("\\")
            if " as " in part:
                names.append(part.split(" as ")[-1].strip())
            else:
                names.append(part.strip())
        return [n for n in names if n]

    # import X, Y
    m = re.match(r"import\s+(.+)", line)
    if m:
        names = []
        for part in m.group(1).split(","):
            part = part.strip()
            if " as " in part:
                names.append(part.split(" as ")[-1].strip())
            else:
                # For "import os.path", the usable name is "os"
                names.append(part.split(".")[0].strip())
        return [n for n in names if n]

    return []


# ---------- 4. Code markers ----------


def check_code_markers() -> list[dict]:
    """Find TODO, FIXME, HACK, DEPRECATED, XXX comments."""
    markers = []
    pattern = re.compile(r"#\s*(TODO|FIXME|HACK|DEPRECATED|XXX)\b(.*)", re.IGNORECASE)

    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        for i, line in enumerate(py_file.read_text().splitlines(), 1):
            m = pattern.search(line)
            if m:
                markers.append({
                    "file": str(py_file.relative_to(APP_DIR.parent)),
                    "line": i,
                    "marker": m.group(1).upper(),
                    "content": m.group(0).strip(),
                })

    return markers


# ---------- 5. Commented-out code ----------


def check_commented_code() -> list[dict]:
    """Find blocks of 3+ consecutive comment lines that look like code."""
    code_indicators = re.compile(
        r"(^#\s*(def |class |import |from |return |if |for |while |elif |else:|try:|except |"
        r"async |await |raise |with |yield |assert |pass$|break$|continue$|"
        r"\w+\s*=\s*|self\.|logger\.|print\(|#\s*\w+\()"
        r")",
    )
    results = []

    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        lines = py_file.read_text().splitlines()

        block_start = None
        block_code_count = 0
        block_total = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 2:
                if block_start is None:
                    block_start = i
                    block_code_count = 0
                    block_total = 0
                block_total += 1
                if code_indicators.search(stripped):
                    block_code_count += 1
            else:
                if block_start is not None and block_total >= 3 and block_code_count >= 2:
                    preview_lines = lines[block_start - 1 : block_start + 2]
                    results.append({
                        "file": str(py_file.relative_to(APP_DIR.parent)),
                        "start_line": block_start,
                        "end_line": block_start + block_total - 1,
                        "preview": "\n".join(preview_lines),
                    })
                block_start = None

        # Check end of file
        if block_start is not None and block_total >= 3 and block_code_count >= 2:
            preview_lines = lines[block_start - 1 : block_start + 2]
            results.append({
                "file": str(py_file.relative_to(APP_DIR.parent)),
                "start_line": block_start,
                "end_line": block_start + block_total - 1,
                "preview": "\n".join(preview_lines),
            })

    return results


# ---------- Main ----------


def main():
    report = {
        "unused_tools": check_unused_tools(),
        "unused_schemas": check_unused_schemas(),
        "unused_imports": check_unused_imports(),
        "code_markers": check_code_markers(),
        "commented_code": check_commented_code(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
