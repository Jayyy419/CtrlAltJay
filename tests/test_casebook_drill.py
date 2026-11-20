"""Drill ratings and capped Claude feedback, with a fake Claude client.

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


class Drill(Checks):
    def test_flow(self):
        cb = ddb.Table("ctrlaltjay-casebooks")
        anon = app.test_client()
        o = app.test_client(); o.post("/admin/auth", json={"passcode": "right-passcode"})

        from types import SimpleNamespace as NS
        import casebook_drill, claude_budget
        from decimal import Decimal
        sent = []; mode = {"v": "ok"}
        class FakeStream:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_final_message(self):
                if mode["v"] == "fail": raise RuntimeError("down")
                stop = {"refusal": "refusal"}.get(mode["v"], "end_turn")
                text = json.dumps({"star": {"situation": True, "task": True, "action": True, "result": False},
                                   "went_well": ["Clear situation \u2014 told in one line!"], "to_work_on": ["Add the real result.", "Say what you did, not we."]})
                return NS(usage=NS(input_tokens=1200, output_tokens=150), stop_reason=stop, content=[NS(type="text", text=text)])
        class FakeClient:
            def __init__(self): self.messages = self
            def stream(self, **kw): sent.append(kw); return FakeStream()
        app.config["CASEBOOK_DRILL_CLIENT"] = FakeClient
        app.config["OWNER_CLAUDE_API_KEY"] = "k"
        cid = o.post("/api/owner/casebooks", json={"occasion": "interview", "organisation": "Acme", "role": "Analyst"}).get_json()["id"]
        o.post(f"/api/owner/casebooks/{cid}/questions", json={"usual": True})
        v = o.get(f"/api/owner/casebooks/{cid}").get_json()
        qs = v["questions"]; q0 = qs[0]["id"]
        self.check("questions carry drill state", qs[0]["drill"] == {"box": 0, "rating": "", "last": "", "count": 0})
        self.check("drill help in view", v["drill_help"]["enabled"] and v["drill_help"]["cap"] == 1.0)
        for m, p in [("POST", f"/api/owner/casebooks/{cid}/questions/{q0}/drill"), ("POST", f"/api/owner/casebooks/{cid}/drill/feedback"), ("POST", "/api/owner/casebooks/sample/drill/feedback")]:
            r = anon.open(p, method=m, json={"rating": "got", "qid": q0, "answer": "one two three four five six"})
            self.check(f"signed out 404 {p.split('/')[-1]}", r.status_code == 404 and "no-store" in r.headers["Cache-Control"])
        self.check("signed out made no call", not sent)
        boxes = []
        for rating in ["got", "got", "got", "got", "shaky", "missed", "got"]:
            boxes.append(o.post(f"/api/owner/casebooks/{cid}/questions/{q0}/drill", json={"rating": rating}).get_json()["box"])
        self.check("boxes move as rated", boxes == [1, 2, 3, 3, 2, 0, 1])
        self.check("bad rating refused", o.post(f"/api/owner/casebooks/{cid}/questions/{q0}/drill", json={"rating": "meh"}).status_code == 400)
        self.check("unknown question 404", o.post(f"/api/owner/casebooks/{cid}/questions/aaaaaaaaaaaa/drill", json={"rating": "got"}).status_code == 404)
        d = o.get(f"/api/owner/casebooks/{cid}").get_json()["questions"][0]["drill"]
        self.check("drill stored on the question", d["box"] == 1 and d["rating"] == "got" and d["count"] == 7 and d["last"])
        self.check("short answer refused before any call", o.post(f"/api/owner/casebooks/{cid}/drill/feedback", json={"qid": q0, "answer": "too short"}).status_code == 400 and not sent)
        ans = "At my last role I noticed the team retyped forms, so I automated it."
        r = o.post(f"/api/owner/casebooks/{cid}/drill/feedback", json={"qid": q0, "answer": ans, "seconds": 75}); j = r.get_json()
        self.check("feedback returned", r.status_code == 200 and j["star"] == {"situation": True, "task": True, "action": True, "result": False})
        self.check("dashes and ! tidied", "\u2014" not in j["went_well"][0] and "!" not in j["went_well"][0])
        self.check("cost at actual", abs(j["budget"]["spent"] - (1200 * 4 + 150 * 20) / 1e6) < 1e-6 and j["budget"]["feedbacks"] == 1)
        body = sent[-1]["messages"][0]["content"]
        self.check("brief has question, answer and seconds", qs[0]["text"] in body and ans in body and 'seconds="75"' in body)
        self.check("schema output and model", sent[-1]["output_config"]["format"]["type"] == "json_schema" and sent[-1]["model"] == "claude-opus-5-5")
        self.check("answer not stored", ans not in json.dumps([dict(i) for i in cb.scan()["Items"]], default=str))
        r = o.post("/api/owner/casebooks/sample/drill/feedback", json={"qid": "s1", "answer": ans})
        self.check("sample feedback works", r.status_code == 200 and "Tell us about a time you changed how a team worked." in sent[-1]["messages"][0]["content"])
        self.check("sample bad qid 404", o.post("/api/owner/casebooks/sample/drill/feedback", json={"qid": "s9", "answer": ans}).status_code == 404)
        mode["v"] = "fail"; before = o.get(f"/api/owner/casebooks/{cid}").get_json()["drill_help"]["spent"]
        r = o.post(f"/api/owner/casebooks/{cid}/drill/feedback", json={"qid": q0, "answer": ans})
        self.check("failure refunds", r.status_code == 400 and abs(r.get_json()["budget"]["spent"] - before) < 1e-6)
        mode["v"] = "refusal"
        self.check("refusal handled", "declined" in o.post(f"/api/owner/casebooks/{cid}/drill/feedback", json={"qid": q0, "answer": ans}).get_json()["error"])
        mode["v"] = "ok"
        cb.put_item(Item={"pk": "SPEND", "sk": f"DRILL#{claude_budget.month()}", "spent_usd": Decimal("0.99"), "feedbacks": 40})
        n = len(sent)
        r = o.post(f"/api/owner/casebooks/{cid}/drill/feedback", json={"qid": q0, "answer": ans})
        self.check("cap reached refuses without calling", r.status_code == 400 and "used up" in r.get_json()["error"] and len(sent) == n)
        self.check("research spend row untouched", cb.get_item(Key={"pk": "SPEND", "sk": claude_budget.month()}).get("Item") is None)
        app.config["OWNER_CLAUDE_API_KEY"] = ""
        self.check("no key: off", not o.get(f"/api/owner/casebooks/{cid}").get_json()["drill_help"]["enabled"])


if __name__ == "__main__":
    unittest.main()
