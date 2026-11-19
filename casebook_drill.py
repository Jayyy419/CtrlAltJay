"""Drill feedback for Casebook, from the Claude API.

The owner types an answer to one of a case's questions and asks for
feedback. Claude gets the question, why it's likely asked, and the stored
notes for it (the lead evidence title and the STAR outline built from stored
facts), plus the answer. Nothing is stored: not the answer, not the
feedback. Spending is capped per calendar month (UTC).
"""
import json
import os
import re

import claude_budget

MODEL = os.getenv("CASEBOOK_DRILL_MODEL", "claude-opus-5-5")
MAX_USD_PER_MONTH = float(os.getenv("CASEBOOK_DRILL_MAX_USD_PER_MONTH", "1"))
# US dollars per million tokens, kept in the stack.
PRICE_INPUT = float(os.getenv("CASEBOOK_DRILL_PRICE_INPUT", "4"))
PRICE_OUTPUT = float(os.getenv("CASEBOOK_DRILL_PRICE_OUTPUT", "20"))
MAX_TOKENS = 900
MAX_ANSWER_CHARS = 4000
# The brief, notes and a 4,000-character answer stay well under this.
MAX_INPUT_TOKENS = 3000
WORST_CASE = (MAX_INPUT_TOKENS * PRICE_INPUT + MAX_TOKENS * PRICE_OUTPUT) / 1_000_000

SCHEMA = {
    "type": "object",
    "properties": {
        "star": {
            "type": "object",
            "properties": {k: {"type": "boolean"} for k in ("situation", "task", "action", "result")},
            "required": ["situation", "task", "action", "result"],
            "additionalProperties": False,
        },
        "went_well": {"type": "array", "items": {"type": "string"}, "description": "One or two things that worked."},
        "to_work_on": {"type": "array", "items": {"type": "string"}, "description": "One or two specific things to change next time."},
    },
    "required": ["star", "went_well", "to_work_on"],
    "additionalProperties": False,
}

SYSTEM = """You coach a university student practising answers for interviews and applications. They typed an answer to one likely question. Give short, honest feedback they can use on the next try.

- Mark which parts of a STAR answer are clearly there: situation, task, action, result. For a motivation question, mark the parts that fit and don't fault the rest.
- went_well: one or two specific things that worked, each one short sentence.
- to_work_on: one or two specific changes, each one short sentence. Point to what's missing or vague, such as a result with no outcome, "we" where their own part is unclear, or too much background.
- Judge only what they wrote. Their notes show what they could draw on; never suggest numbers, outcomes or facts that aren't in the answer or the notes. If a result is missing, say to add the real one, don't make one up.
- Plain words, second person ("you"). No em dashes or en dashes, no emoji, no exclamation marks, no marketing words such as delve, leverage, seamless, robust, elevate, unlock, empower or powerful."""

BANNED = re.compile(r"\b(delve|leverag\w*|seamless\w*|robust\w*|elevat\w*|unlock\w*|empower\w*)\b", re.I)


class DrillError(Exception):
    pass


def budget_key():
    return {"pk": "SPEND", "sk": f"DRILL#{claude_budget.month()}"}


def budget(table):
    spent, calls = claude_budget.spent(table, budget_key(), "feedbacks")
    return {"spent": round(spent, 4), "feedbacks": calls, "cap": MAX_USD_PER_MONTH, "month": claude_budget.month()}


def _tidy(text, limit=220):
    text = re.sub(r"\s*[—–]\s*", ", ", str(text or ""))
    return re.sub(r"\s+", " ", text).replace("!", ".").strip()[:limit]


def brief(question, answer, seconds):
    star = question.get("star") or {}
    lead = (question.get("evidence") or [{}])[0].get("title", "") if question.get("evidence") else ""
    notes = "\n".join(f"{k.title()}: {star.get(k) or '(not in the notes)'}" for k in ("situation", "task", "action", "result")) if star else "(no outline)"
    return (
        f"<question kind=\"{question.get('kind', '')}\">\n{question.get('text', '')}\n</question>\n\n"
        f"<why_they_ask>\n{question.get('why') or 'Not noted.'}\n</why_they_ask>\n\n"
        f"<notes>\nLead evidence: {lead or 'none picked'}\n{notes}\n</notes>\n\n"
        f"<answer seconds=\"{int(seconds or 0)}\">\n{answer}\n</answer>"
    )


def feedback(table, api_key, question, answer, seconds, client_factory=None):
    answer = str(answer or "").strip()[:MAX_ANSWER_CHARS]
    if len(answer.split()) < 5:
        raise DrillError("Type a bit more of your answer first.")
    if not api_key:
        raise DrillError("Feedback isn't set up: there's no Claude API key.")
    if MAX_USD_PER_MONTH <= 0:
        raise DrillError("Feedback is switched off (the monthly cap is zero).")
    key = budget_key()
    try:
        claude_budget.reserve(table, key, MAX_USD_PER_MONTH, WORST_CASE)
    except claude_budget.OverBudget:
        raise DrillError(f"This month's feedback budget (US${MAX_USD_PER_MONTH:.2f}) is used up. It resets on the 1st (UTC).") from None
    cost = 0.0
    try:
        if client_factory is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        else:
            client = client_factory()
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": brief(question, answer, seconds)}],
        ) as stream:
            message = stream.get_final_message()
        usage = message.usage
        cost = ((usage.input_tokens or 0) * PRICE_INPUT + (usage.output_tokens or 0) * PRICE_OUTPUT) / 1_000_000
        if message.stop_reason == "refusal":
            raise DrillError("Claude declined to give feedback on this one.")
        if message.stop_reason == "max_tokens":
            raise DrillError("The feedback came back cut off. Try again.")
        data = json.loads(next((b.text for b in message.content if b.type == "text"), ""))
    except DrillError:
        raise
    except Exception as exc:  # noqa: BLE001 - any API failure becomes one plain message
        raise DrillError("Claude couldn't be reached. Try again in a moment.") from exc
    finally:
        claude_budget.settle(table, key, cost, WORST_CASE, "feedbacks")
    star = {k: bool((data.get("star") or {}).get(k)) for k in ("situation", "task", "action", "result")}
    went = [_tidy(x) for x in (data.get("went_well") or [])[:2] if str(x).strip()]
    work = [_tidy(x) for x in (data.get("to_work_on") or [])[:2] if str(x).strip()]
    words = sorted({m.lower() for m in BANNED.findall(" ".join(went + work))})
    return {"star": star, "went_well": went, "to_work_on": work, "cost": round(cost, 4), "check_words": words}
