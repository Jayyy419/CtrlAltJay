"""Draft help for tour stops: the monthly cap, with a fake Claude client.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
for name in ("ctrlaltjay-public-city", "ctrlaltjay-town"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
town = ddb.Table("ctrlaltjay-town"); pub = ddb.Table("ctrlaltjay-public-city")
SHA = "a" * 40
def meta(i, full, private, mode="approved", **kw):
    town.put_item(Item=dict({"pk": f"REPO#{i}", "sk": "META", "github_id": i, "full_name": full, "private": private, "mode": mode,
        "default_branch": "main", "html_url": f"https://github.com/{full}", "visible_to_token": True, "pushed_at": "2026-11-18T00:00:00Z"}, **kw))
    town.put_item(Item={"pk": f"REPO#{i}", "sk": "STATS#2026-11-19", "commits": 10, "weeks": [[1700000000, 3]], "languages": {"Python": 1000}, "bytes": 1000})
meta(101, "jay/pubrepo", False)
meta(202, "jay/secret-client-work", True, public_name="Client dashboard", description="A dashboard I built.")
meta(303, "jay/hiddenrepo", False, mode="hidden")
FILES = {
 "api/handlers.py": ["import x"] + [f"def f{i}(): return {i}" for i in range(1, 60)],
 "core/router.py": ["def route(p):", "    return p", 'token = "ghp_' + "a1B2" * 9 + '"', "x = 1"],
 "client_acme/billing.py": ["def bill(c):", "    return c.total * 1.09"],
 "README.md": ["# hello"],
}
calls = []
def fake(payload):
    calls.append(payload)
    if payload["action"] == "tree":
        return {"sha": SHA, "branch": "main", "truncated": False, "files": [[p, len("\n".join(l))] for p, l in FILES.items()]}
    if payload["action"] == "file":
        if payload["path"] not in FILES: return {"error": "That file isn't there at this commit."}
        return {"lines": FILES[payload["path"]]}
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app
app.config["TOWN_COLLECTOR_CALL"] = fake


class DraftHelp(Checks):
    def test_flow(self):
        res = []


        from types import SimpleNamespace as NS
        import townhall_draft
        sent = []
        mode = {"v": "ok"}
        class FakeStream:
            def __init__(self, kw): self.kw = kw
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self):
                if mode["v"] == "fail": raise RuntimeError("network")
                stop = {"refusal": "refusal", "cut": "max_tokens"}.get(mode["v"], "end_turn")
                text = json.dumps({"title": "Finding the right handler", "explanation": "Each ping lands here \u2014 a robust check runs first! Then it's handed on."})
                return NS(usage=NS(input_tokens=900, output_tokens=120), stop_reason=stop, content=[NS(type="text", text=text)])
        class FakeClient:
            def __init__(self): self.messages = self
            def stream(self, **kw): sent.append(kw); return FakeStream(kw)
        app.config["TOWN_DRAFT_CLIENT"] = FakeClient
        app.config["TOWN_DRAFT_API_KEY"] = "test-key"
        anon = app.test_client()
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        o.post("/api/owner/townhall/tours/202/tree")
        d = o.post("/api/owner/townhall/tours/202/stops", json={"path": "client_acme/billing.py", "start": 1, "end": 2}).get_json()
        sid = d["stops"][0]["id"]
        self.check("draft help shown with budget", d["draft_help"]["enabled"] and d["draft_help"]["cap"] == 1.0)
        r = anon.post(f"/api/owner/townhall/tours/202/stops/{sid}/draft")
        self.check("signed out 404 and no call", r.status_code == 404 and not sent)
        r = o.post(f"/api/owner/townhall/tours/202/stops/{sid}/draft"); j = r.get_json()
        self.check("draft returned", r.status_code == 200 and j["title"] == "Finding the right handler")
        self.check("dashes and exclamation tidied", "\u2014" not in j["explanation"] and "!" not in j["explanation"])
        self.check("banned word flagged for a check", j["check_words"] == ["robust"])
        exp = (900 * 4 + 120 * 20) / 1e6
        self.check("cost recorded at actual, not reserve", abs(j["budget"]["spent"] - exp) < 1e-6 and j["budget"]["drafts"] == 1)
        kw = sent[-1]; body = kw["messages"][0]["content"]
        self.check("model and schema from config", kw["model"] == "claude-opus-5-5" and kw["output_config"]["format"]["type"] == "json_schema")
        self.check("brief has no path or real repo name", "client_acme" not in body and "secret-client-work" not in body and "billing.py" not in body)
        self.check("brief marks lines", "   1* def bill(c):" in body)
        self.check("draft not saved", o.get("/api/owner/townhall/tours/202").get_json()["stops"][0]["title"] == "")
        mode["v"] = "fail"
        before = o.get("/api/owner/townhall/tours/202").get_json()["draft_help"]["spent"]
        r = o.post(f"/api/owner/townhall/tours/202/stops/{sid}/draft")
        after = r.get_json()["budget"]["spent"]
        self.check("failure gives plain error and refunds", r.status_code == 400 and "couldn't be reached" in r.get_json()["error"] and abs(after - before) < 1e-6)
        mode["v"] = "refusal"
        r = o.post(f"/api/owner/townhall/tours/202/stops/{sid}/draft")
        self.check("refusal handled", r.status_code == 400 and "declined" in r.get_json()["error"])
        mode["v"] = "ok"
        # Push the month to the cap: the next request is refused before any call.
        import boto3 as _b
        town.put_item(Item={"pk": "SPEND", "sk": f"DRAFT#{townhall_draft._month()}", "spent_usd": __import__("decimal").Decimal("0.99"), "drafts": 50})
        n = len(sent)
        r = o.post(f"/api/owner/townhall/tours/202/stops/{sid}/draft")
        self.check("cap reached refuses without calling", r.status_code == 400 and "used up" in r.get_json()["error"] and len(sent) == n)
        app.config["TOWN_DRAFT_API_KEY"] = ""
        self.check("no key: hidden", not o.get("/api/owner/townhall/tours/202").get_json()["draft_help"]["enabled"])


if __name__ == "__main__":
    unittest.main()
