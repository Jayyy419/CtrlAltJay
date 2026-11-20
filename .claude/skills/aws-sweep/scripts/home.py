# One home region in depth: the small recurring costs and the leftovers.
# Run with REGION = "ap-southeast-1", then "us-east-1", and with PART = "a"
# and PART = "b" for each (four runs). Read-only.
#   a: Lambda use, log groups, secrets, KMS keys, alarms, SNS
#   b: DynamoDB tables, ECR repos, schedules
# Per-item calls run in parallel: done one by one they pass run_script's
# 60-second limit.
import datetime as dt

REGION = "ap-southeast-1"
PART = "a"
now = dt.datetime.now(dt.timezone.utc)


def c(svc, op, **p):
    return call_boto3(service_name=svc, operation_name=op, region_name=REGION, params=p or None)


async def each(coros):
    return await asyncio.gather(*coros, return_exceptions=True)


def err(x):
    return str(x)[:120] if isinstance(x, Exception) else None


def age_days(t):
    if not t:
        return None
    if isinstance(t, (int, float)):
        t = dt.datetime.fromtimestamp(t / 1000 if t > 1e11 else t, dt.timezone.utc)
    if isinstance(t, str):
        t = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (now - t).days


out = {"region": REGION, "part": PART, "errors": {}}
fns = await c("lambda", "ListFunctions")
fn_names = [f["FunctionName"] for f in fns.get("Functions", [])]
fnset = set(fn_names)

if PART == "a":
    logs, secrets, keys, aliases, alarms, topics = await each([
        c("logs", "DescribeLogGroups"), c("secretsmanager", "ListSecrets"), c("kms", "ListKeys"), c("kms", "ListAliases"),
        c("cloudwatch", "DescribeAlarms"), c("sns", "ListTopics")])

    # Lambda: functions with no invocations in 30 days (one batched metrics call).
    idle = []
    if fn_names:
        q = [{"Id": f"f{i}", "MetricStat": {"Metric": {"Namespace": "AWS/Lambda", "MetricName": "Invocations",
              "Dimensions": [{"Name": "FunctionName", "Value": n}]}, "Period": 2592000, "Stat": "Sum"}, "ReturnData": True}
             for i, n in enumerate(fn_names[:500])]
        md = await c("cloudwatch", "GetMetricData", MetricDataQueries=q,
                     StartTime=(now - dt.timedelta(days=30)).isoformat(), EndTime=now.isoformat())
        calls = {r["Id"]: sum(r.get("Values", [])) for r in md.get("MetricDataResults", [])}
        idle = [n for i, n in enumerate(fn_names) if calls.get(f"f{i}", 0) == 0]
    out["lambda"] = {"total": len(fn_names), "no_invocations_30d": idle}

    # Log groups: kept forever, the biggest, and groups whose Lambda is gone.
    if not err(logs):
        lg = logs.get("logGroups", [])
        out["log_groups"] = {
            "total": len(lg),
            "stored_mb": round(sum(g.get("storedBytes", 0) for g in lg) / 1e6, 1),
            "no_retention": [{"name": g["logGroupName"], "mb": round(g.get("storedBytes", 0) / 1e6, 2)} for g in lg if not g.get("retentionInDays")],
            "lambda_gone": [g["logGroupName"] for g in lg if g["logGroupName"].startswith("/aws/lambda/")
                            and g["logGroupName"].split("/aws/lambda/", 1)[1] not in fnset],
            "largest_mb": sorted([(g["logGroupName"], round(g.get("storedBytes", 0) / 1e6, 1)) for g in lg], key=lambda x: -x[1])[:5],
        }

    # Secrets: $0.40 a month each. Flag ones nobody has read in 30 days.
    if not err(secrets):
        out["secrets"] = [{"name": s["Name"], "last_accessed_days": age_days(s.get("LastAccessedDate")),
                           "owned_by": s.get("OwningService"),
                           "Project": {t["Key"]: t["Value"] for t in s.get("Tags", [])}.get("Project")}
                          for s in secrets.get("SecretList", [])]

    # KMS: customer-managed keys are $1 a month each.
    if not err(keys) and not err(aliases):
        aws_keys = {a.get("TargetKeyId") for a in aliases.get("Aliases", []) if a["AliasName"].startswith("alias/aws/")}
        names = {}
        for a in aliases.get("Aliases", []):
            if a.get("TargetKeyId"):
                names.setdefault(a["TargetKeyId"], []).append(a["AliasName"])
        todo = [k["KeyId"] for k in keys.get("Keys", []) if k["KeyId"] not in aws_keys]
        ds = await each([c("kms", "DescribeKey", KeyId=k) for k in todo])
        out["kms_customer_keys"] = [
            {"id": k[:8], "state": d["KeyMetadata"]["KeyState"], "aliases": names.get(k, []),
             "created_days": age_days(d["KeyMetadata"].get("CreationDate")), "desc": (d["KeyMetadata"].get("Description") or "")[:60]}
            for k, d in zip(todo, ds) if not err(d) and d["KeyMetadata"].get("KeyManager") == "CUSTOMER"]

    # Alarms: 10 free, then $0.10 each. Long INSUFFICIENT_DATA often means the resource is gone.
    if not err(alarms):
        ma = alarms.get("MetricAlarms", [])
        out["alarms"] = {"total": len(ma) + len(alarms.get("CompositeAlarms", [])),
                         "insufficient_data": [{"name": a["AlarmName"], "since_days": age_days(a.get("StateUpdatedTimestamp")),
                                                "metric": f'{a.get("Namespace")}/{a.get("MetricName")}'}
                                               for a in ma if a["StateValue"] == "INSUFFICIENT_DATA"],
                         "in_alarm": [a["AlarmName"] for a in ma if a["StateValue"] == "ALARM"],
                         "no_actions": [a["AlarmName"] for a in ma if not a.get("AlarmActions")]}

    # SNS: topics nobody listens to, and subscriptions never confirmed.
    # Per topic: ListSubscriptions isn't auto-paginated by run_script and stops at one page.
    if not err(topics):
        ta = [t["TopicArn"] for t in topics.get("Topics", [])]
        subs = await each([c("sns", "ListSubscriptionsByTopic", TopicArn=a) for a in ta])
        sns = {"topics": len(ta), "no_confirmed_subscriber": [], "pending": [], "protocols": {}}
        for a, s in zip(ta, subs):
            n = a.split(":")[-1]
            if err(s):
                sns.setdefault("errors", {})[n] = err(s)
                continue
            sl = s.get("Subscriptions", [])
            if not any(x["SubscriptionArn"].startswith("arn:") for x in sl):
                sns["no_confirmed_subscriber"].append(n)
            if any(x["SubscriptionArn"] == "PendingConfirmation" for x in sl):
                sns["pending"].append(n)
            sns["protocols"][n] = sorted({x["Protocol"] for x in sl})
        out["sns"] = sns
    for k, v in {"logs": logs, "secrets": secrets, "kms": keys, "alarms": alarms, "sns": topics}.items():
        if err(v):
            out["errors"][k] = err(v)

