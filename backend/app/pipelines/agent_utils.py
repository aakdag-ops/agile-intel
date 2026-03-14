"""
Shared utilities for agent pipeline steps.
"""
from __future__ import annotations

import json
import re


def extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from Claude's response.
    Handles:
    - Markdown code fences (```json ... ```)
    - Leading/trailing prose
    - Escaped newlines inside strings
    - Truncated responses (finds largest valid JSON object)
    """
    text = text.strip()

    # 1. Strip markdown code fences (beginning and end)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # 2. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find the outermost JSON object { ... }
    start = text.find('{')
    if start == -1:
        raise ValueError(f"No JSON object found in response. Preview: {text[:300]}")

    # Walk from end to find the matching closing brace
    depth = 0
    end = -1
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

    if end == -1:
        # Truncated response — try to repair by closing open braces
        open_count = text.count('{') - text.count('}')
        repaired = text[start:] + ('}' * open_count)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise ValueError(
                f"Could not parse JSON even after repair attempt. "
                f"Error at char ~{len(text)}. Preview: {text[start:start+300]}"
            )

    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error: {e}. Candidate preview: {candidate[:300]}")
