# Costs: month to date, last month, trend, forecast, anomalies, cost tags, budgets.
# Run as the `code` of the AWS MCP run_script tool. Read-only.
# Cost Explorer bills $0.01 per request; this makes about 11 of them.
# About 4 calls per budget on top, so with more than about 20 budgets split the
# budget part into its own run (run_script stops at 100 calls).
import datetime as dt

today = dt.date.today()
mstart = today.replace(day=1)
prev_end = mstart
prev_start = (mstart - dt.timedelta(days=1)).replace(day=1)
q_start = (prev_start - dt.timedelta(days=1)).replace(day=1)
q_start = (q_start - dt.timedelta(days=1)).replace(day=1)  # three months back
next_month = (mstart + dt.timedelta(days=32)).replace(day=1)
iso = lambda d: d.isoformat()
UE = "us-east-1"


def mask(e):
    if not e or "@" not in e:
        return e
    u, d = e.split("@", 1)
    return u[:2] + "***@" + d


async def ce(op, **p):
    return await call_boto3(service_name="ce", operation_name=op, region_name=UE, params=p)


def by_group(resp, floor=0.01):
    out = {}
    for period in resp.get("ResultsByTime", []):
        for g in period.get("Groups", []):
            k = g["Keys"][0]
            out[k] = out.get(k, 0) + float(g["Metrics"]["UnblendedCost"]["Amount"])
    return {k: round(v, 2) for k, v in sorted(out.items(), key=lambda x: -x[1]) if v >= floor}


acct = (await call_boto3(service_name="sts", operation_name="GetCallerIdentity", region_name=UE))["Account"]
mtd_end = today if today > mstart else today + dt.timedelta(days=1)
M = ["UnblendedCost"]

mtd_svc, prev_svc, months, daily, mtd_proj, mtd_env, mtd_region, mtd_usage = await asyncio.gather(
    ce("GetCostAndUsage", TimePeriod={"Start": iso(mstart), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(prev_start), "End": iso(prev_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(q_start), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(today - dt.timedelta(days=14)), "End": iso(today)}, Granularity="DAILY", Metrics=M),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(mstart), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "TAG", "Key": "Project"}]),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(mstart), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "TAG", "Key": "Environment"}]),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(mstart), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "DIMENSION", "Key": "REGION"}]),
    ce("GetCostAndUsage", TimePeriod={"Start": iso(mstart), "End": iso(mtd_end)}, Granularity="MONTHLY", Metrics=M,
       GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}]),
)

# Spikes: each service's latest full day against its average over the 7 days before.
d8 = await ce("GetCostAndUsage", TimePeriod={"Start": iso(today - dt.timedelta(days=8)), "End": iso(today)}, Granularity="DAILY",
              Metrics=M, GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "REGION"}])
days = d8["ResultsByTime"]
spikes = []
if len(days) >= 2:
    last = days[-1]
    base = {}
    for d in days[:-1]:
        for g in d.get("Groups", []):
            k = " / ".join(g["Keys"])
            base[k] = base.get(k, 0) + float(g["Metrics"]["UnblendedCost"]["Amount"]) / (len(days) - 1)
    for g in last.get("Groups", []):
        k = " / ".join(g["Keys"])
        v = float(g["Metrics"]["UnblendedCost"]["Amount"])
        b = base.get(k, 0)
        if v - b >= 0.10 and v >= 2 * b:
            spikes.append({"day": last["TimePeriod"]["Start"], "service_region": k, "cost": round(v, 2), "avg_7d": round(b, 2)})

try:
    # With MONTHLY granularity this comes back as the whole month, actuals included
    # (inferred: it matched the account budget's own forecast within a dollar).
    fc = await ce("GetCostForecast", TimePeriod={"Start": iso(today), "End": iso(next_month)}, Metric="UNBLENDED_COST", Granularity="MONTHLY")
    forecast_rest = round(float(fc["Total"]["Amount"]), 2)
except Exception as e:  # no forecast on the last day of a month or with too little history
    forecast_rest = f"unavailable: {str(e)[:80]}"

