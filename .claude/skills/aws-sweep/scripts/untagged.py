# Never-tagged resources: the tagging API (tags.py) can't see these, so list
# resources service by service and compare with what carries a Project tag.
# Covers the services that bill or matter for cost attribution. Read-only.
# About 12 calls, 10 services (run_script allows no more than 10 services per run).
# Cognito is left out: user pools cost nothing at this usage.
HOME = "ap-southeast-1"
UE = "us-east-1"


def c(svc, op, region=HOME, **p):
    return call_boto3(service_name=svc, operation_name=op, region_name=region, params=p or None)


def err(x):
    return str(x)[:120] if isinstance(x, Exception) else None


tagged_home, tagged_ue, fns, tables, buckets, zones, dists, apps, apis, clusters, dsql = await asyncio.gather(
    c("resourcegroupstaggingapi", "GetResources", TagFilters=[{"Key": "Project"}]),
    c("resourcegroupstaggingapi", "GetResources", UE, TagFilters=[{"Key": "Project"}]),
    c("lambda", "ListFunctions"), c("dynamodb", "ListTables"), c("s3", "ListBuckets", UE),
    c("route53", "ListHostedZones", UE), c("cloudfront", "ListDistributions", UE), c("amplify", "ListApps"),
    c("apigatewayv2", "GetApis"), c("rds", "DescribeDBClusters"),
    c("dsql", "ListClusters"),
    return_exceptions=True,
)
# The account ID comes from any ARN, which saves an STS call (and a service).
acct = next(m["ResourceARN"].split(":")[4] for m in tagged_home.get("ResourceTagMappingList", []) if m["ResourceARN"].split(":")[4])
have = set()
for t in (tagged_home, tagged_ue):
    if not err(t):
        have |= {m["ResourceARN"] for m in t.get("ResourceTagMappingList", [])}

found = {}
if not err(fns):
    found["lambda"] = [f["FunctionArn"] for f in fns.get("Functions", [])]
if not err(tables):
    found["dynamodb"] = [f"arn:aws:dynamodb:{HOME}:{acct}:table/{t}" for t in tables.get("TableNames", [])]
if not err(buckets):
    found["s3"] = [f"arn:aws:s3:::{b['Name']}" for b in buckets.get("Buckets", [])]
if not err(zones):
    found["route53_zone"] = [f"arn:aws:route53:::hostedzone/{z['Id'].split('/')[-1]}" for z in zones.get("HostedZones", [])]
if not err(dists):
    found["cloudfront"] = [d["ARN"] for d in dists.get("DistributionList", {}).get("Items", [])]
if not err(apps):
    found["amplify"] = [a["appArn"] for a in apps.get("apps", [])]
if not err(apis):
    found["http_api"] = [f"arn:aws:apigateway:{HOME}::/apis/{a['ApiId']}" for a in apis.get("Items", [])]
if not err(clusters):
    found["rds_cluster"] = [x["DBClusterArn"] for x in clusters.get("DBClusters", [])]
if not err(dsql):
    found["dsql"] = [x["arn"] for x in dsql.get("clusters", [])]

# Names help match a resource to its project.
names = {}
if not err(zones):
    names.update({f"arn:aws:route53:::hostedzone/{z['Id'].split('/')[-1]}": z["Name"] for z in zones.get("HostedZones", [])})
if not err(dists):
    names.update({d["ARN"]: ",".join(d.get("Aliases", {}).get("Items", [])) or d.get("Origins", {}).get("Items", [{}])[0].get("DomainName", "")
                  for d in dists.get("DistributionList", {}).get("Items", [])})

missing = {k: [names.get(a, a.split(":")[-1].split("/")[-1]) + ("" if a not in names else f" ({a.split('/')[-1]})") for a in v if a not in have]
           for k, v in found.items()}
result = {"checked": {k: len(v) for k, v in found.items()},
          "no_Project_tag": {k: v for k, v in missing.items() if v},
          "errors": {k: err(v) for k, v in {"lambda": fns, "dynamodb": tables, "s3": buckets, "route53": zones, "cloudfront": dists,
                                             "amplify": apps, "apigatewayv2": apis, "rds": clusters, "dsql": dsql}.items() if err(v)}}
result
