"""Starting research from the app: budget checks and run state.

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
ddb.create_table(TableName="ctrlaltjay-casebooks", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
T = ddb.Table("ctrlaltjay-casebooks")
invoked = []
class StubLambda:
    def invoke(self, **kw): invoked.append(kw); return {"StatusCode": 202}
real_client = boto3.client
boto3.client = lambda name, *a, **k: StubLambda() if name == "lambda" else real_client(name, *a, **k)
sys.path.insert(0, ROOT)
import app as appmod
from datetime import datetime, timezone, timedelta
from decimal import Decimal
app = appmod.app


class ResearchApi(Checks):
    def test_flow(self):

        anon = app.test_client()
        self.check("signed out 404", anon.post("/api/owner/casebooks/abcdef123456/research", json={}).status_code == 404 and not invoked)
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        cid = o.post("/api/owner/casebooks", json={"occasion": "interview", "organisation": "Acme", "role": "Analyst"}).get_json()["id"]
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("view shows caps", v["research"]["status"] == "not_started" and v["research"]["per_case"] == 3 and v["research"]["per_month"] == 10 and v["research"]["available"] == 3)
        r = o.post(f"/api/owner/casebooks/{cid}/research", json={"posting_text": "We need SQL." * 3})
        p = json.loads(invoked[-1]["Payload"])
        self.check("start: 202 and async invoke", r.status_code == 202 and invoked[-1]["InvocationType"] == "Event" and invoked[-1]["FunctionName"] == "ctrlaltjay-casebook-research")
        self.check("payload carries run, budget and posting", p["case_id"] == cid and len(p["run_id"]) == 32 and p["budget_usd"] == 3 and "We need SQL." in p["posting_text"])
        meta = T.get_item(Key={"pk": f"CASE#{cid}", "sk": "META"})["Item"]
        self.check("queued, run id stored, posting not stored", meta["research_status"] == "queued" and meta["research_run"] == p["run_id"] and "We need SQL" not in json.dumps(meta, default=str))
        self.check("second start refused while running", o.post(f"/api/owner/casebooks/{cid}/research", json={}).status_code == 409 and len(invoked) == 1)
        T.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET research_started_at = :t",
                      ExpressionAttributeValues={":t": (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("stale run shows as failed", v["research"]["status"] == "failed" and v["research"]["error"])
        self.check("stale run can be restarted", o.post(f"/api/owner/casebooks/{cid}/research", json={}).status_code == 202)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        T.put_item(Item={"pk": "SPEND", "sk": month, "spent_usd": Decimal("8.2"), "runs": 4})
        T.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET research_status = :d", ExpressionAttributeValues={":d": "done"})
        r = o.post(f"/api/owner/casebooks/{cid}/research", json={})
        self.check("budget limited to what's left in the month", r.status_code == 202 and abs(json.loads(invoked[-1]["Payload"])["budget_usd"] - 1.8) < 1e-9)
        T.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET research_status = :d", ExpressionAttributeValues={":d": "done"})
        T.put_item(Item={"pk": "SPEND", "sk": month, "spent_usd": Decimal("9.7"), "runs": 5})
        n = len(invoked)
        r = o.post(f"/api/owner/casebooks/{cid}/research", json={})
        self.check("refused when month nearly spent", r.status_code == 400 and "used up" in r.get_json()["error"] and len(invoked) == n)
        self.check("spend row not listed as a case", all(c["id"] == cid for c in o.get("/api/owner/casebooks").get_json()))
        # research output rendered with sources
        T.put_item(Item={"pk": f"CASE#{cid}", "sk": "SRC#001", "id": 1, "url": "https://x.example", "title": "X", "date": "March 3, 2026", "supports": "Reported"})
        T.put_item(Item={"pk": f"CASE#{cid}", "sk": "Q#aaaaaaaaaaaa", "id": "aaaaaaaaaaaa", "origin": "research", "text": "Conflict?", "kind": "behavioural",
                         "provenance": "reported", "source_ids": [1], "why": "w", "requirement": "", "competencies": ["Teamwork"], "created_at": "z"})
        T.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET research_brief = :b, questions_for_them = :q, research_topics = :t",
                      ExpressionAttributeValues={":b": {"values": [{"text": "Clients first", "source_ids": [1, 7]}], "format": [], "recent": [], "not_found": ["Pay"], "posting_summary": ""},
                                                 ":q": [{"text": "Ask this", "source_ids": [1]}], ":t": ["Annual report"]})
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        q = [x for x in v["questions"] if x["text"] == "Conflict?"][0]
        self.check("question sources resolved", q["sources"] == [{"id": 1, "title": "X", "url": "https://x.example", "date": "March 3, 2026", "supports": "Reported"}])
        self.check("brief sources resolved, unknown dropped", v["brief"]["values"][0]["sources"][0]["id"] == 1 and len(v["brief"]["values"][0]["sources"]) == 1 and v["brief"]["not_found"] == ["Pay"])
        self.check("questions for them with sources", v["questions_for_them"][0]["sources"][0]["url"] == "https://x.example")
        self.check("topics become loose ends", any(l["kind"] == "revise" and l["text"] == "Annual report" for l in v["loose_ends"]))


if __name__ == "__main__":
    unittest.main()
