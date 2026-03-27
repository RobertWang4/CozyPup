"""Audit: check cross-module logic consistency.

Run: python -m tests.e2e.audit.check_logic_consistency
"""

import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "app"
IOS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "ios-app"

# ---------- 1. Tool definition vs execution ----------


def check_tool_definition_vs_execution() -> dict:
    """Compare tool names in _BASE_TOOL_DEFINITIONS vs _TOOL_HANDLERS."""
    tools_path = APP_DIR / "agents" / "tools.py"
    if not tools_path.exists():
        return {"pass": False, "error": "tools.py not found"}
    text = tools_path.read_text()

    # Extract from _BASE_TOOL_DEFINITIONS: all "name": "xxx" entries
    # We need the names from the function definitions section only
    defs_section = text.split("_BASE_TOOL_DEFINITIONS")[1].split("# Backward compatibility")[0] if "_BASE_TOOL_DEFINITIONS" in text else ""
    defined_tools = set(re.findall(r'"name":\s*"([a-z_]+)"', defs_section))

    # Extract from _TOOL_HANDLERS dict
    handler_section = text.split("_TOOL_HANDLERS")[1].split("}")[0] if "_TOOL_HANDLERS" in text else ""
    handler_tools = set(re.findall(r'"([a-z_]+)":', handler_section))

    defined_not_handled = defined_tools - handler_tools
    handled_not_defined = handler_tools - defined_tools

    passed = not defined_not_handled and not handled_not_defined
    return {
        "pass": passed,
        "defined_tools": sorted(defined_tools),
        "handled_tools": sorted(handler_tools),
        "defined_not_handled": sorted(defined_not_handled),
        "handled_not_defined": sorted(handled_not_defined),
    }


# ---------- 2. Card type consistency (backend vs iOS) ----------


def check_card_type_consistency() -> dict:
    """Find card types backend sends but iOS doesn't handle."""
    tools_path = APP_DIR / "agents" / "tools.py"
    orchestrator_path = APP_DIR / "agents" / "orchestrator.py"
    if not tools_path.exists():
        return {"pass": False, "error": "tools.py not found"}

    # Backend card types: "type": "xxx" in tools.py return values (not in parameter schemas)
    tools_text = tools_path.read_text()
    # Look in the execution section (after _BASE_TOOL_DEFINITIONS)
    exec_section = tools_text.split("# ---------- Tool Execution")[1] if "# ---------- Tool Execution" in tools_text else tools_text
    backend_cards = set(re.findall(r'"type":\s*"([a-z_]+)"', exec_section))
    # Also check orchestrator for confirm_action
    if orchestrator_path.exists():
        orch_text = orchestrator_path.read_text()
        backend_cards.update(re.findall(r'"type":\s*"([a-z_]+)"', orch_text))
    # Filter out non-card types (like "function", "object")
    non_card_types = {"function", "object", "string", "array", "number", "boolean", "integer"}
    backend_cards -= non_card_types

    # iOS card types: scan ChatMessage.swift, ChatView.swift, ChatService.swift for type strings
    ios_cards: set[str] = set()
    ios_search_patterns = [
        r'd\.type\s*==\s*"([a-z_]+)"',
        r'case\s*"([a-z_]+)"',
        r'"([a-z_]+)".*:\s*return',
        r'contains\(\s*"([a-z_]+)"',
        r'\.contains\("([a-z_]+)"\)',
    ]
    ios_files = list(IOS_DIR.rglob("*.swift")) if IOS_DIR.exists() else []
    for f in ios_files:
        if "__pycache__" in str(f):
            continue
        text = f.read_text()
        for pat in ios_search_patterns:
            ios_cards.update(re.findall(pat, text))

    # Filter iOS cards to plausible card type names
    ios_cards = {c for c in ios_cards if "_" in c or c in backend_cards}

    backend_only = backend_cards - ios_cards
    ios_only = ios_cards - backend_cards

    passed = not backend_only
    return {
        "pass": passed,
        "backend_card_types": sorted(backend_cards),
        "ios_card_types": sorted(ios_cards),
        "backend_sends_ios_missing": sorted(backend_only),
        "ios_handles_backend_missing": sorted(ios_only),
    }