else:
    tables, repos, rules, scheds = await each([
        c("dynamodb", "ListTables"), c("ecr", "DescribeRepositories"), c("events", "ListRules"), c("scheduler", "ListSchedules")])

    # DynamoDB: provisioned tables bill even when idle; empty tables may be leftovers.
    if not err(tables):
        names = tables.get("TableNames", [])
        ds = await each([c("dynamodb", "DescribeTable", TableName=t) for t in names[:60]])
        tl = [{"name": t, "mode": d["Table"].get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED"),
               "items": d["Table"].get("ItemCount"), "mb": round(d["Table"].get("TableSizeBytes", 0) / 1e6, 2),
               "rcu": d["Table"].get("ProvisionedThroughput", {}).get("ReadCapacityUnits"),
               "wcu": d["Table"].get("ProvisionedThroughput", {}).get("WriteCapacityUnits")}
              for t, d in zip(names, ds) if not err(d)]
        out["dynamodb"] = {"total": len(names), "provisioned": [t for t in tl if t["mode"] == "PROVISIONED"],
                           "empty": [t["name"] for t in tl if not t["items"]]}

    # ECR: image storage is $0.10/GB-month; repos without a lifecycle policy grow forever.
    if not err(repos):
        rn = [r["repositoryName"] for r in repos.get("repositories", [])]
        imgs = await each([c("ecr", "DescribeImages", repositoryName=n) for n in rn])
        pols = await each([c("ecr", "GetLifecyclePolicy", repositoryName=n) for n in rn])
        out["ecr"] = [{"name": n, "images": len(i.get("imageDetails", [])) if not err(i) else err(i),
                       "mb": round(sum(x.get("imageSizeInBytes", 0) for x in i.get("imageDetails", [])) / 1e6, 1) if not err(i) else None,
                       "untagged": sum(1 for x in i.get("imageDetails", []) if not x.get("imageTags")) if not err(i) else None,
                       "lifecycle_policy": not err(p)} for n, i, p in zip(rn, imgs, pols)]

    # Schedules: anything that wakes on a timer costs on every run.
    sched = []
    if not err(rules):
        sr = [r for r in rules.get("Rules", []) if r.get("ScheduleExpression")]
        ts = await each([c("events", "ListTargetsByRule", Rule=r["Name"]) for r in sr])
        for r, t in zip(sr, ts):
            sched.append({"rule": r["Name"], "every": r["ScheduleExpression"], "state": r["State"],
                          "targets": [x["Arn"] for x in (t.get("Targets", []) if not err(t) else [])]})
    if not err(scheds):
        ss = scheds.get("Schedules", [])
        gs = await each([c("scheduler", "GetSchedule", Name=s["Name"], GroupName=s.get("GroupName", "default")) for s in ss])
        for s, g in zip(ss, gs):
            if not err(g):
                sched.append({"schedule": s["Name"], "every": g.get("ScheduleExpression"), "state": g.get("State"),
                              "targets": [g.get("Target", {}).get("Arn", "")]})
    for s in sched:
        # A Lambda target is arn:aws:lambda:<region>:<acct>:function:<name>[:<alias>]. One in
        # another region shows as missing here; check it there before calling it orphaned.
        lam = [a.split(":function:", 1)[1].split(":")[0] for a in s["targets"] if ":lambda:" in a and ":function:" in a]
        s["target_missing"] = [n for n in lam if n not in fnset]
        s["targets"] = [a.split(":function:", 1)[1] if ":function:" in a else a.split(":")[-1] for a in s["targets"]]
    out["schedules"] = sched
    for k, v in {"dynamodb": tables, "ecr": repos, "events": rules, "scheduler": scheds}.items():
        if err(v):
            out["errors"][k] = err(v)

result = out
result
