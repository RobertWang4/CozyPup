"""Audit: scan for potential runtime risks.

Run: python -m tests.e2e.audit.check_risks
"""

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "app"

# ---------- 1. Exception handling coverage ----------


def check_exception_handling() -> list[dict]:
    """Find async functions in routers/agents that interact with external services but lack try/except."""
    external_indicators = [
        "await db.",
        "await litellm.",
        "await session.",
        "acompletion",
        "httpx",
        "aiohttp",
        "requests.",
        "execute_tool",
        "db.commit",
        "db.execute",
    ]

    results = []
    scan_dirs = [APP_DIR / "routers", APP_DIR / "agents"]

    for d in scan_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.py"):
            if f.name == "__init__.py":
                continue
            text = f.read_text()
            functions = _extract_async_functions(text)

            for func_name, func_body, line_no in functions:
                has_external = any(ind in func_body for ind in external_indicators)
                has_try_except = "try:" in func_body and "except" in func_body

                if has_external and not has_try_except:
                    # Determine which external services
                    services = []
                    if any(x in func_body for x in ["await db.", "db.commit", "db.execute"]):
                        services.append("database")
                    if any(x in func_body for x in ["litellm", "acompletion"]):
                        services.append("LLM")
                    if any(x in func_body for x in ["httpx", "aiohttp", "requests."]):
                        services.append("HTTP")
                    if "execute_tool" in func_body:
                        services.append("tool_execution")

                    results.append({
                        "file": str(f.relative_to(APP_DIR.parent)),
                        "function": func_name,
                        "line": line_no,
                        "services": services,
                    })

    return results


