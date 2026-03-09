"""
Slack signal extractor.
Uses Claude to analyze batches of Slack messages and extract risk signals.
"""
import json
import logging
from typing import Any
import anthropic

logger = logging.getLogger(__name__)

_client = None


def get_claude():
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


SYSTEM_PROMPT = """You are an engineering risk analyst. You analyze Slack messages from a software engineering team and extract risk signals relevant to sprint health, blockers, and team dynamics.

You ALWAYS respond with valid JSON only — no prose, no markdown fences, no explanation.

Return an array of signal objects. Each object must have:
- "type": one of: "blocker", "deployment_failure", "deployment_success", "customer_escalation", "help_request", "sentiment_negative", "sentiment_positive", "unresolved_thread"
- "severity": one of: "critical", "high", "medium", "low"
- "content": a 1-2 sentence description of the signal in plain English
- "actors": array of usernames involved (can be empty)
- "jira_refs": array of any Jira issue keys mentioned e.g. ["ONB-123"] (can be empty)
- "raw_ts": the Slack timestamp of the most relevant message

Only extract genuine signals — ignore casual chitchat, emoji reactions to good news, routine check-ins.
If there are no meaningful signals, return an empty array [].
"""


async def extract_signals(
    messages: list[dict],
    channel_name: str,
    team_jira_key: str,
) -> list[dict]:
    """Extract risk signals from a batch of Slack messages using Claude."""
    if not messages:
        return []

    formatted = []
    for m in messages[:80]:
        formatted.append(
            f"[{m['timestamp'].strftime('%Y-%m-%d %H:%M')}] "
            f"{m['username']}: {m['text'][:300]}"
            + (f" [thread: {m['reply_count']} replies]" if m['reply_count'] > 2 else "")
        )

    messages_text = "\n".join(formatted)
    prompt = f"""Analyze these Slack messages from #{channel_name} (Jira project: {team_jira_key}).
Extract risk signals relevant to engineering sprint health.

Messages:
{messages_text}

Return JSON array of signals."""

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        signals = json.loads(raw)
        return signals if isinstance(signals, list) else []
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in signal extraction: {e}")
        return []
    except Exception as e:
        logger.error(f"Signal extraction error: {e}")
        return []


def signals_to_insights(
    signals: list[dict],
    team_id: str,
    channel_name: str,
    channel_id: str,
) -> list[dict]:
    """Convert extracted signals to Insight model dicts."""
    insight_type_map = {
        "blocker":             "blocker",
        "deployment_failure":  "risk",
        "deployment_success":  "decision",
        "customer_escalation": "blocker",
        "help_request":        "risk",
        "sentiment_negative":  "sentiment",
        "sentiment_positive":  "sentiment",
        "unresolved_thread":   "risk",
    }
    insights = []
    for sig in signals:
        sig_type = sig.get("type", "risk")
        insight_type = insight_type_map.get(sig_type, "risk")
        severity = sig.get("severity", "medium")
        if sig_type == "deployment_failure" and severity == "low":
            severity = "high"
        if sig_type == "customer_escalation" and severity in ("low", "medium"):
            severity = "high"
        insights.append({
            "team_id": team_id,
            "source": "slack",
            "insight_type": insight_type,
            "severity": severity,
            "content": sig.get("content", ""),
            "extra_data": {
                "slack_type": sig_type,
                "channel": channel_name,
                "channel_id": channel_id,
                "actors": sig.get("actors", []),
                "jira_refs": sig.get("jira_refs", []),
                "raw_ts": sig.get("raw_ts"),
            },
        })
    return insights