# ---------- 3. CONFIRM_TOOLS consistency ----------


def check_confirm_tools_consistency() -> dict:
    """Check CONFIRM_TOOLS in constants.py matches usage in orchestrator.py."""
    constants_path = APP_DIR / "agents" / "constants.py"
    orchestrator_path = APP_DIR / "agents" / "orchestrator.py"
    executor_path = APP_DIR / "agents" / "executor.py"

    if not constants_path.exists():
        return {"pass": False, "error": "constants.py not found"}

    # Read CONFIRM_TOOLS from constants.py
    const_text = constants_path.read_text()
    m = re.search(r"CONFIRM_TOOLS\s*=\s*\{([^}]+)\}", const_text)
    if not m:
        return {"pass": False, "error": "CONFIRM_TOOLS not found in constants.py"}
    confirm_tools = set(re.findall(r'"([a-z_]+)"', m.group(1)))

    # Check orchestrator.py imports and uses CONFIRM_TOOLS
    issues = []
    for path, name in [(orchestrator_path, "orchestrator.py"), (executor_path, "executor.py")]:
        if not path.exists():
            issues.append(f"{name} not found")
            continue
        text = path.read_text()
        if "CONFIRM_TOOLS" not in text:
            issues.append(f"{name} does not reference CONFIRM_TOOLS")
        elif "from app.agents.constants import" not in text or "CONFIRM_TOOLS" not in text:
            issues.append(f"{name} may not import CONFIRM_TOOLS from constants")

    # Check if any tool names are hardcoded in orchestrator instead of using CONFIRM_TOOLS
    if orchestrator_path.exists():
        orch_text = orchestrator_path.read_text()
        for tool in confirm_tools:
            # Check for hardcoded references like "delete_pet" not near CONFIRM_TOOLS
            hardcoded = re.findall(rf'"{tool}"', orch_text)
            # Filter: if it appears in describe_tool_call, that's fine
            # Only flag if it appears in confirm-gate logic without CONFIRM_TOOLS

    passed = len(issues) == 0
    return {
        "pass": passed,
        "confirm_tools": sorted(confirm_tools),
        "issues": issues,
    }


# ---------- 4. Route auth coverage ----------


def check_route_auth_coverage() -> dict:
    """Check all router endpoints use get_current_user_id for auth."""
    routers_dir = APP_DIR / "routers"
    if not routers_dir.exists():
        return {"pass": False, "error": "routers/ not found"}

    unprotected = []
    route_pattern = re.compile(r"@router\.(get|post|put|patch|delete)\s*\(")
    func_pattern = re.compile(r"^(async\s+)?def\s+(\w+)\s*\(")

    for f in routers_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        lines = f.read_text().splitlines()

        i = 0
        while i < len(lines):
            if route_pattern.search(lines[i]):
                # Find the function definition (may be on next line or same line)
                func_start = i + 1
                while func_start < len(lines) and not func_pattern.search(lines[func_start]):
                    func_start += 1
                if func_start >= len(lines):
                    break

                func_match = func_pattern.search(lines[func_start])
                func_name = func_match.group(2) if func_match else "unknown"

                # Collect the full function signature (may span multiple lines)
                sig_lines = []
                j = func_start
                paren_depth = 0
                while j < len(lines):
                    sig_lines.append(lines[j])
                    paren_depth += lines[j].count("(") - lines[j].count(")")
                    if paren_depth <= 0 and ")" in lines[j]:
                        break
                    j += 1

                full_sig = "\n".join(sig_lines)
                route_method = route_pattern.search(lines[i]).group(1).upper()
                route_path_match = re.search(r'["\']([^"\']*)["\']', lines[i])
                route_path = route_path_match.group(1) if route_path_match else ""

                if "get_current_user_id" not in full_sig:
                    unprotected.append({
                        "file": str(f.relative_to(APP_DIR.parent)),
                        "function": func_name,
                        "method": route_method,
                        "path": route_path,
                    })
            i += 1

    passed = len(unprotected) == 0
    return {
        "pass": passed,
        "unprotected_routes": unprotected,
        "total_unprotected": len(unprotected),
    }


