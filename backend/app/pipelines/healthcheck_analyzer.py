"""
Backlog Healthcheck Analyzer
Fetches all issues from Jira (last 6 months), scores 11 quality criteria via Claude,
computes column statistics, generates AI insights, top-5 worst items, and concrete actions.
"""
import json
import re
from calendar import monthrange
from datetime import datetime, timezone, timedelta
from statistics import mean
from typing import Any

import anthropic

from app.core.config import settings
from app.core.logging import logger
from app.pipelines.jira_client import JiraClient

# ── Claude singleton ──────────────────────────────────────────────────────────

_client: anthropic.AsyncAnthropic | None = None

def get_claude() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client

CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ── Constants ─────────────────────────────────────────────────────────────────

CRITERIA = [
    "title_clarity",
    "description_quality",
    "acceptance_criteria",
    "estimation",
    "dependencies",
    "customer_focus",
    "data_drivenness",
    "vertical_slicing",
    "product_goal_alignment",
    "okr_alignment",
    "risk_profile",
]

CRITERIA_DEFINITIONS = """
1. title_clarity        — Specific, non-generic title that clearly describes the actual work
2. description_quality  — Meaningful description with scope, context and expected behavior
3. acceptance_criteria  — Clear, testable acceptance criteria explicitly present
4. estimation           — Has story points or size estimate assigned
5. dependencies         — External dependencies, blockers, or integrations identified
6. customer_focus       — User/customer value or benefit clearly stated
7. data_drivenness      — Data, metrics, or evidence backing the need or solution
8. vertical_slicing     — Complete, end-to-end deliverable slice (not just a layer)
9. product_goal_alignment — Connects to a product goal, epic, or roadmap item
10. okr_alignment        — Traceable to an OKR, strategic objective, or outcome
11. risk_profile         — Risks, unknowns, assumptions, or mitigations mentioned
"""

SCORE_VALUES = {"good": 0, "medium": 1, "critical": 2}

# ── Helper: parse Jira description ───────────────────────────────────────────

def _extract_text(node: Any, depth: int = 0) -> str:
    """Recursively extract plain text from Jira Atlassian Document Format."""
    if depth > 10:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        t = node.get("type", "")
        if t == "text":
            return node.get("text", "")
        parts = []
        for child in node.get("content", []):
            parts.append(_extract_text(child, depth + 1))
        return " ".join(p for p in parts if p)
    if isinstance(node, list):
        return " ".join(_extract_text(n, depth + 1) for n in node)
    return ""


def _has_acceptance_criteria(description_text: str) -> bool:
    """Check if description contains acceptance criteria section."""
    lower = description_text.lower()
    keywords = ["acceptance criteria", "ac:", "given ", "when ", "then ", "definition of done"]
    return any(k in lower for k in keywords)


def _extract_story_points(fields: dict) -> float | None:
    """Try multiple custom fields for story points."""
    for field in ("customfield_10016", "customfield_10028", "story_points"):
        val = fields.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _is_active_sprint(sprint_data: Any) -> bool:
    """Check if customfield_10020 (sprint) indicates an active sprint."""
    if not sprint_data:
        return False
    if isinstance(sprint_data, list):
        for s in sprint_data:
            if isinstance(s, dict) and s.get("state") == "active":
                return True
            if isinstance(s, str) and "state=ACTIVE" in s.upper():
                return True
    if isinstance(sprint_data, dict) and sprint_data.get("state") == "active":
        return True
    return False

# ── Step 1: Fetch & Classify ──────────────────────────────────────────────────

def _classify_issues(raw_issues: list[dict]) -> dict[str, list[str]]:
    """
    Classify issue keys into 3 groups:
    - completed_last_month: Done and resolved in the previous calendar month
    - planned_this_month: In an active sprint
    - next_month: Everything else that is not Done
    """
    now = datetime.now(timezone.utc)
    # Previous calendar month boundaries
    first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_this_month - timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    completed, planned, next_month = [], [], []

    for issue in raw_issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        status_cat = (
            fields.get("status", {})
            .get("statusCategory", {})
            .get("key", "")
            .lower()
        )
        resolution_date_str = fields.get("resolutiondate")
        sprint_data = fields.get("customfield_10020")

        if status_cat == "done":
            if resolution_date_str:
                try:
                    rd = datetime.fromisoformat(resolution_date_str.replace("Z", "+00:00"))
                    if last_month_start <= rd <= last_month_end:
                        completed.append(key)
                        continue
                except Exception:
                    pass
            # Done but not last month — skip (too old or this month)
            continue

        if _is_active_sprint(sprint_data):
            planned.append(key)
        else:
            next_month.append(key)

    return {
        "completed_last_month": completed,
        "planned_this_month": planned,
        "next_month": next_month,
    }

