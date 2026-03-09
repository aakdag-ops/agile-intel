"""
Jira Cloud sync pipeline.
Runs every N minutes to pull issues, sprints, and transition history
into PostgreSQL for risk scoring.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.models import IssueTransition, JiraIssue, Sprint, Team
from app.pipelines.jira_client import JiraClient


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Jira returns ISO 8601 with timezone offset
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_story_points(fields: dict) -> float | None:
    """Story points live in customfield_10016 in most Jira configurations."""
    for field in ("customfield_10016", "customfield_10028", "story_points"):
        val = fields.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _extract_issue_links(raw_links: list[dict]) -> dict:
    """Normalize Jira issue link structure."""
    result = {"blocks": [], "blocked_by": [], "relates_to": []}
    for link in raw_links:
        link_type = link.get("type", {}).get("name", "").lower()
        if "inward" in link and link.get("inwardIssue"):
            key = link["inwardIssue"]["key"]
            if "block" in link_type:
                result["blocked_by"].append(key)
            else:
                result["relates_to"].append(key)
        if "outward" in link and link.get("outwardIssue"):
            key = link["outwardIssue"]["key"]
            if "block" in link_type:
                result["blocks"].append(key)
            else:
                result["relates_to"].append(key)
    return result


def _has_acceptance_criteria(fields: dict) -> bool:
    """Check if an issue has acceptance criteria defined."""
    desc = fields.get("description") or {}
    if isinstance(desc, dict):
        # Atlassian Document Format
        content_str = str(desc).lower()
        return any(kw in content_str for kw in [
            "acceptance criteria", "acceptance criterion", "ac:", "given", "when then"
        ])
    if isinstance(desc, str):
        return any(kw in desc.lower() for kw in [
            "acceptance criteria", "acceptance criterion"
        ])
    return False


def _compute_time_in_status(status_changed_at: datetime | None) -> float | None:
    """Hours since the issue entered its current status."""
    if not status_changed_at:
        return None
    delta = datetime.now(timezone.utc) - status_changed_at
    return round(delta.total_seconds() / 3600, 1)


class JiraSyncPipeline:

    def __init__(self, team: Team):
        self.team = team
        self.client = JiraClient()

    async def run(self) -> dict[str, int]:
        """
        Full sync for a team's Jira project.
        Returns counts of upserted records.
        """
        logger.info("jira_sync.start", team=self.team.jira_project_key)
        counts = {"sprints": 0, "issues": 0, "transitions": 0}

        async with AsyncSessionLocal() as db:
            try:
                board_id = await self._ensure_board_id(db)
                if not board_id:
                    logger.error("jira_sync.no_board", team=self.team.jira_project_key)
                    return counts

                counts["sprints"] = await self._sync_sprints(db, board_id)
                counts["issues"] = await self._sync_issues(db, board_id)
                counts["transitions"] = await self._sync_transitions_for_active(db)

                # Update last sync timestamp
                result = await db.execute(
                    select(Team).where(Team.id == self.team.id)
                )
                team_row = result.scalar_one()
                team_row.last_jira_sync = datetime.now(timezone.utc)
                await db.commit()

                logger.info("jira_sync.complete", counts=counts, team=self.team.jira_project_key)
            except Exception as e:
                await db.rollback()
                logger.error("jira_sync.failed", error=str(e), team=self.team.jira_project_key)
                raise

        return counts

    async def _ensure_board_id(self, db: AsyncSession) -> int | None:
        if self.team.jira_board_id:
            return self.team.jira_board_id
        boards = await self.client.get_all_boards(self.team.jira_project_key)
        if not boards:
            return None
        board_id = boards[0]["id"]
        result = await db.execute(select(Team).where(Team.id == self.team.id))
        team_row = result.scalar_one()
        team_row.jira_board_id = board_id
        await db.flush()
        return board_id

    async def _sync_sprints(self, db: AsyncSession, board_id: int) -> int:
        raw_sprints = await self.client.get_sprints(board_id)
        count = 0
        for raw in raw_sprints:
            result = await db.execute(
                select(Sprint).where(
                    Sprint.team_id == self.team.id,
                    Sprint.jira_sprint_id == raw["id"]
                )
            )
            sprint = result.scalar_one_or_none()
            if not sprint:
                sprint = Sprint(team_id=self.team.id, jira_sprint_id=raw["id"])
                db.add(sprint)

            sprint.name = raw.get("name", "")
            sprint.state = raw.get("state", "future")
            sprint.start_date = _parse_dt(raw.get("startDate"))
            sprint.end_date = _parse_dt(raw.get("endDate"))
            sprint.complete_date = _parse_dt(raw.get("completeDate"))
            sprint.goal = raw.get("goal")
            sprint.raw_data = raw
            count += 1

        await db.flush()
        return count

    async def _sync_issues(self, db: AsyncSession, board_id: int) -> int:
        # Fetch from active sprint first, then all open issues
        active_sprint_data = await self.client.get_active_sprint(board_id)
        active_sprint_id = active_sprint_data["id"] if active_sprint_data else None

        raw_issues: list[dict] = []
        if active_sprint_id:
            raw_issues = await self.client.get_issues_for_sprint(board_id, active_sprint_id)
        else:
            raw_issues = await self.client.get_issues_for_project(self.team.jira_project_key)

        # Get sprint DB mapping
        sprint_map: dict[int, str] = {}
        result = await db.execute(select(Sprint).where(Sprint.team_id == self.team.id))
        for s in result.scalars().all():
            sprint_map[s.jira_sprint_id] = s.id

        count = 0
        for raw in raw_issues:
            fields = raw.get("fields", {})
            await self._upsert_issue(db, raw, fields, sprint_map, active_sprint_id)
            count += 1

        await db.flush()
        return count

    async def _upsert_issue(
        self,
        db: AsyncSession,
        raw: dict,
        fields: dict,
        sprint_map: dict,
        active_sprint_id: int | None,
    ) -> None:
        result = await db.execute(
            select(JiraIssue).where(
                JiraIssue.team_id == self.team.id,
                JiraIssue.jira_issue_id == raw["id"]
            )
        )
        issue = result.scalar_one_or_none()
        if not issue:
            issue = JiraIssue(team_id=self.team.id, jira_issue_id=raw["id"])
            db.add(issue)

        issue.issue_key = raw["key"]
        issue.summary = fields.get("summary", "")
        issue.issue_type = fields.get("issuetype", {}).get("name", "Story")
        issue.status = fields.get("status", {}).get("name", "")
        issue.status_category = (
            fields.get("status", {}).get("statusCategory", {}).get("name", "")
        )
        issue.priority = (fields.get("priority") or {}).get("name")
        assignee = fields.get("assignee") or {}
        issue.assignee_account_id = assignee.get("accountId")
        issue.assignee_name = assignee.get("displayName")
        issue.story_points = _extract_story_points(fields)
        issue.labels = fields.get("labels", [])
        issue.created_at_jira = _parse_dt(fields.get("created"))
        issue.updated_at_jira = _parse_dt(fields.get("updated"))

        # Issue links
        raw_links = fields.get("issuelinks", [])
        links = _extract_issue_links(raw_links)
        issue.issue_links = links
        issue.is_blocked = len(links["blocked_by"]) > 0
        issue.blocker_count = len(links["blocked_by"])
        issue.has_acceptance_criteria = _has_acceptance_criteria(fields)
        issue.raw_data = {"key": raw["key"], "fields": {
            k: v for k, v in fields.items() if k not in ("description", "comment")
        }}

        # Sprint assignment
        sprint_field = fields.get("sprint") or {}
        sprint_jira_id = sprint_field.get("id") or active_sprint_id
        if sprint_jira_id and sprint_jira_id in sprint_map:
            issue.sprint_id = sprint_map[sprint_jira_id]

    async def _sync_transitions_for_active(self, db: AsyncSession) -> int:
        """Fetch changelog for all in-progress issues in the active sprint."""
        result = await db.execute(
            select(JiraIssue).where(
                JiraIssue.team_id == self.team.id,
                JiraIssue.status_category == "In Progress"
            )
        )
        in_progress = result.scalars().all()

        count = 0
        for issue in in_progress:
            try:
                raw_transitions = await self.client.get_issue_changelog(issue.issue_key)
                for t in raw_transitions:
                    transitioned_at = _parse_dt(t["created"])
                    # Check if already stored
                    exists = await db.execute(
                        select(IssueTransition).where(
                            IssueTransition.issue_id == issue.id,
                            IssueTransition.to_status == t["to_status"],
                            IssueTransition.transitioned_at == transitioned_at,
                        )
                    )
                    if exists.scalar_one_or_none():
                        continue
                    author = t.get("author", {})
                    transition = IssueTransition(
                        issue_id=issue.id,
                        from_status=t.get("from_status"),
                        to_status=t["to_status"],
                        transitioned_at=transitioned_at,
                        author_account_id=author.get("accountId"),
                        author_name=author.get("displayName"),
                    )
                    db.add(transition)

                    # Update status_changed_at on the issue (latest transition)
                    if (
                        issue.status_changed_at is None
                        or (transitioned_at and transitioned_at > issue.status_changed_at)
                    ):
                        issue.status_changed_at = transitioned_at
                        issue.time_in_status_hours = _compute_time_in_status(transitioned_at)

                    count += 1
            except Exception as e:
                logger.warning(
                    "jira_sync.changelog_failed",
                    issue=issue.issue_key,
                    error=str(e)
                )
                continue

        await db.flush()
        return count


async def run_jira_sync_for_all_teams() -> None:
    """Entry point called by the scheduler."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Team).where(Team.is_active == True))
        teams = result.scalars().all()

    for team in teams:
        try:
            pipeline = JiraSyncPipeline(team)
            await pipeline.run()
        except Exception as e:
            logger.error("jira_sync.team_failed", team=team.jira_project_key, error=str(e))
