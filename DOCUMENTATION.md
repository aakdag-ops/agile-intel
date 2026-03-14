# Agile Intel — User Documentation

> **Agile Intel** is an AI-powered risk intelligence platform for engineering teams. It continuously monitors your Jira board, Slack channels, and meeting transcripts, then synthesises everything into a single risk score and coaching-grade insights — so you can see what's actually happening, not just what the board says.

---

## Table of Contents

1. [What Does Agile Intel Do?](#1-what-does-agile-intel-do)
2. [Key Concepts](#2-key-concepts)
3. [Data Sources](#3-data-sources)
4. [Pages & Features](#4-pages--features)
   - [Teams (Home)](#41-teams-home)
   - [Dashboard](#42-dashboard)
   - [AI Chat Coach](#43-ai-chat-coach)
   - [Timeline](#44-timeline)
   - [Backlog Healthcheck](#45-backlog-healthcheck)
   - [Transcripts](#46-transcripts)
5. [Risk Score Explained](#5-risk-score-explained)
6. [How Automatic Syncs Work (Cron Jobs)](#6-how-automatic-syncs-work-cron-jobs)
7. [Manual Sync & On-Demand Actions](#7-manual-sync--on-demand-actions)
8. [User Roles](#8-user-roles)
9. [Integrations Setup](#9-integrations-setup)
10. [Frequently Asked Questions](#10-frequently-asked-questions)

---

## 1. What Does Agile Intel Do?

Most engineering teams live in Jira but the real problems live in Slack threads, meeting notes, and tribal knowledge that never makes it onto the board. Agile Intel bridges that gap by:

- **Pulling data** from Jira, Slack, and Google Drive meeting transcripts on a schedule
- **Scoring risk** across 7 signals (WIP aging, blockers, velocity, readiness, Slack signals, sentiment, and meeting alignment)
- **Surfacing insights** — concrete blockers, decisions, risks, and scope changes — extracted by AI from Slack messages and meeting transcripts
- **Answering questions** through a conversational AI coach that has live access to all of the above simultaneously

---

## 2. Key Concepts

| Term | Meaning |
|------|---------|
| **Team** | A Jira project mapped to one or more Slack channels. Each team has its own dashboard, risk score, and data. |
| **Risk Score** | A composite 0–100 number representing overall sprint/delivery risk. Higher = more risk. |
| **Signal** | One of 7 risk dimensions (e.g. WIP Aging, Dependencies). Each is scored 0–100 independently. |
| **Insight** | A specific extracted piece of intelligence: a blocker, a decision, a risk, or a sentiment signal — with a source (Jira / Slack / Transcript) and severity. |
| **Snapshot** | A point-in-time capture of all 7 signal scores. Snapshots are taken automatically on every sync cycle. |
| **Sprint** | Active, closed, and future sprints are all tracked. Velocity history is stored across all closed sprints. |
| **Healthcheck** | An on-demand deep analysis of your backlog quality across 11 criteria, scored issue-by-issue by AI. |

---

## 3. Data Sources

Agile Intel integrates with three data sources:

### Jira Cloud
- Reads all sprints (active, closed, future), issues, story points, statuses, priorities, assignees, issue links, and acceptance criteria
- Tracks how long each issue has been in its current status (WIP aging)
- Reads the full transition history of every in-progress issue
- Uses the Jira Agile REST API (`/rest/agile/1.0`) and the Search API (`/rest/api/3/search/jql`)

### Slack
- Reads messages from configured channels over the last 7 days
- Claude AI analyses each message batch to extract risk signals (blockers, deployment failures, customer escalations, negative/positive sentiment, unresolved threads)
- Only channels explicitly added to a team are monitored

### Google Drive / Meeting Transcripts
- Syncs Google Docs that look like meeting transcripts (searches for files named with words like "transcript", "standup", "retro", "planning")
- Exports the document text and passes it to Claude, which extracts blockers, decisions, action items, scope changes, and sentiment
- Transcripts are auto-matched to teams by detecting your Jira project key in the text
- You can also upload transcripts manually (paste text directly)

---

## 4. Pages & Features

### 4.1 Teams (Home)

**URL:** `/teams`

The home screen shows all projects as cards. Each card displays:
- Project key and team name
- Active sprint name
- Current risk score (0–100) and risk level (LOW / MEDIUM / HIGH / CRITICAL)
- A mini breakdown of the 6 main signals (WIP, DEPS, VEL, PBI, SLACK, SENT)
- Last sync timestamp
- Quick-access buttons: DASHBOARD, CHAT, TIMELINE

From here you can also:
- **SYNC ALL** — triggers a manual Jira sync for every team at once
- **+ NEW TEAM** — create a new team by entering a Jira project key and board ID

---

### 4.2 Dashboard

**URL:** `/dashboard/:teamId`

The main team view. Shows four panels:

**Risk Gauge**
The circular dial shows the current composite risk score with a needle and colour coding (green → amber → orange → red). Below it, a trend indicator shows whether risk is improving (↓), worsening (↑), or stable (→) vs the previous snapshot, with the 7-day delta.

**Signal Breakdown**
Horizontal bar chart for all 6 visible signals with colour-coded bars. Each bar shows the individual signal score.

**Risk Radar**
A radar/spider chart plotting all 6 signals at once. Useful for spotting which dimension is the outlier at a glance.

**Composite Risk Trend (14 days)**
A line chart of the composite score over the past 14 days. Reference lines mark the HIGH (50) and CRITICAL (75) thresholds.

**Recent Insights**
The latest 5 insights from all sources (Slack, transcripts, Jira). Each card shows the source, insight type, severity, date, and the extracted text. Click "VIEW ALL →" to go to the full timeline.

**Header buttons:**
- **◈ HEALTHCHECK** — go to the Backlog Healthcheck page
- **◎ TRANSCRIPTS** — go to the Transcripts page
- **◆ ASK AI** — open the AI Chat coach
- **↻ SYNC** — manually trigger a Jira sync + risk rescore for this team

---

### 4.3 AI Chat Coach

**URL:** `/chat/:teamId`

A multi-turn conversational interface powered by Claude. Every message you send is automatically enriched with live project context before it reaches the AI.

**What context is injected automatically:**

| Context Source | Detail |
|---------------|--------|
| Risk snapshot | Current score + all 7 signals + velocity metrics |
| Active sprint | Sprint name, days remaining, goal, points done/total |
| Full sprint board | Every issue grouped by status with story points, assignee, blocked flag, WIP aging flag |
| Blocked issues | Issues flagged as blocked with their blockers listed |
| Sprint history | Last 4 closed sprints with committed/completed points and velocity |
| Recent insights | Up to 40 insights from the last 30 days, grouped by source (Transcript → Slack → Jira) |
| Meeting transcripts | Full text of the last 3 transcripts (truncated at 1200 chars each) |
| Backlog healthcheck | Lead times, AI insights per group, top 5 worst items, and recommended actions |

**Suggested starter questions (shown on first load):**
- What are the main risks in this sprint?
- Which issues have been stuck the longest?
- Will we hit the sprint goal?
- Who is most overloaded right now?
- What should we fix before the next standup?

You can ask anything: cross-reference signals, ask for root causes, request a go/no-go opinion, ask what happened in the last meeting, etc.

Chat history is saved per session and loaded on return so the AI remembers the conversation.

---

### 4.4 Timeline

**URL:** `/timeline/:teamId`

A chronological feed of all insights ever captured for a team. Useful for looking back at patterns, tracking when blockers appeared, or reviewing what was discussed in a specific period.

Insights can be filtered by:
- Source (Jira / Slack / Transcript)
- Severity (low / medium / high / critical)
- Type (blocker / risk / decision / sentiment / dependency / scope change)

---

### 4.5 Backlog Healthcheck

**URL:** `/healthcheck/:teamId`

A deep AI-powered quality audit of your backlog. Unlike the sprint-focused dashboard, this analyses the last **6 months** of issues — including done work, current sprint, and future backlog.

**To run a report:** Click **▶ GENERATE REPORT**. The analysis runs in the background (typically 10–20 minutes depending on backlog size) and the page polls automatically until complete.

**Report sections:**

**Lead Time Cards**
Four cards showing average lead time (created → resolved) overall and broken down by issue type (Story / Bug / Task). Colour coded: green < 20 days · amber 20–40 days · red > 40 days.

**Backlog Depth Analysis Matrix**
An 11 × 3 matrix. Rows are quality criteria; columns are three backlog groups:
- **Completed Last Month** — Done issues resolved in the previous calendar month
- **Planned This Month** — Issues in the active sprint
- **Next Month Work List** — Everything else (backlog, future sprints)

Each cell shows a stacked bar with % Good (green), Medium (amber), and Critical (red) for that criterion in that group.

**The 11 quality criteria scored per issue:**

| Criterion | What it checks |
|-----------|---------------|
| Title Clarity | Specific, non-generic title that describes the actual work |
| Description Quality | Meaningful description with scope and context |
| Acceptance Criteria | Clear, testable AC present |
| Estimation | Has story points / size estimate |
| Dependencies | External dependencies or blockers identified |
| Customer Focus | User or customer value clearly stated |
| Data-Driven | Data, metrics, or evidence backing the need |
| Vertical Slicing | Complete, end-to-end deliverable slice |
| Product Goal Alignment | Connected to a product goal or epic |
| OKR Alignment | Traceable to an OKR or strategic objective |
| Risk Profile | Risks, unknowns, or mitigations mentioned |

**AI Insights**
Three paragraphs — one per column — where the AI interprets what the statistics mean and what to prioritise.

**Top 5 Items to Solve**
The five issues with the most "Critical" ratings across all 11 criteria. Each shows the issue key and an AI-generated root cause explanation.

**Concrete Actions**
Three numbered, prioritised action items the team should take to improve backlog quality, generated by AI based on the full analysis.

---

### 4.6 Transcripts

**URL:** `/transcripts/:teamId`

View and manage meeting transcripts. Each transcript card shows the title, date, participants, and the insights extracted from it.

**Adding transcripts:**
1. **Manual upload** — Paste raw transcript text directly. The AI extracts insights immediately.
2. **Google Drive sync** — Connect your Google account once (OAuth). The system then automatically syncs docs from your Drive that look like meeting transcripts on the hourly schedule.

Click on any transcript to see the full text and all extracted insights below it.

---

## 5. Risk Score Explained

The composite risk score (0–100) is a weighted average of 7 independent signals:

| Signal | Default Weight | What drives it up |
|--------|---------------|-------------------|
| WIP Aging | 20% | Issues stuck In Progress beyond their threshold (Stories: 48h, Bugs: 24h, Tasks: 36h) |
| Dependencies | 20% | Blocked issues; worse if the blocked issue is In Progress |
| Velocity Trend | 15% | Recent sprint velocity significantly below the prior average |
| PBI Readiness | 15% | To-Do items missing story points, acceptance criteria, or assignee |
| Slack Signals | 15% | Unresolved blockers, deployment failures, customer escalations from Slack |
| Team Sentiment | 10% | Negative sentiment signals outnumbering positive ones across Slack + transcripts |
| Meeting Alignment | 5% | Unresolved blockers, untracked action items, or scope changes from meeting transcripts |

**Risk levels:**
- 🟢 **LOW** (0–24) — Healthy. Monitor normally.
- 🟡 **MEDIUM** (25–49) — Some signals worth watching.
- 🟠 **HIGH** (50–74) — Active problems. Review blocked/aged items.
- 🔴 **CRITICAL** (75–100) — Sprint delivery at serious risk. Immediate action needed.

Weights can be customised per team by an admin (e.g. if Slack isn't configured, increase Jira weights).

---

## 6. How Automatic Syncs Work (Cron Jobs)

Agile Intel runs background jobs on a continuous schedule to keep all data fresh. These jobs run silently in the background — you never need to trigger them manually (though you can if you want fresher data immediately).

### Job 1 — Jira Sync
**Runs every: 15 minutes** (configurable via `JIRA_SYNC_INTERVAL_MINUTES`)

What it does on each run:
1. Loops through every active team
2. Fetches all sprints (active, closed, future) for the team's Jira board
3. Fetches all issues in the active sprint + all open issues in the project
4. Updates sprint velocity, issue statuses, story points, WIP time, and transition history
5. Calculates how long each issue has been in its current status

After Jira sync completes, the risk scoring job runs immediately to update scores.

---

### Job 2 — Risk Scoring
**Runs every: 15 minutes** (same interval as Jira sync, runs right after it)

What it does on each run:
1. For each team, reads the freshly synced Jira data from the database
2. Computes all 7 signal scores
3. Computes the weighted composite score
4. Saves a new **RiskSnapshot** (timestamped record) — this is what powers the trend chart
5. Auto-generates insights for any high-scoring anomalies (e.g. an issue that's been stuck for 72+ hours)

Each run produces a new snapshot, so you get a full historical record of how your risk score has changed over time.

---

### Job 3 — Slack Sync
**Runs every: 30 minutes** (configurable via `SLACK_SYNC_INTERVAL_MINUTES`)
**Requires:** Slack bot token to be configured

What it does on each run:
1. For each team, looks up which Slack channels are configured
2. Fetches messages from the last 7 days from each channel
3. Sends message batches to Claude, which extracts risk signals
4. Saves any new insights to the database (deduplicates by content)

If `SLACK_BOT_TOKEN` is not set, this job is skipped entirely.

---

### Job 4 — Transcript Sync (Google Drive)
**Runs every: 60 minutes** (configurable via `TRANSCRIPT_SYNC_INTERVAL_MINUTES`)
**Requires:** At least one user has connected their Google account

What it does on each run:
1. Finds all users who have a valid Google OAuth token
2. For each user, searches their Google Drive for recent documents with meeting-related names
3. Exports each document as plain text
4. Passes the text to Claude, which extracts blockers, decisions, action items, scope changes, and sentiment
5. Auto-matches the transcript to the right team by looking for Jira project keys in the text
6. Saves the transcript and its extracted insights

If no user has connected Google Drive, this job is skipped.

---

### Checking Sync Status

You can check what the scheduler is doing via the API:

```
GET /api/v1/scheduler/status
```

This returns the current state of each job and the timestamp of its next scheduled run.

---

### Sync Frequency Summary

| Job | Frequency | Configurable | Requires |
|-----|-----------|-------------|----------|
| Jira Sync | Every 15 min | ✅ | Jira service account |
| Risk Scoring | Every 15 min | ✅ | Jira sync data |
| Slack Sync | Every 30 min | ✅ | Slack bot token |
| Transcript Sync | Every 60 min | ✅ | Google OAuth connected |

All intervals are set in environment variables and take effect on the next server restart.

---

## 7. Manual Sync & On-Demand Actions

You don't have to wait for the scheduler. Every sync can be triggered manually:

| Action | Where | What happens |
|--------|-------|-------------|
| **↻ SYNC** button on Dashboard | Team Dashboard | Triggers Jira sync + risk rescore for that team |
| **SYNC ALL** button on Teams page | Teams home | Triggers Jira sync for all teams |
| **▶ GENERATE REPORT** on Healthcheck | Healthcheck page | Runs full backlog healthcheck analysis (10–20 min) |
| Manual transcript upload | Transcripts page | Processes immediately, no wait |
| Google Drive sync | Transcripts page | Triggers a one-off Drive scan for that team |

---

## 8. User Roles

| Role | Can do |
|------|--------|
| **Admin** | Everything: create teams, add/remove members, change risk weights, trigger any sync, access all teams |
| **Coach** | View all data, use AI chat, upload transcripts, trigger syncs — cannot create teams or manage users |
| **Viewer** | Read-only access to dashboards, timeline, and healthcheck reports |

---

## 9. Integrations Setup

### Jira (Required)
Jira is always required — it is the primary data source.

You need:
- **Jira Base URL** — e.g. `https://yourcompany.atlassian.net`
- **Service Account Email** — a dedicated Jira user email
- **API Token** — generated in Jira account settings → Security → API tokens

These are set in the server's environment variables (`JIRA_BASE_URL`, `JIRA_SERVICE_EMAIL`, `JIRA_SERVICE_API_TOKEN`).

When creating a team you provide the **Jira Project Key** (e.g. `ONB`) and **Board ID** (visible in the Jira board URL).

---

### Slack (Optional)
Enables Slack signal extraction.

You need:
- A **Slack Bot Token** (`xoxb-...`) with `channels:history` and `channels:read` scope
- Set `SLACK_BOT_TOKEN` in environment variables

Once configured, add channels to a team via the Teams page or the Integrations API. The bot must be invited to each channel (`/invite @your-bot-name`).

---

### Google Drive / Transcripts (Optional)
Enables automatic meeting transcript sync.

You need:
- A **Google OAuth 2.0 client** (Client ID + Secret) configured in Google Cloud Console with the Drive API enabled
- Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in environment variables
- Each user connects their own Google account via the **Transcripts** page → Google Drive connect flow

Agile Intel only reads documents; it never writes to your Drive.

---

## 10. Frequently Asked Questions

**Q: How often does the risk score update?**
Every 15 minutes automatically. You can force an immediate update using the ↻ SYNC button on the Dashboard.

**Q: Why is my Slack Signals score always 0?**
Either Slack is not configured (no `SLACK_BOT_TOKEN`), or no Slack channels have been added to your team, or no risk signals were found in the last sync window.

**Q: How long does a Backlog Healthcheck take?**
It depends on backlog size. Each batch of 20 issues takes about 15–20 seconds for Claude to score. A backlog of ~800 issues takes roughly 10–15 minutes. The page polls automatically and refreshes when complete.

**Q: Does the AI chat see my latest Jira data?**
Yes. Every message you send injects the latest data (from the last sync) as context, including the full sprint board, all insights from the last 30 days, recent transcripts, and the latest healthcheck report.

**Q: Can I use Agile Intel without Slack?**
Yes. The Slack Signals score will be 0 and those insights won't appear, but all Jira-based signals (WIP aging, dependencies, velocity, PBI readiness) work fully without Slack.

**Q: What happens if Jira credentials expire?**
The Jira sync job will fail. The last successful snapshot remains visible but won't update. The Dashboard will show the timestamp of the last sync so you can detect staleness.

**Q: Can I adjust the risk score weights for my team?**
Yes, as an Admin. Each team has configurable weights for all 7 signals (they must sum to 1.0). Contact your admin or use the Teams API (`PATCH /api/v1/teams/{team_id}`).

**Q: How is sentiment scored?**
Each negative signal from Slack or transcripts adds points to the sentiment score based on severity (critical = 25pts, high = 15pts, medium = 8pts, low = 4pts). Each positive signal subtracts 3 points. The score is capped at 100.

**Q: Are chat conversations stored?**
Yes, per session. The AI loads your last 10 conversation turns as history so it remembers context within a session. History is stored in the database linked to your user ID.
