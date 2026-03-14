"""
Solution Architect Agent
------------------------
Analyses existing architecture (GitHub repo + Jira epics/DB context) and
produces an architecture proposal for a new incoming request.
"""
from __future__ import annotations

import base64
import re
from typing import Any

import anthropic
import httpx

from app.core.config import settings
from app.core.logging import logger


async def _fetch_github_context(repo_url: str, token: str | None) -> dict[str, str]:
    """Fetch README and key files from a GitHub repo to understand architecture."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    # Parse owner/repo from URL
    match = re.search(r"github\.com[/:]([^/]+)/([^/.\s]+)", repo_url)
    if not match:
        return {"error": f"Cannot parse GitHub URL: {repo_url}"}

    owner, repo = match.group(1), match.group(2).rstrip(".git")
    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    files: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        # Fetch README
        try:
            r = await client.get(f"{api_base}/readme", headers=headers)
            if r.status_code == 200:
                content = r.json().get("content", "")
                files["README.md"] = base64.b64decode(content).decode("utf-8", errors="replace")[:4000]
        except Exception as e:
            logger.warning("github.readme.fetch_failed", error=str(e))

        # Fetch root directory listing
        try:
            r = await client.get(f"{api_base}/contents", headers=headers)
            if r.status_code == 200:
                entries = r.json()
                dir_tree = "\n".join(
                    f"{'[DIR]' if e['type'] == 'dir' else '[FILE]'} {e['name']}"
                    for e in entries
                )
                files["_root_structure"] = dir_tree
        except Exception as e:
            logger.warning("github.contents.fetch_failed", error=str(e))

        # Try to fetch key architectural files
        key_files = [
            "docker-compose.yml", "docker-compose.yaml",
            "requirements.txt", "package.json",
            "pyproject.toml", "Makefile",
        ]
        for fname in key_files:
            try:
                r = await client.get(f"{api_base}/contents/{fname}", headers=headers)
                if r.status_code == 200:
                    content = r.json().get("content", "")
                    decoded = base64.b64decode(content).decode("utf-8", errors="replace")[:2000]
                    files[fname] = decoded
            except Exception:
                pass

    return files


def _build_jira_context(existing_issues: list[dict]) -> str:
    if not existing_issues:
        return "No existing issues available."

    epics = [i for i in existing_issues if i.get("issue_type", "").lower() == "epic"]
    recent = existing_issues[:20]

    lines = []
    if epics:
        lines.append("EXISTING EPICS:")
        for e in epics[:10]:
            lines.append(f"  [{e['issue_key']}] {e['summary']} ({e['status']})")
    lines.append("\nRECENT ISSUES (sample):")
    for i in recent:
        lines.append(f"  [{i['issue_key']}] {i.get('issue_type','?')} - {i['summary']} ({i['status']})")

    return "\n".join(lines)


async def run(
    issue_key: str,
    issue_summary: str,
    issue_description: str,
    existing_issues: list[dict],
    github_repo_url: str | None,
    github_token: str | None,
) -> dict[str, Any]:
    """
    Returns:
        {
          "architecture_proposal": str,  # Markdown text
          "affected_components": list[str],
          "new_components": list[str],
          "complexity": "low|medium|high|very_high",
          "technical_approach": str,
          "estimated_effort_days": int | None,
          "risks": list[str],
          "github_context_used": bool,
        }
    """
    logger.info("solution_architect.start", issue_key=issue_key)

    github_context = ""
    github_context_used = False
    if github_repo_url:
        files = await _fetch_github_context(github_repo_url, github_token)
        if files and "error" not in files:
            github_context_used = True
            parts = [f"\n### {name}\n```\n{content}\n```" for name, content in files.items()]
            github_context = "\n".join(parts)

    jira_context = _build_jira_context(existing_issues)

    prompt = f"""You are a senior Solution Architect. Analyse the following new feature request and the existing system context, then produce a clear architecture proposal.

## NEW REQUEST
Issue: {issue_key}
Summary: {issue_summary}
Description:
{issue_description or '(no description provided)'}

## EXISTING JIRA PROJECT CONTEXT
{jira_context}

{'## GITHUB REPOSITORY CONTEXT' + github_context if github_context else ''}

## YOUR TASK
Produce a structured architecture proposal in JSON with these exact fields:
{{
  "architecture_proposal": "<detailed markdown describing the proposed changes>",
  "affected_components": ["<list of existing components/modules that will be modified>"],
  "new_components": ["<list of new components/modules to create>"],
  "complexity": "<low|medium|high|very_high>",
  "technical_approach": "<concise paragraph on implementation strategy>",
  "estimated_effort_days": <integer or null>,
  "risks": ["<potential technical risk 1>", "..."]
}}

Return ONLY valid JSON. No markdown fences. No extra text."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = message.content[0].text.strip()
    # Strip potential markdown fences
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    result = json.loads(raw)
    result["github_context_used"] = github_context_used
    logger.info("solution_architect.done", issue_key=issue_key, complexity=result.get("complexity"))
    return result