# ── Step 2: Lead Time ─────────────────────────────────────────────────────────

def _compute_lead_times(raw_issues: list[dict]) -> dict[str, float | None]:
    """Compute average lead time in days by issue type for Done issues."""
    buckets: dict[str, list[float]] = {"story": [], "bug": [], "task": []}
    all_days: list[float] = []

    for issue in raw_issues:
        fields = issue.get("fields", {})
        status_cat = (
            fields.get("status", {})
            .get("statusCategory", {})
            .get("key", "")
            .lower()
        )
        if status_cat != "done":
            continue
        created_str = fields.get("created")
        resolution_str = fields.get("resolutiondate")
        if not created_str or not resolution_str:
            continue
        try:
            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            resolved_dt = datetime.fromisoformat(resolution_str.replace("Z", "+00:00"))
            days = (resolved_dt - created_dt).total_seconds() / 86400
            if days < 0:
                continue
            all_days.append(days)
            itype = fields.get("issuetype", {}).get("name", "").lower()
            if "bug" in itype:
                buckets["bug"].append(days)
            elif "story" in itype:
                buckets["story"].append(days)
            elif "task" in itype or "sub-task" in itype:
                buckets["task"].append(days)
        except Exception:
            continue

    def avg(lst: list[float]) -> float | None:
        return round(mean(lst), 1) if lst else None

    return {
        "avg": avg(all_days),
        "story": avg(buckets["story"]),
        "bug": avg(buckets["bug"]),
        "task": avg(buckets["task"]),
    }

# ── Step 3: Claude Scoring ────────────────────────────────────────────────────

def _build_issue_summary(issue: dict) -> str:
    """Build compact text representation of an issue for Claude."""
    key = issue["key"]
    f = issue.get("fields", {})
    title = f.get("summary", "")
    itype = f.get("issuetype", {}).get("name", "Unknown")
    sp = _extract_story_points(f)
    sp_str = str(int(sp)) if sp else "None"
    has_links = bool(f.get("issuelinks"))
    labels = ", ".join(f.get("labels", [])) or "None"

    desc_raw = f.get("description") or {}
    desc_text = _extract_text(desc_raw).strip()[:400] if desc_raw else ""
    has_ac = _has_acceptance_criteria(desc_text)

    return (
        f"Key: {key}\n"
        f"Title: {title}\n"
        f"Type: {itype} | Story Points: {sp_str} | Has Links: {has_links} | Has AC: {has_ac}\n"
        f"Labels: {labels}\n"
        f"Description: {desc_text or '(empty)'}"
    )


async def _score_batch(issues: list[dict]) -> dict[str, dict[str, str]]:
    """Send a batch of ≤20 issues to Claude and return {key: {criterion: rating}}."""
    summaries = "\n\n---\n\n".join(_build_issue_summary(i) for i in issues)
    keys = [i["key"] for i in issues]

    prompt = f"""Rate each backlog issue below across ALL 11 criteria.
Return ONLY a valid JSON object mapping each issue key to its scores.
Use exactly these values: "good", "medium", or "critical".

Criteria:
{CRITERIA_DEFINITIONS}

Rating scale:
- "good"     = criterion is well addressed
- "medium"   = criterion is partially addressed or unclear
- "critical" = criterion is completely missing or severely inadequate

Issues to rate:

{summaries}

Required JSON structure (include ALL {len(keys)} keys, ALL 11 criteria per key):
{{
  "ISSUE-KEY": {{
    "title_clarity": "good|medium|critical",
    "description_quality": "good|medium|critical",
    "acceptance_criteria": "good|medium|critical",
    "estimation": "good|medium|critical",
    "dependencies": "good|medium|critical",
    "customer_focus": "good|medium|critical",
    "data_drivenness": "good|medium|critical",
    "vertical_slicing": "good|medium|critical",
    "product_goal_alignment": "good|medium|critical",
    "okr_alignment": "good|medium|critical",
    "risk_profile": "good|medium|critical"
  }}
}}"""

    claude = get_claude()
    response = await claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system="You are a backlog quality analyst. Respond only with valid JSON, no explanation.",
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)

    # Fill in any missing keys/criteria with "critical" as safe default
    result: dict[str, dict[str, str]] = {}
    for key in keys:
        scores = data.get(key, {})
        result[key] = {c: scores.get(c, "critical") for c in CRITERIA}
    return result


