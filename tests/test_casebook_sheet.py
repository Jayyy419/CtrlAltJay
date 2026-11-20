"""Questions for them, the opening line, and how research re-runs keep the owner's picks.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  SECRET_KEY="test-secret-key-0123456789abcdefghijkl", ADMIN_PASSCODE="right-passcode",
                  CASEBOOK_API_KEY_SSM_PARAM="/x", CASEBOOKS_TABLE="ctrlaltjay-casebooks")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
for name in ("ctrlaltjay-portfolio-items", "ctrlaltjay-resume-items", "ctrlaltjay-skills", "ctrlaltjay-stories"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
for name in ("ctrlaltjay-casebooks", "ctrlaltjay-public-city", "ctrlaltjay-town"):
    ddb.create_table(TableName=name, KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
sys.path.insert(0, ROOT)
import app as appmod
app = appmod.app


class QuestionsForThem(Checks):
    def test_flow(self):
        cb = ddb.Table("ctrlaltjay-casebooks")
        anon = app.test_client()
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})
        cid = o.post("/api/owner/casebooks", json={"occasion": "interview", "organisation": "Acme", "role": "Analyst", "date": "2026-12-03", "opener": "I like building things people use."}).get_json()["id"]
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        self.check("opener saved on create", v["casebook"]["opener"] == "I like building things people use.")
        o.patch(f"/api/owner/casebooks/{cid}", json={"opener": "  A   new line.  "})
        self.check("opener edited and trimmed", o.get(f"/api/owner/casebooks/{cid}").get_json()["casebook"]["opener"] == "A   new line.")
        self.check("opener capped", len(o.patch(f"/api/owner/casebooks/{cid}", json={"opener": "x" * 900}).get_json()["opener"]) == 400)
        # research-style items without ids
        cb.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET questions_for_them = :q",
                       ExpressionAttributeValues={":q": [{"text": "How is feedback given?", "source_ids": []}, {"text": "What does week one look like?", "source_ids": []}]})
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        t = v["questions_for_them"]
        self.check("research items get stable ids", len(t) == 2 and all(x["id"].startswith("r") for x in t) and t[0]["id"] == o.get(f"/api/owner/casebooks/{cid}").get_json()["questions_for_them"][0]["id"])
        for m, p in [("POST", f"/api/owner/casebooks/{cid}/theirs"), ("PATCH", f"/api/owner/casebooks/{cid}/theirs/{t[0]['id']}"), ("DELETE", f"/api/owner/casebooks/{cid}/theirs/{t[0]['id']}")]:
            r = anon.open(p, method=m, json={"text": "x"})
            self.check(f"signed out 404 {m} theirs", r.status_code == 404 and "no-store" in r.headers["Cache-Control"])
        r = o.post(f"/api/owner/casebooks/{cid}/theirs", json={"text": "Which teams would I work with?"})
        t = r.get_json()["questions_for_them"]
        self.check("own question added and on the sheet", r.status_code == 201 and t[-1]["own"] and t[-1]["ask"])
        self.check("blank refused", o.post(f"/api/owner/casebooks/{cid}/theirs", json={"text": "  "}).status_code == 400)
        t = o.patch(f"/api/owner/casebooks/{cid}/theirs/{t[0]['id']}", json={"ask": True}).get_json()["questions_for_them"]
        self.check("research question put on the sheet", t[0]["ask"] and not t[0]["own"])
        t = o.patch(f"/api/owner/casebooks/{cid}/theirs/{t[1]['id']}", json={"text": "What does the first month look like?"}).get_json()["questions_for_them"]
        self.check("edited research question becomes yours", t[1]["text"] == "What does the first month look like?" and t[1]["own"])
        t = o.delete(f"/api/owner/casebooks/{cid}/theirs/{t[0]['id']}").get_json()["questions_for_them"]
        self.check("removed", [x["text"] for x in t] == ["What does the first month look like?", "Which teams would I work with?"])
        self.check("unknown id 404", o.patch(f"/api/owner/casebooks/{cid}/theirs/zzz", json={"ask": True}).status_code == 404)
        meta = cb.get_item(Key={"pk": f"CASE#{cid}", "sk": "META"})["Item"]
        self.check("removed research question remembered", meta["theirs_dismissed"] == ["How is feedback given?"])
        for i in range(10): o.post(f"/api/owner/casebooks/{cid}/theirs", json={"text": f"Q{i}"})
        self.check("capped at 12", o.post(f"/api/owner/casebooks/{cid}/theirs", json={"text": "one more"}).status_code == 400)
        # Research re-run keeps own, keeps picks, skips dismissed
        sys.path.insert(0, os.path.join(ROOT, "casebook_research"))
        import research
        class R: pass
        run = R(); run.key = {"pk": f"CASE#{cid}", "sk": "META"}; run.run_id = "r1"
        cb.update_item(Key=run.key, UpdateExpression="SET research_run = :r, questions_for_them = :q",
                       ExpressionAttributeValues={":r": "r1", ":q": [{"text": "Old research Q", "source_ids": [], "ask": True}, {"id": "own1", "text": "Mine", "own": True, "ask": False}]})
        meta = cb.get_item(Key=run.key)["Item"]
        research._store(run, meta, {"sources": [], "questions": [], "brief": {}, "topics": [], "competencies": [],
            "questions_for_them": [{"text": "Old research Q", "source_ids": []}, {"text": "How is feedback given?", "source_ids": []}, {"text": "Brand new", "source_ids": []}]})
        t = cb.get_item(Key=run.key)["Item"]["questions_for_them"]
        self.check("re-run keeps pick, skips dismissed, keeps own", [(x["text"], bool(x.get("ask"))) for x in t] == [("Old research Q", True), ("Brand new", False), ("Mine", False)])
        # sample sheet data
        s = o.get("/api/owner/casebooks/sample").get_json()
        self.check("sample has opener and picks", s["casebook"]["opener"] and sum(1 for x in s["questions_for_them"] if x["ask"]) == 2)


if __name__ == "__main__":
    unittest.main()
