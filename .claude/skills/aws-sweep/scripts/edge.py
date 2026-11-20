# Account-wide and edge services: DNS and health checks, CloudFront, certificates,
# S3, Amplify, API Gateway, WAF, GuardDuty and IAM sign-in hygiene.
# Read-only, apart from asking IAM to build a credential report (no side effects).
# About 35 calls.
import base64
import csv
import datetime as dt
import io

HOME = "ap-southeast-1"
UE = "us-east-1"
now = dt.datetime.now(dt.timezone.utc)


def c(svc, op, region=HOME, **p):
    return call_boto3(service_name=svc, operation_name=op, region_name=region, params=p or None)


async def each(coros):
    return await asyncio.gather(*coros, return_exceptions=True)


def err(x):
    return str(x)[:120] if isinstance(x, Exception) else None


out = {"errors": {}}
zones, hcs, dists, certs_ue, certs_home, buckets, apps, apis, acl_reg, acl_cf, gd = await each([
    c("route53", "ListHostedZones", UE), c("route53", "ListHealthChecks", UE), c("cloudfront", "ListDistributions", UE),
    c("acm", "ListCertificates", UE), c("acm", "ListCertificates", HOME), c("s3", "ListBuckets", UE),
    c("amplify", "ListApps"), c("apigatewayv2", "GetApis"),
    c("wafv2", "ListWebACLs", Scope="REGIONAL"), c("wafv2", "ListWebACLs", UE, Scope="CLOUDFRONT"),
    c("guardduty", "ListDetectors"),
])

# Route 53: $0.50 a zone; health checks $0.50 each plus $1 per optional feature
# (HTTPS, string matching, 10-second interval, latency graphs).
if not err(zones):
    out["hosted_zones"] = [{"name": z["Name"], "records": z.get("ResourceRecordSetCount"), "private": z["Config"].get("PrivateZone")}
                           for z in zones.get("HostedZones", [])]
if not err(hcs):
    hl = []
    for h in hcs.get("HealthChecks", []):
        cfg = h["HealthCheckConfig"]
        extras = [n for n, on in [("https", cfg.get("Type", "").startswith("HTTPS")),
                                  ("string_match", "STR_MATCH" in cfg.get("Type", "")),
                                  ("fast_10s", cfg.get("RequestInterval") == 10),
                                  ("latency_graphs", cfg.get("MeasureLatency"))] if on]
        hl.append({"id": h["Id"][:8], "target": cfg.get("FullyQualifiedDomainName") or cfg.get("Type"),
                   "type": cfg.get("Type"), "interval": cfg.get("RequestInterval"), "regions": len(cfg.get("Regions", [])) or "default",
                   "paid_extras": extras, "approx_month": round(0.5 + 1.0 * len(extras), 2)})
    out["health_checks"] = hl

# CloudFront: disabled distributions are clutter; note price class and WAF.
if not err(dists):
    out["cloudfront"] = [{"id": d["Id"], "aliases": d.get("Aliases", {}).get("Items", []), "enabled": d["Enabled"],
                          "price_class": d.get("PriceClass"), "waf": bool(d.get("WebACLId"))}
                         for d in dists.get("DistributionList", {}).get("Items", [])]

# ACM: certificates nothing uses, and ones that won't renew.
for label, r in (("us-east-1", certs_ue), (HOME, certs_home)):
    if not err(r):
        out.setdefault("certificates", {})[label] = [
            {"domain": x["DomainName"], "status": x.get("Status"), "in_use": x.get("InUse"), "renewal": x.get("RenewalEligibility")}
            for x in r.get("CertificateSummaryList", []) if not x.get("InUse") or x.get("Status") != "ISSUED"]

