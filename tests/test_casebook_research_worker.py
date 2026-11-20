"""The research worker: provenance checks, caps and cost, with a fake Claude client.

Runs in its own process with AWS faked by moto; see tests/run_all.py.
"""
import os, sys, json, types
import unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import Checks
os.environ.update(AWS_DEFAULT_REGION="ap-southeast-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
                  CASEBOOK_API_KEY_SSM_PARAM="/ctrlaltjay/casebook/anthropic-api-key", CASEBOOKS_TABLE="ctrlaltjay-casebooks")
from moto import mock_aws
mock_aws().start()
import boto3
ddb = boto3.resource("dynamodb", region_name="ap-southeast-1")
ddb.create_table(TableName="ctrlaltjay-casebooks", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
    AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
T = ddb.Table("ctrlaltjay-casebooks")
ssm = boto3.client("ssm", region_name="ap-southeast-1")
sys.path.insert(0, os.path.join(ROOT, "casebook_research"))
import research

class B(dict):
    def __getattr__(self, k): return self[k]
    def model_dump(self): return json.loads(json.dumps(self))
def usage(i, o, s=0): return types.SimpleNamespace(input_tokens=i, output_tokens=o, cache_read_input_tokens=0, cache_creation_input_tokens=0, server_tool_use=types.SimpleNamespace(web_search_requests=s))
def msg(content, stop, u): return types.SimpleNamespace(content=[B(c) for c in content], stop_reason=stop, usage=u)

SEARCH1 = msg([{"type": "server_tool_use", "name": "web_search", "input": {"query": "Acme interview questions"}},
               {"type": "web_search_tool_result", "content": [{"url": "https://www.glassdoor.com/acme", "title": "Acme interviews", "page_age": "March 3, 2026"},
                                                               {"url": "https://acme.example/values", "title": "Our values", "page_age": None},
                                                               {"url": "https://unused.example", "title": "Unused", "page_age": None}]}], "pause_turn", usage(20000, 1000, 4))
SEARCH2 = msg([{"type": "text", "text": "Candidates report being asked about a time they handled conflict.",
                "citations": [{"type": "web_search_result_location", "url": "https://www.glassdoor.com/acme", "title": "Acme interviews", "cited_text": "x"}]},
               {"type": "text", "text": " Acme values client focus.", "citations": [{"url": "https://acme.example/values", "title": "Our values"}]}],
              "end_turn", usage(30000, 2000, 3))
WRITE = {"values": [{"text": "Client focus comes first.", "source_ids": [2]}], "format": [{"text": "Two rounds.", "source_ids": [9]}],
         "recent": [], "not_found": ["Salary bands"], "posting_summary": "An analyst role.",
         "competencies": ["Client focus", "Teamwork"],
         "questions": [
            {"kind": "behavioural", "text": "Tell us about handling conflict.", "why": "Reported often.", "provenance": "reported", "source_ids": [1], "requirement": "", "competencies": ["Teamwork"]},
            {"kind": "technical", "text": "Have they asked about SQL?", "why": "x", "provenance": "reported", "source_ids": [42], "requirement": "", "competencies": []},
            {"kind": "technical", "text": "Walk us through a SQL query.", "why": "Posting asks for it.", "provenance": "posting", "source_ids": [], "requirement": "strong SQL skills", "competencies": []},
            {"kind": "case", "text": "Size a market.", "why": "Made up requirement.", "provenance": "posting", "source_ids": [], "requirement": "market sizing wizardry", "competencies": []},
            {"kind": "motivation", "text": "Why Acme?", "why": "Common.", "provenance": "usual", "source_ids": [1], "requirement": "zz", "competencies": []},
            {"kind": "weird", "text": "Odd kind", "why": "", "provenance": "usual", "source_ids": [], "requirement": "", "competencies": []}],
         "questions_for_them": [{"text": "How do analysts get client time?", "source_ids": [2]}],
         "topics_to_revise": ["Acme's latest results"], "sources": [{"id": 1, "supports": "Reported questions"}, {"id": 2, "supports": "Values"}]}
WRITE_MSG = msg([{"type": "text", "text": json.dumps(WRITE)}], "end_turn", usage(8000, 3000))

class FakeStream:
    def __init__(self, m): self.m = m
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.m
class FakeClient:
    script = []
    calls = []
    def __init__(self, api_key=None, max_retries=None): assert api_key == "sk-test"
    @property
    def messages(self): return self
    def stream(self, **kw):
        FakeClient.calls.append(kw)
        m = FakeClient.script.pop(0)
        if isinstance(m, Exception): raise m
        return FakeStream(m)
fake = types.ModuleType("anthropic"); fake.Anthropic = FakeClient
class AuthenticationError(Exception): pass
fake.AuthenticationError = AuthenticationError
sys.modules["anthropic"] = fake



class ResearchWorker(Checks):
    def test_flow(self):
        def setup(cid, run, status="queued", **extra):
            T.put_item(Item={"pk": f"CASE#{cid}", "sk": "META", "id": cid, "occasion": "interview", "organisation": "Acme", "role": "Analyst",
                             "research_status": status, "research_run": run, "competencies": ["Teamwork", "Communication"], **extra})
            T.put_item(Item={"pk": f"CASE#{cid}", "sk": "Q#own000000001", "id": "own000000001", "text": "Why Acme?", "provenance": "own", "kind": "motivation", "created_at": "a"})

        self.check("check: no key", research.handler({"action": "check"}, None) == {"key_configured": False})
        ssm.put_parameter(Name="/ctrlaltjay/casebook/anthropic-api-key", Value="sk-test", Type="SecureString")
        self.check("check: key", research.handler({"action": "check"}, None) == {"key_configured": True})

        cid, run = "a" * 12, "b" * 32
        setup(cid, run, posting_url="")
        FakeClient.script = [SEARCH1, SEARCH2, WRITE_MSG]
        out = research.handler({"action": "research", "case_id": cid, "run_id": run, "budget_usd": 3, "posting_text": "We want strong SQL skills and teamwork."}, None)
        meta = T.get_item(Key={"pk": f"CASE#{cid}", "sk": "META"})["Item"]
        rows = T.query(KeyConditionExpression="pk = :p", ExpressionAttributeValues={":p": f"CASE#{cid}"})["Items"]
        qs = {r["text"]: r for r in rows if r["sk"].startswith("Q#")}
        srcs = [r for r in rows if r["sk"].startswith("SRC#")]
        self.check("run done", out == {"ok": True} and meta["research_status"] == "done" and meta["researched_at"])
        exp = (20000*4 + 1000*20 + 30000*4 + 2000*20 + 8000*4 + 3000*20) / 1e6 + 7 * 0.01
        self.check(f"cost recorded {float(meta['cost_usd']):.4f} == {exp:.4f}", abs(float(meta["cost_usd"]) - exp) < 1e-4 and meta["searches"] == 7)
        spend = T.get_item(Key={"pk": "SPEND", "sk": research.datetime.now(research.timezone.utc).strftime("%Y-%m")})["Item"]
        self.check("month spend recorded", abs(float(spend["spent_usd"]) - exp) < 1e-4 and spend["runs"] == 1)
        self.check("pause_turn continued with assistant turn", len(FakeClient.calls) == 3 and FakeClient.calls[1]["messages"][-1]["role"] == "assistant")
        self.check("model and tool from config", FakeClient.calls[0]["model"] == "claude-opus-5-5" and FakeClient.calls[0]["tools"][0]["type"] == "web_search_20260318" and FakeClient.calls[0]["tools"][0]["max_uses"] == 25)
        self.check("no fetch tool without a posting link", len(FakeClient.calls[0]["tools"]) == 1)
        self.check("pasted posting sent to the model", "strong SQL skills" in FakeClient.calls[0]["messages"][0]["content"])
        self.check("reported with a real source kept", qs["Tell us about handling conflict."]["provenance"] == "reported" and qs["Tell us about handling conflict."]["source_ids"] == [1])
        self.check("reported with a made-up source becomes usual", qs["Have they asked about SQL?"]["provenance"] == "usual" and qs["Have they asked about SQL?"]["source_ids"] == [])
        self.check("posting requirement found in posting kept", qs["Walk us through a SQL query."]["provenance"] == "posting")
        self.check("posting requirement not in posting becomes usual", qs["Size a market."]["provenance"] == "usual" and qs["Size a market."]["requirement"] == "")
        self.check("own question not duplicated", sum(1 for t in qs if t == "Why Acme?") == 1 and qs["Why Acme?"]["provenance"] == "own")
        self.check("bad kind normalised", qs["Odd kind"]["kind"] == "behavioural")
        self.check("only cited sources stored", sorted(int(s["id"]) for s in srcs) == [1, 2] and all("cited_text" not in s for s in srcs))
        self.check("source has date, supports, no copied text", srcs[0]["date"] == "March 3, 2026" and srcs[0]["supports"] == "Reported questions")
        self.check("brief source ids filtered", meta["research_brief"]["format"][0]["source_ids"] == [] and meta["research_brief"]["values"][0]["source_ids"] == [2])
        self.check("competencies merged", meta["competencies"] == ["Teamwork", "Communication", "Client focus"])
        self.check("questions for them + topics stored", meta["questions_for_them"][0]["source_ids"] == [2] and meta["research_topics"] == ["Acme's latest results"])
        self.check("posting text never stored (only the short requirement phrase)", "We want strong SQL skills and teamwork" not in json.dumps([dict(r) for r in rows], default=str))

        out2 = research.handler({"action": "research", "case_id": cid, "run_id": run, "budget_usd": 3}, None)
        self.check("retried invocation skipped, nothing charged", out2 == {"skipped": True} and len(FakeClient.calls) == 3)

        # rerun replaces research questions and sources
        T.update_item(Key={"pk": f"CASE#{cid}", "sk": "META"}, UpdateExpression="SET research_status = :q, research_run = :r", ExpressionAttributeValues={":q": "queued", ":r": "c" * 32})
        w2 = dict(WRITE, questions=[WRITE["questions"][0]], sources=[{"id": 1, "supports": "Reported"}], values=[], questions_for_them=[])
        FakeClient.script = [SEARCH2, msg([{"type": "text", "text": json.dumps(w2)}], "end_turn", usage(100, 100))]
        research.handler({"action": "research", "case_id": cid, "run_id": "c" * 32, "budget_usd": 3}, None)
        rows = T.query(KeyConditionExpression="pk = :p", ExpressionAttributeValues={":p": f"CASE#{cid}"})["Items"]
        self.check("rerun replaced research rows, kept own", sorted(r["text"] for r in rows if r["sk"].startswith("Q#")) == ["Tell us about handling conflict.", "Why Acme?"])

        # failure path
        cid2, run2 = "d" * 12, "e" * 32
        setup(cid2, run2)
        FakeClient.script = [SEARCH1, AuthenticationError("bad key")]
        research.handler({"action": "research", "case_id": cid2, "run_id": run2, "budget_usd": 3}, None)
        m2 = T.get_item(Key={"pk": f"CASE#{cid2}", "sk": "META"})["Item"]
        self.check("failure recorded with plain message", m2["research_status"] == "failed" and "rejected" in m2["research_error"])
        self.check("partial cost still recorded", abs(float(m2["cost_usd"]) - ((20000*4 + 1000*20)/1e6 + 0.04)) < 1e-4)

        # budget stop: pause_turn but over 75% of budget -> stop searching, still write up
        cid3, run3 = "f" * 12, "1" * 32
        setup(cid3, run3)
        FakeClient.calls = []
        FakeClient.script = [SEARCH1, WRITE_MSG]
        research.handler({"action": "research", "case_id": cid3, "run_id": run3, "budget_usd": 0.1}, None)
        self.check("budget stops searching and still writes up", len(FakeClient.calls) == 2 and "output_config" in FakeClient.calls[1] and FakeClient.calls[1]["output_config"]["format"]["type"] == "json_schema")

        # posting link adds web fetch, fetched text validates posting requirement
        cid4, run4 = "2" * 12, "3" * 32
        setup(cid4, run4, posting_url="https://jobs.acme.example/1")
        FETCH = msg([{"type": "web_fetch_tool_result", "content": {"type": "web_fetch_result", "url": "https://jobs.acme.example/1", "content": {"type": "document", "source": {"type": "text", "data": "Requires strong SQL skills."}}}}], "end_turn", usage(1000, 100))
        FakeClient.calls = []
        FakeClient.script = [FETCH, WRITE_MSG]
        research.handler({"action": "research", "case_id": cid4, "run_id": run4, "budget_usd": 3}, None)
        rows = T.query(KeyConditionExpression="pk = :p", ExpressionAttributeValues={":p": f"CASE#{cid4}"})["Items"]
        q = [r for r in rows if r.get("text") == "Walk us through a SQL query."][0]
        self.check("fetch tool offered for a posting link", any(t["type"] == "web_fetch_20260318" for t in FakeClient.calls[0]["tools"]))
        self.check("fetched posting backs a posting question", q["provenance"] == "posting")
        self.check("fetched posting text not stored", "Requires strong SQL" not in json.dumps([dict(r) for r in rows], default=str))
        self.check("bad ids rejected", research.handler({"action": "research", "case_id": "x", "run_id": "y"}, None) == {"error": "bad request"})


if __name__ == "__main__":
    unittest.main()
