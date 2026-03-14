"""
PBI Generator Agent
-------------------
Takes the Solution Architect's proposal and generates a structured
Product Backlog with Epics, Stories, and Tasks including acceptance
criteria and story point estimates.
"""
from __future__ import annotations

from typing import Any

import anthropic

from app.core.config import settings
from app.core.logging import logger
from app.pipelines.agent_utils import extract_json


async def run(
    issue_key: str,
    issue_summary: str,
    architecture_proposal: str,
    affected_components: list[str],
    new_components: list[str],
    complexity: str,
    technical_approach: str,
) -> dict[str, Any]:
    """
    Returns:
        {
          "epics": [
            {
              "title": str,
              "description": str,
              "stories": [
                {
                  "title": str,
                  "description": str,
                  "acceptance_criteria": [str],
                  "story_points": int,
                  "tasks": [{"title": str, "description": str, "story_points": int}]
                }
              ]
            }
          ],
          "total_story_points": int,
          "summary": str
        }
    """
    logger.info("pbi_generator.start", issue_key=issue_key)

    components_text = ""
    if affected_components:
        components_text += f"\nAffected components: {', '.join(affected_components)}"
    if new_components:
        components_text += f"\nNew components to create: {', '.join(new_components)}"

    prompt = f"""You are a senior Product Owner and Scrum Master. Based on the architecture proposal below, generate a complete Product Backlog in JSON format.

## ORIGINAL REQUEST
{issue_key}: {issue_summary}

## ARCHITECTURE PROPOSAL
{architecture_proposal}

## COMPONENTS
{components_text}
Complexity: {complexity}
Approach: {technical_approach}

## YOUR TASK
Generate a structured backlog with Epics > Stories > Tasks.

Rules:
- Story points use Fibonacci: 1, 2, 3, 5, 8, 13, 21
- Each story MUST have at least 2 acceptance criteria (Given/When/Then format preferred)
- Break complex work into small, independently deliverable stories
- Include technical stories (e.g., migration, infrastructure) alongside feature stories
- Maximum 3 epics; maximum 5 stories per epic

Return ONLY valid JSON:
{{
  "epics": [
    {{
      "title": "<Epic title>",
      "description": "<What this epic covers>",
      "stories": [
        {{
          "title": "<Story title>",
          "description": "<As a ... I want ... so that ...>",
          "acceptance_criteria": ["Given ... When ... Then ...", "..."],
          "story_points": <int>,
          "tasks": [
            {{"title": "<Task title>", "description": "<technical detail>", "story_points": <int>}}
          ]
        }}
      ]
    }}
  ],
  "total_story_points": <int>,
  "summary": "<2-3 sentence overview of the full backlog>"
}}

Return ONLY valid JSON. No markdown fences. No extra text."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = extract_json(message.content[0].text)

    # Recalculate total if needed
    if "epics" in result:
        total = sum(
            story.get("story_points", 0)
            for epic in result["epics"]
            for story in epic.get("stories", [])
        )
        result["total_story_points"] = total

    logger.info(
        "pbi_generator.done",
        issue_key=issue_key,
        epics=len(result.get("epics", [])),
        total_sp=result.get("total_story_points"),
    )
    return result