async def score_all_items(raw_issues: list[dict]) -> dict[str, dict[str, str]]:
    """Score all issues in batches of 20."""
    all_scores: dict[str, dict[str, str]] = {}
    batch_size = 20
    for i in range(0, len(raw_issues), batch_size):
        batch = raw_issues[i : i + batch_size]
        logger.info("healthcheck.scoring_batch", batch_start=i, batch_size=len(batch))
        try:
            scores = await _score_batch(batch)
            all_scores.update(scores)
        except Exception as exc:
            logger.error("healthcheck.batch_error", error=str(exc), batch_start=i)
            # Fall back to "critical" for all items in failed batch
            for issue in batch:
                all_scores[issue["key"]] = {c: "critical" for c in CRITERIA}
    return all_scores

# ── Step 4: Column Statistics ─────────────────────────────────────────────────

def compute_column_stats(
    item_scores: dict[str, dict[str, str]],
    item_groups: dict[str, list[str]],
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Returns {group: {criterion: {good: pct, medium: pct, critical: pct}}}
    """
    stats: dict = {}
    for group, keys in item_groups.items():
        group_stats: dict = {}
        for criterion in CRITERIA:
            counts = {"good": 0, "medium": 0, "critical": 0}
            for key in keys:
                rating = item_scores.get(key, {}).get(criterion, "critical")
                if rating in counts:
                    counts[rating] += 1
            total = sum(counts.values())
            if total == 0:
                group_stats[criterion] = {"good": 0.0, "medium": 0.0, "critical": 0.0}
            else:
                group_stats[criterion] = {
                    k: round(v / total * 100, 1) for k, v in counts.items()
                }
        stats[group] = group_stats
    return stats

# ── Step 5: AI Insights per Column ───────────────────────────────────────────

async def generate_column_insights(
    column_stats: dict[str, dict[str, dict[str, float]]],
    item_groups: dict[str, list[str]],
) -> dict[str, str]:
    """Generate a short paragraph insight for each status group."""
    group_labels = {
        "completed_last_month": "Completed Last Month",
        "planned_this_month": "Planned This Month",
        "next_month": "Next Month Work List",
    }
    insights: dict[str, str] = {}
    claude = get_claude()

    for group, label in group_labels.items():
        stats = column_stats.get(group, {})
        n = len(item_groups.get(group, []))
        if n == 0:
            insights[group] = "No items in this group for the selected period."
            continue

        lines = []
        for c in CRITERIA:
            s = stats.get(c, {})
            lines.append(
                f"- {c.replace('_', ' ').title()}: "
                f"{s.get('good', 0):.0f}% good / {s.get('medium', 0):.0f}% medium / {s.get('critical', 0):.0f}% critical"
            )
        breakdown = "\n".join(lines)

        prompt = f"""You are analyzing backlog health for "{label}" ({n} items).

Criterion breakdown:
{breakdown}

Write a concise 3-sentence technical insight paragraph that:
1. Identifies the most critical problem areas
2. Explains the impact on delivery
3. Suggests the key priority for improvement

Be direct and actionable. Do not use bullet points."""

        try:
            response = await claude.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            insights[group] = response.content[0].text.strip()
        except Exception as exc:
            logger.error("healthcheck.insight_error", group=group, error=str(exc))
            insights[group] = "Unable to generate insight for this group."

    return insights

# ── Step 6: Top 5 + Concrete Actions ─────────────────────────────────────────

def _find_top_issues(
    item_scores: dict[str, dict[str, str]],
    raw_issues: list[dict],
    n: int = 5,
) -> list[dict]:
    """Return the n issues with the most 'critical' scores."""
    issue_map = {i["key"]: i for i in raw_issues}
    ranked = sorted(
        item_scores.items(),
        key=lambda kv: sum(1 for v in kv[1].values() if v == "critical"),
        reverse=True,
    )
    top = []
    for key, scores in ranked[:n]:
        raw = issue_map.get(key, {})
        summary = raw.get("fields", {}).get("summary", key)
        critical_criteria = [c for c, v in scores.items() if v == "critical"]
        top.append({"key": key, "summary": summary, "critical_criteria": critical_criteria})
    return top


async def generate_top_issues_and_actions(
    top_candidates: list[dict],
    column_stats: dict,
) -> tuple[list[dict], list[str]]:
    """Ask Claude for root cause per top item + 3 concrete actions."""
    if not top_candidates:
        return [], ["Define acceptance criteria for all backlog items.",
                    "Add story points to unestimated items.",
                    "Link items to product goals and OKRs."]

    items_text = "\n".join(
        f"- {t['key']}: {t['summary']} | Missing: {', '.join(t['critical_criteria'][:5])}"
        for t in top_candidates
    )

    # Build a quick summary of worst criteria across all groups
    worst = []
    for group, stats in column_stats.items():
        for c, s in stats.items():
            if s.get("critical", 0) >= 80:
                worst.append(f"{c.replace('_',' ')} ({group}: {s['critical']:.0f}% critical)")
    worst_text = "; ".join(worst[:6]) or "various criteria"

    prompt = f"""You are a backlog quality expert. Based on this analysis:

Most problematic criteria: {worst_text}

Top items needing attention:
{items_text}

Provide:
1. For each item: a 1-2 sentence root cause explanation of WHY it scored so poorly
2. Three concrete, prioritized action items for the team to improve overall backlog quality

Return ONLY valid JSON in this format:
{{
  "root_causes": {{
    "ISSUE-KEY": "root cause explanation"
  }},
  "concrete_actions": [
    "Action 1 description",
    "Action 2 description",
    "Action 3 description"
  ]
}}"""

    claude = get_claude()
    try:
        response = await claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system="Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        root_causes = data.get("root_causes", {})
        actions = data.get("concrete_actions", [])[:3]
    except Exception as exc:
        logger.error("healthcheck.top_issues_error", error=str(exc))
        root_causes = {}
        actions = [
            "Define acceptance criteria for all backlog items.",
            "Add story points to all unestimated items.",
            "Link backlog items to OKRs and product goals.",
        ]

    top_issues = [
        {
            "key": t["key"],
            "summary": t["summary"],
            "root_cause": root_causes.get(t["key"], "Missing key backlog fields across multiple criteria."),
        }
        for t in top_candidates
    ]
    return top_issues, actions

# ── Main entry point ──────────────────────────────────────────────────────────

async def run_healthcheck(
    team_id: str,
    project_key: str,
    months_back: int = 6,
) -> dict:
    """
    Full pipeline. Returns a dict with all report data.
    Raises on unrecoverable errors.
    """
    logger.info("healthcheck.start", team=project_key, months=months_back)
    client = JiraClient()

    # 1. Fetch all issues
    raw_issues = await client.get_issues_for_healthcheck(project_key, months_back)
    logger.info("healthcheck.fetched", count=len(raw_issues))

    if not raw_issues:
        return {
            "status": "complete",
            "total_items": 0,
            "lead_times": {"avg": None, "story": None, "bug": None, "task": None},
            "item_scores": {},
            "item_groups": {"completed_last_month": [], "planned_this_month": [], "next_month": []},
            "column_stats": {},
            "ai_insights": {
                "completed_last_month": "No items found.",
                "planned_this_month": "No items found.",
                "next_month": "No items found.",
            },
            "top_issues": [],
            "concrete_actions": ["Create backlog items to start healthcheck tracking."],
        }

    # 2. Classify
    item_groups = _classify_issues(raw_issues)
    logger.info(
        "healthcheck.classified",
        completed=len(item_groups["completed_last_month"]),
        planned=len(item_groups["planned_this_month"]),
        next_month=len(item_groups["next_month"]),
    )

    # 3. Lead times
    lead_times = _compute_lead_times(raw_issues)

    # 4. Score (only items that appear in one of the 3 groups)
    keys_to_score = set(
        item_groups["completed_last_month"]
        + item_groups["planned_this_month"]
        + item_groups["next_month"]
    )
    issues_to_score = [i for i in raw_issues if i["key"] in keys_to_score]
    item_scores = await score_all_items(issues_to_score)

    # 5. Column stats
    column_stats = compute_column_stats(item_scores, item_groups)

    # 6. AI insights
    ai_insights = await generate_column_insights(column_stats, item_groups)

    # 7. Top 5 + actions
    top_candidates = _find_top_issues(item_scores, issues_to_score, n=5)
    top_issues, concrete_actions = await generate_top_issues_and_actions(top_candidates, column_stats)

    logger.info("healthcheck.complete", team=project_key, scored=len(item_scores))

    return {
        "status": "complete",
        "total_items": len(issues_to_score),
        "lead_times": lead_times,
        "item_scores": item_scores,
        "item_groups": {k: list(v) for k, v in item_groups.items()},
        "column_stats": column_stats,
        "ai_insights": ai_insights,
        "top_issues": top_issues,
        "concrete_actions": concrete_actions,
    }
