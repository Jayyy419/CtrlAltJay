"""Town hall collector: pulls repo stats from GitHub into ctrlaltjay-town.

Runs daily on a schedule and when the owner presses "Refresh now". It is the
only thing that can read the GitHub token. It never writes the public table:
nothing reaches the public site until the owner publishes from Town hall.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3

API = "https://api.github.com"
API_VERSION = "2022-11-28"
_ssm = boto3.client("ssm")
_table = boto3.resource("dynamodb").Table(os.environ.get("TOWN_TABLE", "ctrlaltjay-town"))

# Stats are computed by GitHub in the background and answer 202 until ready.
STATS_PASSES = 5
STATS_WAIT_SECONDS = 12
# Paging commit dates is the fallback when stats never become ready.
MAX_COMMIT_PAGES = 50
WEEK = 7 * 24 * 3600


class RateLimited(Exception):
    pass


def _token():
    return _ssm.get_parameter(Name=os.environ["GITHUB_TOKEN_SSM_PARAM"], WithDecryption=True)["Parameter"]["Value"].strip()


class GitHub:
    def __init__(self, token):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "ctrlaltjay-town-collector",
        }
        self.remaining = None
        self.reset_at = None
        self.calls = 0

    def get(self, path, params=None, accept=None, raw=False):
        url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = dict(self._headers)
        if accept:
            headers["Accept"] = accept
        for attempt in range(3):
            self.calls += 1
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self._note(resp.headers)
                    body = resp.read()
                    if resp.status in (202, 204):
                        return resp.status, None
                    return resp.status, (body if raw else json.loads(body or b"null"))
            except urllib.error.HTTPError as err:
                self._note(err.headers)
                if err.code in (403, 429):
                    if err.headers.get("x-ratelimit-remaining") == "0":
                        raise RateLimited(self.reset_at)
                    wait = int(err.headers.get("retry-after") or 0) or 30 * (attempt + 1)
                    if wait > 120:
                        raise RateLimited(self.reset_at)
                    time.sleep(wait)
                    continue
                if err.code >= 500 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return err.code, None
        return 599, None

    def _note(self, headers):
        if headers is None:
            return
        if headers.get("x-ratelimit-remaining") is not None:
            self.remaining = int(headers["x-ratelimit-remaining"])
        if headers.get("x-ratelimit-reset"):
            self.reset_at = int(headers["x-ratelimit-reset"])

    def pages(self, path, params, limit):
        params = dict(params, per_page=100)
        for page in range(1, limit + 1):
            status, items = self.get(path, dict(params, page=page))
            if status != 200 or not items:
                return
            yield from items
            if len(items) < 100:
                return


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _week_start(ts):
    # GitHub's weekly stats start on Sunday 00:00 UTC; bucket commits the same way.
    day = datetime.fromtimestamp(ts, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = day - timedelta(days=(day.weekday() + 1) % 7)
    return int(sunday.timestamp())


def _weeks_from_contributors(data):
    weeks = {}
    for contributor in data or []:
        for w in contributor.get("weeks") or []:
            if w.get("c"):
                weeks[int(w["w"])] = weeks.get(int(w["w"]), 0) + int(w["c"])
    return weeks


def _weeks_from_commits(gh, full_name, branch):
    weeks = {}
    for item in gh.pages(f"/repos/{full_name}/commits", {"sha": branch}, MAX_COMMIT_PAGES):
        stamp = ((item.get("commit") or {}).get("author") or {}).get("date") or ((item.get("commit") or {}).get("committer") or {}).get("date")
        if not stamp:
            continue
        ts = int(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        week = _week_start(ts)
        weeks[week] = weeks.get(week, 0) + 1
    return weeks


def _upsert_repo(repo, seen_at):
    """Record a repo the token can see. New repos start hidden."""
    key = {"pk": f"REPO#{repo['id']}", "sk": "META"}
    _table.update_item(
        Key=key,
        UpdateExpression=(
            "SET github_id = :id, full_name = :fn, #private = :pv, default_branch = :db, html_url = :url, "
            "gh_description = :d, archived = :ar, pushed_at = :pa, last_seen = :ls, visible_to_token = :t, "
            "#mode = if_not_exists(#mode, :hidden), first_seen = if_not_exists(first_seen, :ls)"
        ),
        ExpressionAttributeNames={"#private": "private", "#mode": "mode"},
        ExpressionAttributeValues={
            ":id": repo["id"], ":fn": repo["full_name"], ":pv": bool(repo.get("private")),
            ":db": repo.get("default_branch") or "", ":url": repo.get("html_url") or "",
            ":d": (repo.get("description") or "")[:500], ":ar": bool(repo.get("archived")),
            ":pa": repo.get("pushed_at") or "", ":ls": seen_at, ":t": True, ":hidden": "hidden",
        },
    )


def _collect_stats(gh, repos, today):
    pending = {r["id"]: r for r in repos}
    results = {}
    for attempt in range(STATS_PASSES):
        for rid, repo in list(pending.items()):
            status, data = gh.get(f"/repos/{repo['full_name']}/stats/contributors")
            if status == 200:
                results[rid] = ("contributors", _weeks_from_contributors(data))
                del pending[rid]
            elif status == 204:
                results[rid] = ("contributors", {})
                del pending[rid]
            elif status != 202:
                results[rid] = ("error", None)
                del pending[rid]
        if not pending:
            break
        if attempt < STATS_PASSES - 1:
            time.sleep(STATS_WAIT_SECONDS)
    for rid, repo in pending.items():
        results[rid] = ("commits", _weeks_from_commits(gh, repo["full_name"], repo.get("default_branch") or "main"))

    errors = []
    for repo in repos:
        source, weeks = results[repo["id"]]
        if source == "error":
            errors.append(repo["id"])
            continue
        status, languages = gh.get(f"/repos/{repo['full_name']}/languages")
        languages = languages if status == 200 and isinstance(languages, dict) else {}
        ordered = sorted(weeks.items())
        _table.put_item(Item={
            "pk": f"REPO#{repo['id']}",
            "sk": f"STATS#{today}",
            "snapshot_date": today,
            "collected_at": _now(),
            "commits": sum(weeks.values()),
            "weeks": [[w, c] for w, c in ordered],
            "weeks_active": len(ordered),
            "first_week": ordered[0][0] if ordered else 0,
            "languages": {k: int(v) for k, v in languages.items()},
            "bytes": sum(int(v) for v in languages.values()),
            "pushed_at": repo.get("pushed_at") or "",
            "archived": bool(repo.get("archived")),
            "history_source": source,
        })
    return errors


def refresh(trigger):
    started = _now()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run = {"pk": "RUN", "sk": "LATEST", "status": "running", "trigger": trigger, "started_at": started}
    _table.put_item(Item=run)
    gh = None
    try:
        gh = GitHub(_token())
        repos = list(gh.pages("/user/repos", {"sort": "pushed", "affiliation": "owner,collaborator,organization_member"}, 20))
        for repo in repos:
            _upsert_repo(repo, started)
        # Repos the token can no longer see stay recorded but stop updating,
        # so an owner's approvals aren't lost if a token is replaced.
        seen = {f"REPO#{r['id']}" for r in repos}
        listed = _table.scan(FilterExpression="sk = :m", ExpressionAttributeValues={":m": "META"}).get("Items", [])
        for row in listed:
            if row["pk"].startswith("REPO#") and row["pk"] not in seen and row.get("visible_to_token"):
                _table.update_item(Key={"pk": row["pk"], "sk": "META"}, UpdateExpression="SET visible_to_token = :f",
                                   ExpressionAttributeValues={":f": False})
        errors = _collect_stats(gh, repos, today)
        outcome = {"status": "done", "repos": len(repos), "errors": len(errors)}
    except RateLimited as limited:
        reset = datetime.fromtimestamp(limited.args[0], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if limited.args and limited.args[0] else ""
        outcome = {"status": "rate_limited", "reset_at": reset}
    except Exception as exc:  # noqa: BLE001 - the run's outcome has to be recorded either way
        outcome = {"status": "failed", "error": exc.__class__.__name__}
        if isinstance(exc, urllib.error.URLError):
            outcome["error"] = "GitHub couldn't be reached"
    outcome.update(finished_at=_now(), started_at=started, trigger=trigger,
                   api_calls=gh.calls if gh else 0, rate_remaining=gh.remaining if gh and gh.remaining is not None else -1)
    _table.put_item(Item={"pk": "RUN", "sk": "LATEST", **outcome})
    _table.put_item(Item={"pk": "RUN", "sk": f"AT#{started}", **outcome})
    print(json.dumps({k: v for k, v in outcome.items() if k != "error"}))
    return outcome


def handler(event, context):
    event = event or {}
    action = event.get("action") or ("refresh" if event.get("source") == "schedule" else "")
    if action == "refresh":
        return refresh(event.get("trigger") or "schedule")
    return {"error": "unknown action"}