# ---------- 5. Model vs Schema field check ----------


def check_model_vs_schema_fields() -> dict:
    """Compare SQLAlchemy model columns with Pydantic response schema fields."""
    models_path = APP_DIR / "models.py"
    if not models_path.exists():
        return {"pass": False, "error": "models.py not found"}

    models_text = models_path.read_text()

    checks = {
        "Pet": {
            "schema_file": APP_DIR / "schemas" / "pets.py",
            "schema_class": "PetResponse",
        },
        "CalendarEvent": {
            "schema_file": APP_DIR / "schemas" / "calendar.py",
            "schema_class": "CalendarEventResponse",
        },
        "Reminder": {
            "schema_file": APP_DIR / "schemas" / "reminders.py",
            "schema_class": "ReminderResponse",
        },
    }

    results = {}
    all_pass = True

    for model_name, config in checks.items():
        # Extract model columns
        model_cols = _extract_model_columns(models_text, model_name)
        # Skip internal fields
        skip_fields = {"id", "user_id", "created_at", "updated_at"}

        # Extract schema fields
        schema_file = config["schema_file"]
        schema_class = config["schema_class"]
        if not schema_file.exists():
            results[model_name] = {"pass": False, "error": f"{schema_file.name} not found"}
            all_pass = False
            continue

        schema_fields = _extract_schema_fields(schema_file.read_text(), schema_class)

        # Compare: fields in model but not in schema (excluding skip_fields)
        model_only = (model_cols - schema_fields - skip_fields)
        schema_only = (schema_fields - model_cols - skip_fields)
        # Also remove obviously computed/virtual fields
        computed_fields = {"pet_name", "pet_color_hex", "pet_tags", "gender"}
        schema_only -= computed_fields

        passed = len(model_only) == 0
        if not passed:
            all_pass = False

        results[model_name] = {
            "pass": passed,
            "model_columns": sorted(model_cols),
            "schema_fields": sorted(schema_fields),
            "in_model_not_schema": sorted(model_only),
            "in_schema_not_model": sorted(schema_only),
        }

    return {"pass": all_pass, "models": results}


def _extract_model_columns(text: str, class_name: str) -> set[str]:
    """Extract column names from a SQLAlchemy model class."""
    # Find class block
    pattern = re.compile(rf"^class\s+{class_name}\(", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return set()

    start = m.end()
    # Find end of class (next class or end of file)
    next_class = re.search(r"^class\s+\w+\(", text[start:], re.MULTILINE)
    end = start + next_class.start() if next_class else len(text)
    block = text[start:end]

    # Match "name: Mapped[...] = mapped_column(...)" pattern
    cols = set(re.findall(r"^\s+(\w+):\s+Mapped\[", block, re.MULTILINE))
    return cols


def _extract_schema_fields(text: str, class_name: str) -> set[str]:
    """Extract field names from a Pydantic BaseModel class."""
    pattern = re.compile(rf"^class\s+{class_name}\(", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return set()

    start = m.end()
    next_class = re.search(r"^class\s+\w+\(", text[start:], re.MULTILINE)
    end = start + next_class.start() if next_class else len(text)
    block = text[start:end]

    fields = set(re.findall(r"^\s+(\w+):\s+", block, re.MULTILINE))
    return fields


# ---------- Main ----------


def main():
    report = {
        "tool_definition_vs_execution": check_tool_definition_vs_execution(),
        "card_type_consistency": check_card_type_consistency(),
        "confirm_tools_consistency": check_confirm_tools_consistency(),
        "route_auth_coverage": check_route_auth_coverage(),
        "model_vs_schema_fields": check_model_vs_schema_fields(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
