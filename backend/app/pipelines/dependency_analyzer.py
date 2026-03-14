"""
Dependency Agent
----------------
Analyses generated PBIs against existing Jira issues to identify
cross-dependencies, ordering constraints, and blockers.
"""
from __future__ import annotations

from typing import Any

import anthropic

from app.core.config import settings
from app.core.logging import logger
from app.pipelines.agent_utils import extract_json


def _summarise_existing(existing_issues: list[dict]) -> str:
    if not existing_issues:
        return "No existing open issues."

    in_progress = [i for i in existing_issues if "progress" in i.get("status_category", "").lower()]
    blocked = [i for i in existing_issues if i.get("is_blocked")]
    sample = existing_issues[:30]

    lines = []
    if in_progress:
        lines.append("IN-PROGRESS ISSUES:")
        for i in in_progress[:10]:
            lines.append(f"  [{i['issue_key']}] {i['summary'][:80]} (assignee: {i.get('assignee_name','unassigned')})")
    if blocked:
        lines.append("\nBLOCKED ISSUES:")
        for i in blocked[:5]:
            lines.append(f"  [{i['issue_key']}] {i['summary'][:80]}")
    lines.append("\nOPEN BACKLOG (sample):")
    for i in sample:
        sp = f" ({i['story_points']}sp)" if i.get("story_points") else ""
        lines.append(f"  [{i['issue_key']}] {i.get('issue_type','?')} - {i['summary'][:70]}{sp}")

    return "\n".join(lines)


def _flatten_stories(epics: list[dict]) -> list[dict]:
    stories = []
    for epic in epics:
        for story in epic.get("stories", []):
            stories.append({
                "epic": epic["title"],
                "title": story["title"],
                "description": story.get("description", ""),
                "story_points": story.get("story_points", 0),
            })
    return stories


async def run(
    issue_key: str,
    epics: list[dict],
    existing_issues: list[dict],
) -> dict[str, Any]:
    """
    Returns:
        {
          "internal_dependencies": [
            {"from_story": str, "to_story": str, "type": "blocks|relates_to", "reason": str}
          ],
          "external_dependencies": [
            {"story": str, "existing_issue_key": str, "type": "blocked_by|relates_to", "reason": str}
          ],
          "recommended_sequence": [str],   # ordered list of story titles
          "risk_assessment": str,
          "blockers": [str],
          "total_risk_level": "low|medium|high|critical"
        }
    """
    logger.info("dependency_analyzer.start", issue_key=issue_key)

    stories = _flatten_stories(epics)
    stories_text = "\n".join(
        f"  STORY-{i+1}: [{s['epic']}] {s['title']} ({s['story_points']}sp)\n    {s['description'][:120]}"
        for i, s in enumerate(stories)
    )
    existing_context = _summarise_existing(existing_issues)

    prompt = f"""You are a senior Scrum Master and Dependency Analyst. Analyse the new backlog items and identify dependencies with each other and with existing open work.

## NEW BACKLOG (from request {issue_key})
{stories_text}

## EXISTING OPEN ISSUES IN PROJECT
{existing_context}

## YOUR TASK
Identify:
1. Internal dependencies between the NEW stories (which must be done before which)
2. External dependencies on EXISTING issues (does any new story require an existing issue to be done first?)
3. Recommended delivery sequence
4. Risks and blockers

Return ONLY valid JSON:
{{
  "internal_dependencies": [
    {{"from_story": "<story title>", "to_story": "<story title>", "type": "blocks", "reason": "<why>"}}
  ],
  "external_dependencies": [
    {{"story": "<new story title>", "existing_issue_key": "<PROJ-123>", "type": "blocked_by", "reason": "<why>"}}
  ],
  "recommended_sequence": ["<story title in recommended order>"],
  "risk_assessment": "<paragraph describing overall risk>",
  "blockers": ["<blocker description>"],
  "total_risk_level": "<low|medium|high|critical>"
}}

Return ONLY valid JSON. No markdown fences. No extra text."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = extract_json(message.content[0].text)
    logger.info(
        "dependency_analyzer.done",
        issue_key=issue_key,
        internal_deps=len(result.get("internal_dependencies", [])),
        external_deps=len(result.get("external_dependencies", [])),
        risk=result.get("total_risk_level"),
    )
    return result
