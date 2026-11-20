# Every enabled region: anything that runs or bills on its own, wherever it hides.
# EC2 instances, EBS volumes, Elastic IPs, NAT gateways, CloudFormation stacks,
# Lambda functions, RDS/Aurora clusters and instances. Only regions with
# something in them are reported. Read-only. About 8 calls per region (about
# 140 for 17 regions), so it is split into two halves: set HALF = 0, run, then
# set HALF = 1 and run again.
HALF = 0
HOME = {"ap-southeast-1", "us-east-1"}  # covered in depth by home.py

all_regions = sorted(r["RegionName"] for r in (await call_boto3(service_name="ec2", operation_name="DescribeRegions",
                                                                region_name="us-east-1"))["Regions"])
regions = all_regions[HALF::2]
LIVE = ["CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE", "ROLLBACK_COMPLETE", "CREATE_FAILED",
        "DELETE_FAILED", "UPDATE_ROLLBACK_FAILED", "ROLLBACK_FAILED", "IMPORT_COMPLETE", "IMPORT_ROLLBACK_COMPLETE",
        "CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS", "DELETE_IN_PROGRESS", "REVIEW_IN_PROGRESS"]


def tagmap(tags):
    return {t["Key"]: t["Value"] for t in tags or []}


async def one(region):
    c = lambda svc, op, **p: call_boto3(service_name=svc, operation_name=op, region_name=region, params=p or None)
    inst, vols, eips, nats, stacks, fns, dbc, dbi = await asyncio.gather(
        c("ec2", "DescribeInstances"),
        c("ec2", "DescribeVolumes"),
        c("ec2", "DescribeAddresses"),
        c("ec2", "DescribeNatGateways", Filter=[{"Name": "state", "Values": ["available", "pending"]}]),
        c("cloudformation", "ListStacks", StackStatusFilter=LIVE),
        c("lambda", "ListFunctions"),
        c("rds", "DescribeDBClusters"),
        c("rds", "DescribeDBInstances"),
        return_exceptions=True,
    )
    out = {}
    if isinstance(inst, Exception):
        return region, {"error": str(inst)[:120]}
    i = [{"id": x["InstanceId"], "type": x["InstanceType"], "state": x["State"]["Name"], "Project": tagmap(x.get("Tags")).get("Project")}
         for r in inst.get("Reservations", []) for x in r["Instances"] if x["State"]["Name"] != "terminated"]
    if i: out["instances"] = i
    v = [{"id": x["VolumeId"], "gb": x["Size"], "type": x["VolumeType"], "state": x["State"],
          "attached": bool(x.get("Attachments")), "Project": tagmap(x.get("Tags")).get("Project")} for x in vols.get("Volumes", [])]
    if v: out["volumes"] = v
    e = [{"ip": "masked", "alloc": x.get("AllocationId"), "attached": bool(x.get("AssociationId")),
          "Project": tagmap(x.get("Tags")).get("Project")} for x in eips.get("Addresses", [])]
    if e: out["elastic_ips"] = e
    if not isinstance(nats, Exception) and nats.get("NatGateways"):
        out["nat_gateways"] = [{"id": x["NatGatewayId"], "Project": tagmap(x.get("Tags")).get("Project")} for x in nats["NatGateways"]]
    home = region in HOME
    if not isinstance(stacks, Exception):
        s = [{"name": x["StackName"], "status": x["StackStatus"], "updated": str(x.get("LastUpdatedTime") or x.get("CreationTime"))[:10]}
             for x in stacks.get("StackSummaries", []) if not x.get("ParentId")]
        # In the home regions only stacks stuck in a failed or rollback state are news.
        bad = [x for x in s if not x["status"].endswith("_COMPLETE") or "ROLLBACK" in x["status"]]
        if home:
            out["stacks_total"] = len(s)
            if bad: out["stacks_needing_attention"] = bad
        elif s:
            out["stacks"] = s
    else:
        out["stacks_error"] = str(stacks)[:120]
    if not isinstance(fns, Exception) and fns.get("Functions"):
        if home:
            out["lambda_total"] = len(fns["Functions"])
        else:
            out["lambda"] = [{"name": x["FunctionName"], "runtime": x.get("Runtime"), "modified": x["LastModified"][:10]} for x in fns["Functions"]]
    # Databases bill by the hour, so outside the home regions any cluster or instance is news.
    if not home:
        if isinstance(dbc, Exception) or isinstance(dbi, Exception):
            out["rds_error"] = str(dbc if isinstance(dbc, Exception) else dbi)[:120]
        else:
            db = [{"cluster": x["DBClusterIdentifier"], "engine": x.get("Engine"), "status": x.get("Status"),
                   "created": str(x.get("ClusterCreateTime"))[:10], "Project": tagmap(x.get("TagList")).get("Project")}
                  for x in dbc.get("DBClusters", [])]
            db += [{"instance": x["DBInstanceIdentifier"], "class": x.get("DBInstanceClass"), "status": x.get("DBInstanceStatus"),
                    "Project": tagmap(x.get("TagList")).get("Project")}
                   for x in dbi.get("DBInstances", []) if not x.get("DBClusterIdentifier")]
            if db: out["databases"] = db
    return region, out


res = await asyncio.gather(*[one(r) for r in regions], return_exceptions=True)
result = {"half": HALF, "checked": regions,
          "found": {r: o for r, o in [x for x in res if not isinstance(x, Exception)] if o},
          "errors": [str(x)[:120] for x in res if isinstance(x, Exception)]}
result
