"""The GitHub collector and Town hall approval and publishing, with GitHub faked.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json, io, urllib.error, urllib.request
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode",
                  GITHUB_TOKEN_SSM_PARAM="/ctrlaltjay/github-token", TOWN_TABLE="ctrlaltjay-town")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
for name in ("ctrlaltjay-casebooks", "ctrlaltjay-town", "ctrlaltjay-public-city"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
boto3.client("ssm", region_name="ap-southeast-1").put_parameter(Name="/ctrlaltjay/github-token", Value="ghp_testtoken", Type="SecureString")
T = ddb.Table("ctrlaltjay-town")
sys.path.insert(0, os.path.join(ROOT, "town_collector"))
import collector
collector.STATS_WAIT_SECONDS = 0
collector.time.sleep = lambda s: None

REPOS = [{"id": 101, "full_name": "jay/public-app", "private": False, "default_branch": "main", "html_url": "https://github.com/jay/public-app",
          "description": "Public one", "archived": False, "pushed_at": "2026-11-18T03:00:00Z"},
         {"id": 202, "full_name": "jay/secret-app", "private": True, "default_branch": "dev", "html_url": "https://github.com/jay/secret-app",
          "description": "Private one", "archived": True, "pushed_at": "2025-01-02T00:00:00Z"},
         {"id": 303, "full_name": "jay/broken", "private": False, "default_branch": "main", "html_url": "", "description": None, "archived": False, "pushed_at": "2026-01-01T00:00:00Z"}]
W1, W2 = 1700352000, 1700956800  # two Sundays
calls = {"stats_101": 0, "auth": set(), "paths": []}
mode = {"rate": False}

class Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status = status; self._b = body; self.headers = headers or {"x-ratelimit-remaining": "4990", "x-ratelimit-reset": "1795100000"}
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(req, timeout=None):
    url = req.full_url
    calls["auth"].add(req.get_header("Authorization")); calls["paths"].append(url)
    assert req.get_header("X-github-api-version") == "2022-11-28"
    if mode["rate"]:
        raise urllib.error.HTTPError(url, 403, "rate", {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1795100000"}, io.BytesIO(b"{}"))
    path = url.split("api.github.com")[1]
    if path.startswith("/user/repos"):
        return Resp(200, json.dumps(REPOS).encode())
    if path == "/repos/jay/public-app/stats/contributors":
        calls["stats_101"] += 1
        if calls["stats_101"] == 1:
            return Resp(202)
        return Resp(200, json.dumps([{"total": 5, "weeks": [{"w": W1, "a": 1, "d": 0, "c": 3}, {"w": W2, "a": 0, "d": 0, "c": 0}]},
                                     {"total": 2, "weeks": [{"w": W1, "a": 1, "d": 0, "c": 1}, {"w": W2, "a": 0, "d": 0, "c": 1}]}]).encode())
    if path == "/repos/jay/secret-app/stats/contributors":
        return Resp(202)
    if path.startswith("/repos/jay/secret-app/commits"):
        assert "sha=dev" in path
        if "page=1" in path:
            return Resp(200, json.dumps([{"commit": {"author": {"date": "2023-11-20T10:00:00Z"}}}, {"commit": {"author": {"date": "2023-11-22T10:00:00Z"}}},
                                         {"commit": {"author": {"date": "2023-11-27T10:00:00Z"}}}]).encode())
        return Resp(200, b"[]")
    if path == "/repos/jay/broken/stats/contributors":
        raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b"{}"))
    if path.endswith("/languages"):
        return Resp(200, json.dumps({"Python": 9000, "HTML": 1000} if "public" in path else {"TypeScript": 500}).encode())
    raise AssertionError("unexpected " + path)

collector.urllib.request.urlopen = fake_urlopen


class TownHall(Checks):
    def test_flow(self):

        out = collector.handler({"action": "refresh", "trigger": "manual"}, None)
        self.check(f"run done {out}", out["status"] == "done" and out["repos"] == 3 and out["errors"] == 1)
        self.check("token sent as bearer, never in a URL", calls["auth"] == {"Bearer ghp_testtoken"} and all("ghp_" not in u for u in calls["paths"]))
        meta = {r["pk"]: r for r in T.scan()["Items"] if r["sk"] == "META"}
        self.check("new repos start hidden", all(m["mode"] == "hidden" for m in meta.values()))
        self.check("real names stored owner-side", meta["REPO#202"]["full_name"] == "jay/secret-app" and meta["REPO#202"]["private"] is True)
        stats = {r["pk"]: r for r in T.scan()["Items"] if r["sk"].startswith("STATS#")}
        s1 = stats["REPO#101"]
        self.check("202 retried then contributors used", calls["stats_101"] == 2 and s1["history_source"] == "contributors")
        self.check("weekly commits summed across contributors", [[int(a), int(b)] for a, b in s1["weeks"]] == [[W1, 4], [W2, 1]] and int(s1["commits"]) == 5 and int(s1["weeks_active"]) == 2)
        self.check("bytes and languages", int(s1["bytes"]) == 10000 and int(s1["languages"]["Python"]) == 9000)
        s2 = stats["REPO#202"]
        self.check("stats never ready -> commit paging fallback on the default branch", s2["history_source"] == "commits" and int(s2["commits"]) == 3)
        self.check("commit dates bucketed into Sunday weeks", [int(c) for _, c in s2["weeks"]] == [2, 1] and all(int(w) % 86400 == 0 for w, _ in s2["weeks"]))
        self.check("archived recorded", s2["archived"] is True)
        self.check("errored repo has no snapshot", "REPO#303" not in stats)
        run = T.get_item(Key={"pk": "RUN", "sk": "LATEST"})["Item"]
        self.check("run log kept", run["status"] == "done" and int(run["rate_remaining"]) == 4990 and any(r["sk"].startswith("AT#") for r in T.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq("RUN"))["Items"]))
        self.check("collector never writes the public table", ddb.Table("ctrlaltjay-public-city").scan()["Count"] == 0)

        # owner's mode survives a refresh; repo the token loses is flagged, not deleted
        T.update_item(Key={"pk": "REPO#101", "sk": "META"}, UpdateExpression="SET #m = :a", ExpressionAttributeNames={"#m": "mode"}, ExpressionAttributeValues={":a": "approved"})
        REPOS.pop(2)
        collector.handler({"action": "refresh"}, None)
        meta = {r["pk"]: r for r in T.scan()["Items"] if r["sk"] == "META"}
        self.check("approval survives refresh", meta["REPO#101"]["mode"] == "approved")
        self.check("repo the token can't see any more is flagged, kept", meta["REPO#303"]["visible_to_token"] is False)

        mode["rate"] = True
        out = collector.handler({"action": "refresh"}, None)
        self.check("rate limit recorded with reset time", out["status"] == "rate_limited" and out["reset_at"])
        mode["rate"] = False
        self.check("unknown action refused", collector.handler({"action": "x"}, None) == {"error": "unknown action"})

        # --- app side
        invoked = []
        class StubLambda:
            def invoke(self, **kw): invoked.append(kw); return {"StatusCode": 202}
        real = boto3.client
        boto3.client = lambda name, *a, **k: StubLambda() if name == "lambda" else real(name, *a, **k)
        sys.path.insert(0, ROOT)
        import app as appmod
        app = appmod.app
        anon = app.test_client()
        for m, p in [("GET", "/owner/townhall"), ("GET", "/owner/townhall/app.js"), ("GET", "/owner/townhall/app.css"), ("GET", "/api/owner/townhall/repos"), ("POST", "/api/owner/townhall/refresh")]:
            r = anon.open(p, method=m)
            self.check(f"signed out 404 {m} {p}", r.status_code == 404 and b"secret-app" not in r.data and "no-store" in r.headers.get("Cache-Control", ""))
        self.check("signed out: nothing invoked", not invoked)
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        r = o.get("/api/owner/townhall/repos"); d = r.get_json()
        self.check("owner sees repos with stats, private headers", r.status_code == 200 and len(d["repos"]) == 3 and "no-store" in r.headers["Cache-Control"] and "noindex" in r.headers["X-Robots-Tag"])
        row = [x for x in d["repos"] if x["id"] == 101][0]
        self.check("main language and counts", row["stats"]["main_language"] == "Python" and row["stats"]["commits"] == 5 and row["mode"] == "approved")
        r = o.post("/api/owner/townhall/refresh")
        self.check("refresh: async invoke, 202", r.status_code == 202 and invoked[-1]["InvocationType"] == "Event" and json.loads(invoked[-1]["Payload"]) == {"action": "refresh", "trigger": "manual"})
        self.check("second refresh refused while running", o.post("/api/owner/townhall/refresh").status_code == 409 and len(invoked) == 1)
        for p in ("/owner/townhall", "/owner/townhall/app.js", "/owner/townhall/app.css"):
            self.check(f"owner gets {p}", o.get(p).status_code == 200)
        self.check("asset whitelist", o.get("/owner/townhall/townhall.py").status_code == 404)
        tools = o.get("/api/owner/tools").get_json()
        self.check("Town hall in owner tools", any(t["href"] == "/owner/townhall" for t in tools))
        pub = anon.get("/").data.decode() + anon.get("/sitemap.xml").data.decode() + anon.get("/api/public-data").data.decode()
        self.check("public page, sitemap, public data: no repo names, no town hall", all(x not in pub for x in ("secret-app", "public-app", "townhall")))
        self.check("robots disallows owner paths", b"Disallow: /owner/" in anon.get("/robots.txt").data)
        # --- Commit City public page
        r = anon.get("/api/city"); c = r.get_json()
        self.check("city: sample when nothing published", c["sample"] is True and len(c["buildings"]) == 6 and "max-age=300" in r.headers["Cache-Control"])
        self.check("city: sample has no real repo names", all(x not in json.dumps(c) for x in ("secret-app", "public-app", "jay/")))
        self.check("city page renders", anon.get("/city").status_code == 200)
        import commit_city, inspect
        src = inspect.getsource(commit_city)
        self.check("public module never touches the town table or GitHub", "ctrlaltjay-town\"" not in src and "TOWN_TABLE" not in src and "api.github.com" not in src)
        self.check("sitemap doesn't list /city yet", b"/city" not in anon.get("/sitemap.xml").data)
        # --- step 4: modes, approval, the public snapshot
        ddb.Table("ctrlaltjay-portfolio-items").put_item(Item={"id": "item-live", "section": "project", "title": "Live project"})
        ddb.Table("ctrlaltjay-portfolio-items").put_item(Item={"id": "item-draft", "section": "project", "title": "Draft one", "is_draft": True})
        for m, p in [("PATCH", "/api/owner/townhall/repos/202"), ("POST", "/api/owner/townhall/repos/202/approve"), ("POST", "/api/owner/townhall/repos/202/drawer"),
                     ("GET", "/api/owner/townhall/repos/202/preview"), ("GET", "/api/owner/townhall/repos/202/preview-city"), ("GET", "/owner/townhall/preview/202"),
                     ("POST", "/api/owner/townhall/publish"), ("GET", "/api/owner/townhall/approvals")]:
            r = anon.open(p, method=m, json={})
            self.check(f"signed out 404 {m} {p}", r.status_code == 404 and b"secret" not in r.data)
        T.update_item(Key={"pk": "REPO#101", "sk": "META"}, UpdateExpression="SET #m = :h", ExpressionAttributeNames={"#m": "mode"}, ExpressionAttributeValues={":h": "hidden"})
        r = o.post("/api/owner/townhall/repos/202/approve")
        self.check("private can't be approved without a public name and description", r.status_code == 400 and "public name" in r.get_json()["error"])
        self.check("project page must be live", o.patch("/api/owner/townhall/repos/202", json={"project_item_id": "item-draft"}).status_code == 400)
        o.patch("/api/owner/townhall/repos/202", json={"public_name": "Quiet Tower", "description": "Something I built for a client.", "project_item_id": "item-live"})
        pv = o.get("/api/owner/townhall/repos/202/preview").get_json()
        self.check("preview shows exactly the public building", pv["building"]["name"] == "Quiet Tower" and pv["building"]["size_class"] == 1 and not pv["problems"])
        self.check("preview page owner-only, noindex", o.get("/owner/townhall/preview/202").status_code == 200 and "noindex" in o.get("/owner/townhall/preview/202").headers["X-Robots-Tag"])
        self.check("nothing public before approval", anon.get("/api/city").get_json()["sample"] is True)
        r = o.post("/api/owner/townhall/repos/202/approve")
        self.check("private approved", r.status_code == 200)
        pub = anon.get("/api/city").get_json()
        blob = json.dumps(pub)
        b = pub["buildings"][0]
        self.check("public snapshot has only the approved building", pub["sample"] is False and len(pub["buildings"]) == 1 and b["name"] == "Quiet Tower")
        self.check("private: no real name, owner, branch, link, bytes or archived flag", all(x not in blob for x in ("secret-app", "jay/", "\"dev\"", "github.com", "html_url", "full_name", "default_branch")) and "bytes" not in b and "github_url" not in b and b["archived"] is False)
        self.check("private: allowed fields only", set(b) <= {"slug", "name", "description", "languages", "main_language", "color", "weeks", "first_week", "commits", "weeks_active", "last_push", "project_url", "tour_url", "size_class", "archived"})
        self.check("private: weekly counts, shares, size class", b["weeks"] and all(len(w) == 2 for w in b["weeks"]) and b["languages"][0][0] == "TypeScript" and b["languages"][0][1] == 1.0 and b["size_class"] == 1)
        self.check("project link to the live item", b["project_url"] == "/#item/item-live")
        self.check("hidden repos appear nowhere, not even as a count", "broken" not in blob and "public-app" not in blob and len(pub["buildings"]) == 1)
        page = anon.get("/").data.decode(); sm = anon.get("/sitemap.xml").data.decode()
        self.check("site links the city once published", 'href="/city"' in page and "/city" in sm)
        self.check("hidden and private real names not in page or sitemap", all(x not in page + sm for x in ("secret-app", "broken", "public-app")))
        # public repo approval publishes link and bytes; renaming republishes
        T.update_item(Key={"pk": "REPO#101", "sk": "META"}, UpdateExpression="SET visible_to_token = :t", ExpressionAttributeValues={":t": True})
        self.check("public approved without extra words", o.post("/api/owner/townhall/repos/101/approve").status_code == 200)
        pub = anon.get("/api/city").get_json(); names = [x["name"] for x in pub["buildings"]]
        pb = [x for x in pub["buildings"] if x["name"] == "public-app"][0]
        self.check("public repo: name, link and bytes", pb["github_url"] == "https://github.com/jay/public-app" and pb["bytes"] == 10000 and "Quiet Tower" in names)
        o.patch("/api/owner/townhall/repos/202", json={"public_name": "Quiet Spire"})
        self.check("renaming an approved building republishes", any(x["name"] == "Quiet Spire" for x in anon.get("/api/city").get_json()["buildings"]))
        r = o.post("/api/owner/townhall/repos/202/drawer")
        pub = anon.get("/api/city").get_json()
        self.check("drawer removes it from the public city at once", r.status_code == 200 and all(x["name"] != "Quiet Spire" for x in pub["buildings"]) and len(pub["buildings"]) == 1)
        self.check("publish latest stats", o.post("/api/owner/townhall/publish").get_json()["buildings"] == 1)
        log = o.get("/api/owner/townhall/approvals").get_json()
        self.check("approvals log records each action with a time", [x["action"] for x in log][:5] == ["publish", "drawer", "update", "approve", "approve"] and all(x["at"] for x in log))
        o.post("/api/owner/townhall/repos/101/drawer")
        pub = anon.get("/api/city").get_json()
        self.check("empty city after everything is in the drawer", pub["sample"] is False and pub["buildings"] == [])
        self.check("city link gone when nothing is published", 'href="/city"' not in anon.get("/").data.decode())
        self.check("bad repo id 404", o.get("/api/owner/townhall/repos/abc/preview").status_code == 404 and o.get("/api/owner/townhall/repos/999/preview").status_code == 404)


if __name__ == "__main__":
    unittest.main()
