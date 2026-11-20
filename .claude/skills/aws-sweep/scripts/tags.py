# Tags: every resource the tagging API knows about, in every enabled region,
# checked against the project registry. Read-only. About 20 API calls.
#
# The tagging API only lists resources that carry, or once carried, a tag.
# Resources that were never tagged show up in inventory.py instead.
#
# Keep EXPECTED in step with the registry table in SKILL.md.
EXPECTED = {
    "CtrlAltJay": "Production",
    "Sentrix": "Production",
    "SeadsSingapore": "Production",
    "NTUHall7": "Production",
    "Recallibur": "Development",
    "MindWeave": "Development",
    "Tiraameowsu": "Development",
    "Misu": "Development",
    "Pinwheel": "Development",
    "Upkeep": "Development",
    "Fairfare": "Development",
    "Shelfmark": "Development",
    "Capital": "Development",
    "Curio": "Development",
    "Haystack": "Development",
    "Shared": "Shared",
    "VPC-Default": "Shared",
}
# Keys that look like Project/Environment but aren't the cost-tracked ones.
LEGACY = {"project", "app", "Env", "env", "environment", "Stage", "stage"}
# Resources that can't be tagged, or whose tags don't matter for cost.
SKIP = (":backup:", ":cloudformation:", ":ssm:", ":logs:")

regions = [r["RegionName"] for r in (await call_boto3(service_name="ec2", operation_name="DescribeRegions",
                                                      region_name="us-east-1"))["Regions"]]


async def scan(region):
    # No ResourcesPerPage: setting it stops run_script's auto-pagination after one page.
    r = await call_boto3(service_name="resourcegroupstaggingapi", operation_name="GetResources", region_name=region)
    return region, r.get("ResourceTagMappingList", [])


res = await asyncio.gather(*[scan(r) for r in regions], return_exceptions=True)
errors = {regions[i]: str(x)[:120] for i, x in enumerate(res) if isinstance(x, Exception)}
counts, by_project = {}, {}
no_tags, no_project, no_env, unknown_project, wrong_env, legacy = [], [], [], [], [], []
for item in res:
    if isinstance(item, Exception):
        continue
    region, mappings = item
    for m in mappings:
        arn = m["ResourceARN"]
        tags = {t["Key"]: t["Value"] for t in m.get("Tags", [])}
        if any(s in arn for s in SKIP):
            continue
        counts[region] = counts.get(region, 0) + 1
        p, e = tags.get("Project"), tags.get("Environment")
        by_project.setdefault(p or "(none)", {}).setdefault(e or "(none)", 0)
        by_project[p or "(none)"][e or "(none)"] += 1
        if not tags:
            no_tags.append(arn)
            continue
        if not p:
            no_project.append({"arn": arn, "tags": tags})
        elif p not in EXPECTED:
            unknown_project.append({"arn": arn, "Project": p, "Environment": e})
        if not e:
            no_env.append({"arn": arn, "Project": p})
        elif p in EXPECTED and e != EXPECTED[p]:
            wrong_env.append({"arn": arn, "Project": p, "Environment": e, "expected": EXPECTED[p]})
        lk = sorted(LEGACY & tags.keys())
        if lk:
            legacy.append({"arn": arn, "Project": p, "legacy": {k: tags[k] for k in lk}})

result = {
    "regions_with_resources": counts,
    "by_project_env": by_project,
    "untagged_but_listed": no_tags,
    "missing_Project": no_project,
    "missing_Environment": no_env,
    "unknown_Project": unknown_project,
    "Environment_not_expected": wrong_env,
    "legacy_keys": legacy[:40],
    "legacy_count": len(legacy),
    "errors": errors,
}
result
