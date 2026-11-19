"""Draft help for Source Map stops, from the Claude API.

The owner presses "Draft with Claude" on a plotted stop and gets a suggested
title and explanation in the form. Nothing is saved or published until they
edit it and press Save the stop. Spending is capped per calendar month (UTC):
each request reserves its worst-case cost before it's sent, so two drafts at
once can't push the month over the cap.
"""
import json
import os
import re
from datetime import datetime, timezone

import claude_budget

MODEL = os.getenv("TOWN_DRAFT_MODEL", "claude-opus-5-5")
MAX_USD_PER_MONTH = float(os.getenv("TOWN_DRAFT_MAX_USD_PER_MONTH", "1"))
# US dollars per million tokens, kept in the stack so a price change doesn't
# need a code change.
PRICE_INPUT = float(os.getenv("TOWN_DRAFT_PRICE_INPUT", "4"))
PRICE_OUTPUT = float(os.getenv("TOWN_DRAFT_PRICE_OUTPUT", "20"))
MAX_TOKENS = 1000
# Input is a short brief plus at most 40 lines of code, well under this.
MAX_INPUT_TOKENS = 4000

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "A short, plain title for the stop, at most 60 characters."},
        "explanation": {"type": "string", "description": "Two or three plain sentences, at most 450 characters."},
    },
    "required": ["title", "explanation"],
    "additionalProperties": False,
}

SYSTEM = """You help a developer write one stop of a guided tour through their own code. Visitors to their portfolio, often recruiters and other developers, read each stop beside a short excerpt of the code.

Write a title and an explanation for the stop.
- The title names what this code does, in a few plain words, like "Finding the right bot" or "Writing it down". No colon, no file names.
- The explanation says what the marked lines do and why they matter, in two or three short sentences of plain English, in the developer's voice ("I", "my"). Someone who doesn't read code should still follow it.
- Only say what the code shows. Don't guess at numbers, users, results or history that aren't in the excerpt.
- Don't name file paths, folders, company or client names, people, keys or URLs, even if they appear in the code.
- Write plainly. No em dashes or en dashes, no emoji, no exclamation marks, no marketing words such as delve, leverage, seamless, robust, elevate, unlock, empower, cutting-edge or powerful, and no "not just X but Y"."""

BANNED = re.compile(r"\b(delve|leverag\w*|seamless\w*|robust\w*|elevat\w*|unlock\w*|empower\w*|cutting-edge)\b", re.I)


class DraftError(Exception):
    pass


def _month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _worst_case():
    return (MAX_INPUT_TOKENS * PRICE_INPUT + MAX_TOKENS * PRICE_OUTPUT) / 1_000_000


def _tidy(text, limit):
    text = re.sub(r"\s*[—–]\s*", ", ", str(text or ""))
    text = re.sub(r"\s+", " ", text).replace("!", ".").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0]


def spend(town):
    item = town.get_item(Key={"pk": "SPEND", "sk": f"DRAFT#{_month()}"}).get("Item") or {}
    return {"spent": float(item.get("spent_usd", 0)), "drafts": int(item.get("drafts", 0)), "cap": MAX_USD_PER_MONTH, "month": _month()}


def brief(repo_name, description, stop, position, titles):
    numbered = "\n".join(f"{stop['start'] + i:>4}{'*' if stop['mark'][0] <= stop['start'] + i <= stop['mark'][1] else ' '} {line}"
                         for i, line in enumerate(stop["lines"]))
    others = "\n".join(f"{n}. {t or '(untitled)'}" for n, t in enumerate(titles, 1))
    return (
        f"<project>\n{repo_name}\n{description}\n</project>\n\n"
        f"<route>\nThis is stop {position} of {len(titles)}. The stops so far:\n{others}\n</route>\n\n"
        f"<excerpt language=\"{stop.get('lang') or 'text'}\">\n{numbered}\n</excerpt>\n\n"
        "Lines marked * are the ones the developer wants visitors to notice."
    )


def draft_stop(town, api_key, repo_name, description, stop, position, titles, client_factory=None):
    if not api_key:
        raise DraftError("Draft help isn't set up: there's no Claude API key.")
    if MAX_USD_PER_MONTH <= 0:
        raise DraftError("Draft help is switched off (the monthly cap is zero).")
    key = {"pk": "SPEND", "sk": f"DRAFT#{_month()}"}
    try:
        claude_budget.reserve(town, key, MAX_USD_PER_MONTH, _worst_case())
    except claude_budget.OverBudget:
        raise DraftError(f"This month's draft budget (US${MAX_USD_PER_MONTH:.2f}) is used up. It resets on the 1st (UTC).") from None
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
            messages=[{"role": "user", "content": brief(repo_name, description, stop, position, titles)}],
        ) as stream:
            message = stream.get_final_message()
        usage = message.usage
        cost = ((usage.input_tokens or 0) * PRICE_INPUT + (usage.output_tokens or 0) * PRICE_OUTPUT) / 1_000_000
        if message.stop_reason == "refusal":
            raise DraftError("Claude declined to draft this stop. Write it yourself, or try other lines.")
        if message.stop_reason == "max_tokens":
            raise DraftError("The draft came back cut off. Try again.")
        text = next((b.text for b in message.content if b.type == "text"), "")
        data = json.loads(text)
    except DraftError:
        raise
    except Exception as exc:  # noqa: BLE001 - any API failure becomes one plain message
        raise DraftError("Claude couldn't be reached. Try again in a moment.") from exc
    finally:
        claude_budget.settle(town, key, cost, _worst_case(), "drafts")
    title, explanation = _tidy(data.get("title"), 80), _tidy(data.get("explanation"), 600)
    words = sorted({m.lower() for m in BANNED.findall(title + " " + explanation)})
    return {"title": title, "explanation": explanation, "cost": round(cost, 4), "check_words": words}