def _extract_async_functions(text: str) -> list[tuple[str, str, int]]:
    """Extract (name, body, line_number) of async functions from Python source."""
    lines = text.splitlines()
    functions = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)async\s+def\s+(\w+)\s*\(", lines[i])
        if m:
            indent = len(m.group(1))
            func_name = m.group(2)
            start_line = i + 1
            body_lines = [lines[i]]
            j = i + 1
            while j < len(lines):
                line = lines[j]
                # Function ends when we hit a line with same or less indent (non-empty)
                stripped = line.strip()
                if stripped and not line.startswith(" " * (indent + 1)) and not line.startswith("\t" * (indent + 1)):
                    # Check it's actually a dedent (not a blank line)
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= indent and stripped:
                        break
                body_lines.append(line)
                j += 1
            functions.append((func_name, "\n".join(body_lines), start_line))
            i = j
        else:
            i += 1
    return functions


# ---------- 2. Cascade delete check ----------


def check_cascade_deletes() -> list[dict]:
    """Find ForeignKey definitions without ondelete cascade settings."""
    models_path = APP_DIR / "models.py"
    if not models_path.exists():
        return []

    text = models_path.read_text()
    results = []

    # Find all ForeignKey definitions
    for i, line in enumerate(text.splitlines(), 1):
        fk_match = re.search(r'ForeignKey\s*\(\s*"([^"]+)"', line)
        if fk_match:
            fk_target = fk_match.group(1)
            has_ondelete = "ondelete=" in line
            col_match = re.match(r"\s+(\w+):", line)
            col_name = col_match.group(1) if col_match else "unknown"

            if not has_ondelete:
                results.append({
                    "line": i,
                    "column": col_name,
                    "foreign_key": fk_target,
                    "issue": "no ondelete policy - could create orphan rows",
                })
            else:
                ondelete_match = re.search(r'ondelete="(\w+)"', line)
                if ondelete_match:
                    policy = ondelete_match.group(1)
                    if policy not in ("CASCADE", "SET NULL"):
                        results.append({
                            "line": i,
                            "column": col_name,
                            "foreign_key": fk_target,
                            "ondelete": policy,
                            "issue": f"unusual ondelete policy: {policy}",
                        })

    return results


# ---------- 3. Missing environment variables ----------


def check_missing_env_vars() -> list[dict]:
    """Find config settings with no default value (required env vars)."""
    config_path = APP_DIR / "config.py"
    if not config_path.exists():
        return []

    text = config_path.read_text()
    results = []

    # Find class Settings block
    in_settings = False
    for i, line in enumerate(text.splitlines(), 1):
        if "class Settings" in line:
            in_settings = True
            continue
        if in_settings and line.strip().startswith("class "):
            break
        if not in_settings:
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("class "):
            continue

        # Match field definitions: name: type = default or name: type
        field_match = re.match(r"(\w+):\s*(\w+)(\s*=\s*(.+))?", stripped)
        if field_match:
            name = field_match.group(1)
            has_default = field_match.group(3) is not None
            default_val = field_match.group(4).strip() if has_default else None

            if not has_default:
                results.append({
                    "variable": name,
                    "line": i,
                    "has_default": False,
                    "risk": "high - app will crash if not set",
                })
            elif default_val in ('""', "''", '""'):
                results.append({
                    "variable": name,
                    "line": i,
                    "has_default": True,
                    "default": "empty string",
                    "risk": "medium - feature disabled if not set",
                })

    return results


# ---------- 4. Pagination check ----------


def check_pagination() -> list[dict]:
    """Find GET list endpoints without pagination parameters."""
    routers_dir = APP_DIR / "routers"
    if not routers_dir.exists():
        return []

    results = []
    route_pattern = re.compile(r"@router\.get\s*\(")

    for f in routers_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        lines = f.read_text().splitlines()

        i = 0
        while i < len(lines):
            if route_pattern.search(lines[i]):
                # Check response model for list
                route_line = lines[i]
                is_list = "list[" in route_line or "List[" in route_line

                # Find function signature
                func_start = i + 1
                while func_start < len(lines):
                    if re.match(r"^(async\s+)?def\s+", lines[func_start]):
                        break
                    func_start += 1

                if func_start < len(lines):
                    func_match = re.match(r"^(async\s+)?def\s+(\w+)", lines[func_start])
                    func_name = func_match.group(2) if func_match else "unknown"

                    # Collect full signature
                    sig = ""
                    j = func_start
                    while j < len(lines):
                        sig += lines[j]
                        if ")" in lines[j] and ":" in lines[j]:
                            break
                        j += 1

                    has_pagination = any(p in sig for p in ["limit", "offset", "page", "skip", "cursor"])
                    has_date_filter = any(p in sig for p in ["start_date", "end_date", "date"])

                    if is_list and not has_pagination and not has_date_filter:
                        results.append({
                            "file": str(f.relative_to(APP_DIR.parent)),
                            "function": func_name,
                            "line": func_start + 1,
                            "issue": "GET list endpoint without pagination or date filter - could return unbounded results",
                        })
            i += 1

    return results


# ---------- 5. File upload validation ----------


def check_file_upload_validation() -> list[dict]:
    """Find file upload endpoints and check for size/type validation."""
    results = []
    scan_dirs = [APP_DIR / "routers", APP_DIR / "agents"]

    for d in scan_dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            text = f.read_text()

            # Find functions that accept UploadFile or process base64 images
            upload_funcs = re.findall(r"(async\s+)?def\s+(\w+)[^:]*UploadFile", text)
            base64_funcs = re.findall(r"(async\s+)?def\s+(\w+)[^:]*base64", text)

            for _, func_name in upload_funcs:
                # Extract function body
                func_body = _get_function_body(text, func_name)
                has_size_check = any(x in func_body for x in ["len(content)", "file.size", "MAX_FILE_SIZE", "5 * 1024"])
                has_type_check = any(x in func_body for x in ["content_type", "ALLOWED_TYPES", "image/jpeg"])

                issues = []
                if not has_size_check:
                    issues.append("no file size validation")
                if not has_type_check:
                    issues.append("no content type validation")

                if issues:
                    results.append({
                        "file": str(f.relative_to(APP_DIR.parent)),
                        "function": func_name,
                        "upload_type": "UploadFile",
                        "issues": issues,
                    })

            # Check base64 image handling in agent tools
            if "base64.b64decode" in text or "base64_decode" in text:
                # Find functions that decode base64
                for m in re.finditer(r"(async\s+)?def\s+(\w+)", text):
                    func_name = m.group(2)
                    func_body = _get_function_body(text, func_name)
                    if "b64decode" not in func_body and "base64" not in func_body:
                        continue
                    has_size_check = any(x in func_body for x in ["len(image_data)", "len(content)", "5 * 1024"])
                    if not has_size_check:
                        results.append({
                            "file": str(f.relative_to(APP_DIR.parent)),
                            "function": func_name,
                            "upload_type": "base64",
                            "issues": ["no decoded size validation"],
                        })

    return results


def _get_function_body(text: str, func_name: str) -> str:
    """Get the body of a function by name."""
    pattern = re.compile(rf"(async\s+)?def\s+{re.escape(func_name)}\s*\(")
    m = pattern.search(text)
    if not m:
        return ""
    start = m.start()
    lines = text[start:].splitlines()
    if not lines:
        return ""

    # Determine indent of def line
    first_line = lines[0]
    indent = len(first_line) - len(first_line.lstrip())

    body = [first_line]
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and not line.startswith(" " * (indent + 1)):
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent and stripped:
                break
        body.append(line)
    return "\n".join(body)


# ---------- Risk categorization ----------


def categorize_risks(report: dict) -> dict:
    """Categorize findings into high/medium/low risk."""
    high_risk = []
    medium_risk = []
    low_risk = []

    # Exception handling: functions touching DB/LLM without try/except are medium risk
    for item in report.get("exception_handling", []):
        if "LLM" in item.get("services", []) or "HTTP" in item.get("services", []):
            high_risk.append({"category": "exception_handling", **item})
        else:
            medium_risk.append({"category": "exception_handling", **item})

    # Cascade deletes: missing cascade is medium risk
    for item in report.get("cascade_deletes", []):
        medium_risk.append({"category": "cascade_delete", **item})

    # Missing env vars: required vars without defaults are high risk
    for item in report.get("env_vars", []):
        if item.get("risk", "").startswith("high"):
            high_risk.append({"category": "env_var", **item})
        else:
            medium_risk.append({"category": "env_var", **item})

    # Pagination: unbounded lists are medium risk
    for item in report.get("pagination", []):
        medium_risk.append({"category": "pagination", **item})

    # File upload: missing validation is high risk
    for item in report.get("file_uploads", []):
        if "no file size validation" in item.get("issues", []):
            high_risk.append({"category": "file_upload", **item})
        else:
            low_risk.append({"category": "file_upload", **item})

    return {
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "summary": {
            "high": len(high_risk),
            "medium": len(medium_risk),
            "low": len(low_risk),
            "total": len(high_risk) + len(medium_risk) + len(low_risk),
        },
    }


# ---------- Main ----------


def main():
    raw_report = {
        "exception_handling": check_exception_handling(),
        "cascade_deletes": check_cascade_deletes(),
        "env_vars": check_missing_env_vars(),
        "pagination": check_pagination(),
        "file_uploads": check_file_upload_validation(),
    }

    categorized = categorize_risks(raw_report)
    output = {
        **categorized,
        "details": raw_report,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
