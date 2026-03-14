"""
Backlog Dispatcher & Follow-up Agent
-------------------------------------
Takes the generated PBIs and dependency map, optionally creates Jira issues,
and produces a dispatch plan with follow-up monitoring recommendations.
"""
from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from app.core.config import settings
from app.core.logging import logger
from app.pipelines.jira_client import JiraClient


async def _create_jira_issues(
    jira: JiraClient,
    project_key: str,
    epics: list[dict],
    recommended_sequence: list[str],
) -> list[dict]:
    """Creates Epics and Stories in Jira and returns created issue keys."""
    created = []

    for epic in epics:
        # Create epic
        try:
            epic_issue = await jira.create_issue(
                project_key=project_key,
                issue_type="Epic",
                summary=epic["title"],
                description=epic.get("description", ""),
            )
            epic_key = epic_issue.get("key", "")
            created.append({"type": "Epic", "key": epic_key, "title": epic["title"]})

            # Create stories under epic
            for story in epic.get("stories", []):
                story_issue = await jira.create_issue(
                    project_key=project_key,
                    issue_type="Story",
                    summary=story["title"],
                    description=_format_story_description(story),
                    story_points=story.get("story_points"),
                    epic_key=epic_key,
                )
                story_key = story_issue.get("key", "")
                created.append({"type": "Story", "key": story_key, "title": story["title"]})
        except Exception as e:
            logger.error("jira.create_issue.failed", epic=epic["title"], error=str(e))

    return created


def _format_story_description(story: dict) -> str:
    lines = [story.get("description", "")]
    acs = story.get("acceptance_criteria", [])
    if acs:
        lines.append("\n*Acceptance Criteria:*")
        for ac in acs:
            lines.append(f"* {ac}")
    return "\n".join(lines)


async def run(
    issue_key: str,
    issue_summary: str,
    epics: list[dict],
    dependency_result: dict,
    auto_create: bool,
    target_project_key: str | None,
    jira_client: JiraClient | None,
) -> dict[str, Any]:
    """
    Returns:
        {
          "dispatch_plan": str,           # Markdown dispatch plan
          "sprint_recommendations": [     # Which stories go in which sprint
            {"sprint": 1, "stories": [str], "total_sp": int}
          ],
          "created_issues": [...],        # If auto_create=True
          "follow_up_checklist": [str],
          "definition_of_done": [str],
          "success_metrics": [str]
        }
    """
    logger.info("backlog_dispatcher.start", issue_key=issue_key, auto_create=auto_create)

    total_sp = sum(
        story.get("story_points", 0)
        for epic in epics
        for story in epic.get("stories", [])
    )
    recommended_sequence = dependency_result.get("recommended_sequence", [])
    blockers = dependency_result.get("blockers", [])
    risk_level = dependency_result.get("total_risk_level", "medium")

    stories_for_prompt = [
        f"  - {s['title']} ({s.get('story_points',0)}sp)" + (
            f" [BLOCKED: needs existing issue]"
            if any(d.get("story") == s["title"] for d in dependency_result.get("external_dependencies", []))
            else ""
        )
        for epic in epics
        for s in epic.get("stories", [])
    ]

    prompt = f"""You are a Scrum Master and Delivery Lead. Create a sprint dispatch plan for the following backlog.

## CONTEXT
Original request: {issue_key} - {issue_summary}
Total story points: {total_sp}
Risk level: {risk_level}
Blockers: {', '.join(blockers) if blockers else 'none'}

## STORIES (in recommended sequence)
{chr(10).join(stories_for_prompt)}

## RECOMMENDED SEQUENCE
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(recommended_sequence))}

## YOUR TASK
Create:
1. Sprint allocation plan (assume 20-30 SP capacity per sprint)
2. Follow-up monitoring checklist
3. Definition of Done criteria
4. Success metrics

Return ONLY valid JSON:
{{
  "dispatch_plan": "<Markdown delivery plan with phases and milestones>",
  "sprint_recommendations": [
    {{"sprint": 1, "stories": ["<story title>"], "total_sp": <int>, "goal": "<sprint goal>"}}
  ],
  "follow_up_checklist": [
    "<specific follow-up action>"
  ],
  "definition_of_done": [
    "<DoD criterion>"
  ],
  "success_metrics": [
    "<measurable success metric>"
  ]
}}

Return ONLY valid JSON. No markdown fences. No extra text."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    result = json.loads(raw)

    created_issues = []
    if auto_create and jira_client and target_project_key:
        logger.info("backlog_dispatcher.creating_jira_issues", project=target_project_key)
        created_issues = await _create_jira_issues(
            jira_client, target_project_key, epics, recommended_sequence
        )

    result["created_issues"] = created_issues
    result["auto_created"] = auto_create and bool(created_issues)

    logger.info(
        "backlog_dispatcher.done",
        issue_key=issue_key,
        sprints=len(result.get("sprint_recommendations", [])),
        created=len(created_issues),
    )
    return result
