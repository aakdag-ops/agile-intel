"""
Transcript signal extractor.
Uses Claude to analyze meeting transcripts and extract risk signals.
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


SYSTEM_PROMPT = """You are an engineering risk analyst. You analyze meeting transcripts from a software engineering team and extract structured risk signals relevant to sprint health, decisions, blockers, and team alignment.

You ALWAYS respond with valid JSON only — no prose, no markdown fences, no explanation.

Return an array of signal objects. Each object must have:
- "type": one of: "blocker", "decision", "action_item", "risk", "scope_change", "sentiment_negative", "sentiment_positive"
- "severity": one of: "critical", "high", "medium", "low"
- "content": a 1-2 sentence description of the signal in plain English
- "actors": array of participant names involved (can be empty)
- "jira_refs": array of any Jira issue keys mentioned e.g. ["ONB-123"] (can be empty)
- "raw_text": a short verbatim quote from the transcript (max 100 chars) that supports this signal

Signal type definitions:
- "blocker": something that is preventing work from progressing
- "decision": a concrete decision made during the meeting
- "action_item": a task or follow-up assigned to someone
- "risk": a risk or concern raised that is not yet a blocker
- "scope_change": discussion about adding/removing work from the sprint or project
- "sentiment_negative": significant frustration, confusion, or low morale expressed
- "sentiment_positive": team confidence, celebration of progress

Only extract genuine signals — ignore small talk, status updates with no risk content, and routine check-ins.
If there are no meaningful signals, return an empty array [].
"""


async def extract_signals(
    transcript_text: str,
    title: str,
    team_jira_key: str,
    participants: list[str],
) -> list[dict]:
    """Extract risk signals from a meeting transcript using Claude."""
    if not transcript_text or not transcript_text.strip():
        return []

    participants_str = ", ".join(participants) if participants else "unknown"
    prompt = f"""Analyze this meeting transcript titled "{title}" from team {team_jira_key}.
Participants: {participants_str}

Extract risk signals relevant to engineering sprint health, decisions, and blockers.

Transcript:
{transcript_text[:8000]}

Return JSON array of signals."""

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
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
        logger.error(f"JSON parse error in transcript extraction: {e}")
        return []
    except Exception as e:
        logger.error(f"Transcript extraction error: {e}")
        return []


def signals_to_insights(
    signals: list[dict],
    team_id: str,
    transcript_id: str,
    title: str,
) -> list[dict]:
    """Convert extracted signals to Insight model dicts."""
    insight_type_map = {
        "blocker":           "blocker",
        "decision":          "decision",
        "action_item":       "risk",
        "risk":              "risk",
        "scope_change":      "scope_change",
        "sentiment_negative": "sentiment",
        "sentiment_positive": "sentiment",
    }
    insights = []
    for sig in signals:
        sig_type = sig.get("type", "risk")
        insight_type = insight_type_map.get(sig_type, "risk")
        severity = sig.get("severity", "medium")
        # Elevate scope changes — they often go untracked
        if sig_type == "scope_change" and severity in ("low", "medium"):
            severity = "high"
        insights.append({
            "team_id": team_id,
            "transcript_id": transcript_id,
            "source": "transcript",
            "insight_type": insight_type,
            "severity": severity,
            "content": sig.get("content", ""),
            "extra_data": {
                "transcript_type": sig_type,
                "meeting_title": title,
                "actors": sig.get("actors", []),
                "jira_refs": sig.get("jira_refs", []),
                "raw_text": sig.get("raw_text", ""),
            },
        })
    return insights