try:
    an = await ce("GetAnomalies", DateInterval={"StartDate": iso(today - dt.timedelta(days=30)), "EndDate": iso(today)})
    anomalies = [{"start": a.get("AnomalyStartDate"), "end": a.get("AnomalyEndDate"),
                  "impact": round(float(a.get("Impact", {}).get("TotalImpact", 0)), 2),
                  "causes": [{k: c.get(k) for k in ("Service", "Region", "UsageType", "LinkedAccount") if c.get(k)} for c in a.get("RootCauses", [])][:3],
                  "feedback": a.get("Feedback")} for a in an.get("Anomalies", [])]
    monitors = len((await ce("GetAnomalyMonitors")).get("AnomalyMonitors", []))
except Exception as e:
    anomalies, monitors = f"error: {str(e)[:100]}", None

tags = await ce("ListCostAllocationTags", Type="UserDefined")
cost_tags = {t["TagKey"]: t["Status"] for t in tags.get("CostAllocationTags", [])}

bud = await call_boto3(service_name="budgets", operation_name="DescribeBudgets", region_name=UE, params={"AccountId": acct})


async def budget_alerts(name):
    # Per budget and per alert in parallel: one by one they pass the 60-second limit.
    n = await call_boto3(service_name="budgets", operation_name="DescribeNotificationsForBudget", region_name=UE,
                         params={"AccountId": acct, "BudgetName": name})
    notes = n.get("Notifications", [])
    subs = await asyncio.gather(*[call_boto3(service_name="budgets", operation_name="DescribeSubscribersForNotification",
                                             region_name=UE, params={"AccountId": acct, "BudgetName": name, "Notification": x})
                                  for x in notes])
    return [f'{x["NotificationType"]} {x["ComparisonOperator"]} {x["Threshold"]}{"%" if x.get("ThresholdType", "PERCENTAGE") == "PERCENTAGE" else ""}'
            f' -> {[mask(y["Address"]) if y["SubscriptionType"] == "EMAIL" else y["Address"].split(":")[-1] for y in s.get("Subscribers", [])]}'
            for x, s in zip(notes, subs)]


bl = bud.get("Budgets", [])
alerts = await asyncio.gather(*[budget_alerts(b["BudgetName"]) for b in bl], return_exceptions=True)
budgets = []
for b, notes in zip(bl, alerts):
    cs = b.get("CalculatedSpend", {})
    budgets.append({
        "name": b["BudgetName"], "limit": b["BudgetLimit"]["Amount"] if b.get("BudgetLimit") else None,
        "actual": round(float(cs.get("ActualSpend", {}).get("Amount", 0)), 2),
        "forecast": round(float(cs.get("ForecastedSpend", {}).get("Amount", 0)), 2) if cs.get("ForecastedSpend") else None,
        "filters": b.get("CostFilters", {}) or (b.get("FilterExpression") and "FilterExpression") or "NONE (whole account)",
        "notifications": notes if not isinstance(notes, Exception) else f"error: {str(notes)[:80]}",
    })

result = {
    "account": acct,
    "today": iso(today),
    "mtd_total": round(sum(by_group(mtd_svc, 0).values()), 2),
    "forecast_month": forecast_rest,
    "months": {p["TimePeriod"]["Start"][:7]: round(float(p["Total"]["UnblendedCost"]["Amount"]), 2) for p in months["ResultsByTime"]},
    "daily_last_14": {p["TimePeriod"]["Start"][5:]: round(float(p["Total"]["UnblendedCost"]["Amount"]), 2) for p in daily["ResultsByTime"]},
    "mtd_by_service": by_group(mtd_svc),
    "last_month_by_service": by_group(prev_svc),
    "mtd_by_project": by_group(mtd_proj, 0),
    "mtd_by_environment": by_group(mtd_env, 0),
    "mtd_by_region": by_group(mtd_region),
    "mtd_top_usage_types": dict(list(by_group(mtd_usage, 0.05).items())[:20]),
    "spikes_last_day": spikes,
    "anomalies_30d": anomalies,
    "anomaly_monitors": monitors,
    "cost_allocation_tags": cost_tags,
    "budgets": budgets,
}
result
