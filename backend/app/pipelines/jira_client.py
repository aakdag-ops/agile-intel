"""
Jira Cloud REST API client.
Supports both service account (email + API token) and OAuth 2.0 auth.
"""
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import logger


class JiraClient:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        access_token: str | None = None,
    ):
        self.base_url = (base_url or settings.jira_base_url).rstrip("/")
        self._email = email or settings.jira_service_email
        self._api_token = api_token or settings.jira_service_api_token
        self._access_token = access_token  # OAuth token (user-specific)

    def _get_auth_headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        import base64
        creds = base64.b64encode(f"{self._email}:{self._api_token}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers={**self._get_auth_headers(), "Accept": "application/json"},
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _post(self, path: str, body: dict) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers={**self._get_auth_headers(), "Accept": "application/json", "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Boards & Sprints ─────────────────────────────────────────────────────

    async def get_all_boards(self, project_key: str) -> list[dict]:
        """Get all agile boards for a project."""
        data = await self._get(
            "/rest/agile/1.0/board",
            params={"projectKeyOrId": project_key, "maxResults": 50}
        )
        return data.get("values", [])

    async def get_sprints(self, board_id: int, state: str = "active,closed,future") -> list[dict]:
        """Get all sprints for a board."""
        sprints = []
        start = 0
        while True:
            data = await self._get(
                f"/rest/agile/1.0/board/{board_id}/sprint",
                params={"state": state, "startAt": start, "maxResults": 50}
            )
            sprints.extend(data.get("values", []))
            if data.get("isLast", True):
                break
            start += 50
        return sprints

    async def get_active_sprint(self, board_id: int) -> dict | None:
        """Get the currently active sprint."""
        data = await self._get(
            f"/rest/agile/1.0/board/{board_id}/sprint",
            params={"state": "active", "maxResults": 1}
        )
        values = data.get("values", [])
        return values[0] if values else None

    # ── Issues ───────────────────────────────────────────────────────────────

    async def get_issues_for_sprint(self, board_id: int, sprint_id: int) -> list[dict]:
        """Get all issues in a sprint with full field set."""
        issues = []
        start = 0
        fields = (
            "summary,status,priority,assignee,story_points,customfield_10016,"
            "issuetype,labels,created,updated,issuelinks,description,acceptanceCriteria,"
            "customfield_10014,parent"  # story points + epic link
        )
        while True:
            data = await self._get(
                f"/rest/agile/1.0/board/{board_id}/sprint/{sprint_id}/issue",
                params={"startAt": start, "maxResults": 100, "fields": fields}
            )
            batch = data.get("issues", [])
            issues.extend(batch)
            total = data.get("total", 0)
            start += len(batch)
            if start >= total or not batch:
                break
        return issues

    async def get_issues_for_project(
        self, project_key: str, max_results: int = 500
    ) -> list[dict]:
        """Get all non-done issues in a project via JQL."""
        issues = []
        next_page_token: str | None = None
        jql = f"project = {project_key} AND statusCategory != Done ORDER BY updated DESC"
        fields = [
            "summary", "status", "priority", "assignee", "customfield_10016",
            "issuetype", "labels", "created", "updated", "issuelinks",
            "description", "customfield_10014", "parent", "customfield_10020",
        ]
        while len(issues) < max_results:
            body: dict = {"jql": jql, "maxResults": 100, "fields": fields}
            if next_page_token:
                body["nextPageToken"] = next_page_token
            data = await self._post("/rest/api/3/search/jql", body)
            batch = data.get("issues", [])
            issues.extend(batch)
            next_page_token = data.get("nextPageToken")
            if data.get("isLast", True) or not batch or not next_page_token:
                break
        return issues

    async def get_issue_changelog(self, issue_key: str) -> list[dict]:
        """Get the full transition history for an issue."""
        data = await self._get(
            f"/rest/api/3/issue/{issue_key}/changelog",
            params={"maxResults": 100}
        )
        # Filter to status changes only
        status_changes = []
        for entry in data.get("values", []):
            for item in entry.get("items", []):
                if item.get("field") == "status":
                    status_changes.append({
                        "from_status": item.get("fromString"),
                        "to_status": item.get("toString"),
                        "author": entry.get("author", {}),
                        "created": entry.get("created"),
                    })
        return status_changes

    async def get_issues_for_healthcheck(self, project_key: str, months_back: int = 6) -> list[dict]:
        """Fetch ALL issues created in last N months — Done + active + backlog."""
        issues: list[dict] = []
        next_page_token: str | None = None
        jql = f"project = {project_key} AND created >= -{months_back * 30}d ORDER BY created DESC"
        fields = [
            "summary", "status", "issuetype", "priority", "assignee",
            "customfield_10016", "customfield_10028", "story_points",
            "labels", "created", "updated", "resolutiondate", "issuelinks",
            "description", "customfield_10014", "parent", "customfield_10020",
        ]
        while True:
            body: dict = {"jql": jql, "maxResults": 100, "fields": fields}
            if next_page_token:
                body["nextPageToken"] = next_page_token
            data = await self._post("/rest/api/3/search/jql", body)
            batch = data.get("issues", [])
            issues.extend(batch)
            next_page_token = data.get("nextPageToken")
            if data.get("isLast", True) or not batch or not next_page_token:
                break
        return issues

    async def get_project_info(self, project_key: str) -> dict:
        """Get project metadata."""
        return await self._get(f"/rest/api/3/project/{project_key}")

    async def get_myself(self) -> dict:
        """Verify auth and get current user info."""
        return await self._get("/rest/api/3/myself")