# S3: sizes from CloudWatch's daily storage metric, per bucket region.
if not err(buckets):
    bl = buckets.get("Buckets", [])
    by_region = {}
    for b in bl:
        by_region.setdefault(b.get("BucketRegion") or HOME, []).append(b["Name"])
    sizes = {}
    for reg, names in by_region.items():
        q = []
        for i, n in enumerate(names):
            q.append({"Id": f"s{i}", "MetricStat": {"Metric": {"Namespace": "AWS/S3", "MetricName": "BucketSizeBytes",
                      "Dimensions": [{"Name": "BucketName", "Value": n}, {"Name": "StorageType", "Value": "StandardStorage"}]},
                      "Period": 86400, "Stat": "Average"}})
            q.append({"Id": f"n{i}", "MetricStat": {"Metric": {"Namespace": "AWS/S3", "MetricName": "NumberOfObjects",
                      "Dimensions": [{"Name": "BucketName", "Value": n}, {"Name": "StorageType", "Value": "AllStorageTypes"}]},
                      "Period": 86400, "Stat": "Average"}})
        md = await c("cloudwatch", "GetMetricData", reg, MetricDataQueries=q[:500],
                     StartTime=(now - dt.timedelta(days=3)).isoformat(), EndTime=now.isoformat())
        vals = {r["Id"]: (r.get("Values") or [0])[0] for r in md.get("MetricDataResults", [])}
        for i, n in enumerate(names):
            sizes[n] = {"region": reg, "mb": round(vals.get(f"s{i}", 0) / 1e6, 1), "objects": int(vals.get(f"n{i}", 0))}
    out["s3"] = {"total": len(bl), "total_mb": round(sum(v["mb"] for v in sizes.values()), 1),
                 "largest": sorted(sizes.items(), key=lambda x: -x[1]["mb"])[:6],
                 "empty": [n for n, v in sizes.items() if v["objects"] == 0]}

# Amplify: builds cost per minute; stale apps and branches keep building on pushes.
if not err(apps):
    al = apps.get("apps", [])
    brs = await each([c("amplify", "ListBranches", appId=a["appId"]) for a in al])
    out["amplify"] = [{"app": a["name"], "id": a["appId"], "updated": str(a.get("updateTime"))[:10],
                       "branches": [{"name": b["branchName"], "auto_build": b.get("enableAutoBuild"), "stage": b.get("stage"),
                                     "updated": str(b.get("updateTime"))[:10]} for b in (br.get("branches", []) if not err(br) else [])]}
                      for a, br in zip(al, brs)]

if not err(apis):
    out["http_apis"] = [{"name": a["Name"], "id": a["ApiId"], "created": str(a.get("CreatedDate"))[:10]} for a in apis.get("Items", [])]

# WAF: the web ACL is about $5 a month plus $1 a rule. Keep it; just show what it guards.
acls = []
for scope, r, reg in (("REGIONAL", acl_reg, HOME), ("CLOUDFRONT", acl_cf, UE)):
    if not err(r):
        for a in r.get("WebACLs", []):
            if scope == "CLOUDFRONT":
                # CloudFront ACLs are attached from the distribution side.
                ds = dists.get("DistributionList", {}).get("Items", []) if not err(dists) else []
                prot = [d["Id"] for d in ds if d.get("WebACLId") == a["ARN"]]
            else:
                # ListResourcesForWebACL defaults to load balancers only, so ask for each type.
                types = ["APPLICATION_LOAD_BALANCER", "API_GATEWAY", "APPSYNC", "COGNITO_USER_POOL", "APP_RUNNER_SERVICE", "VERIFIED_ACCESS_INSTANCE"]
                rs = await each([c("wafv2", "ListResourcesForWebACL", reg, WebACLArn=a["ARN"], ResourceType=t) for t in types])
                prot = [f"{t}: {x.split(':')[-1][:60]}" for t, x2 in zip(types, rs) if not err(x2) for x in x2.get("ResourceArns", [])]
            acls.append({"name": a["Name"], "scope": scope, "protects": prot,
                         "note": "attached to nothing: paying for no protection" if not prot else ""})
out["waf"] = acls

if not err(gd):
    out["guardduty_detectors"] = len(gd.get("DetectorIds", []))

# IAM: users, keys and MFA from the credential report (two calls, no per-user loop).
try:
    await c("iam", "GenerateCredentialReport", UE)
    rep = await c("iam", "GetCredentialReport", UE)
    body = rep["Content"]
    if isinstance(body, (bytes, bytearray)):
        body = body.decode()
    elif not body.startswith("user,"):
        body = base64.b64decode(body).decode()
    rows = list(csv.DictReader(io.StringIO(body)))
    out["iam_users"] = [{"user": r["user"], "mfa": r["mfa_active"], "password_last_used": r["password_last_used"][:10],
                         "key1": (r["access_key_1_active"], r["access_key_1_last_used_date"][:10]),
                         "key2": (r["access_key_2_active"], r["access_key_2_last_used_date"][:10])} for r in rows]
except Exception as e:
    out["iam_users"] = f"credential report not ready yet, run again in a minute: {str(e)[:80]}"

for k, v in {"route53": zones, "health_checks": hcs, "cloudfront": dists, "acm": certs_ue, "s3": buckets, "amplify": apps,
             "apigatewayv2": apis, "waf": acl_reg, "guardduty": gd}.items():
    if err(v):
        out["errors"][k] = err(v)
result = out
result
