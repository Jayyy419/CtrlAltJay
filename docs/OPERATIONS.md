# Operations

## Deploying

Merging to `main` runs **Deploy to Lambda**: a syntax check, `sam build --use-container`, `sam deploy`, an S3 sync of `static/` (uploads excluded) and a CloudFront invalidation. The `SiteEnabled` value already on the stack is carried forward.

**Rolling back:** revert the commit on `main`; the same workflow redeploys the previous code. CloudFormation also rolls a failed deploy back on its own.

## Switching the site on or off

Run **Site on/off** in GitHub Actions. Off attaches a CloudFront Function that serves a holding page for every request; the certificate stays valid. The workflow only passes once it sees the expected state from outside AWS.

## Seeing the site while it is off

Run **Owner preview link**. It mints a new secret (revoking the old link) and emails the link to the owner's verified inbox. The link is never printed, because the repository and its logs are public.

## Configuration

Environment variable names and what they do are in `.env.example`. Secrets are SSM Parameter Store SecureStrings under `/ctrlaltjay/`:

| Parameter | Read by |
|---|---|
| `/ctrlaltjay/flask-secret-key` | App |
| `/ctrlaltjay/admin-passcode` | App |
| `/ctrlaltjay/anthropic-api-key` | App (site chat) |
| `/ctrlaltjay/mail-password` | App (legacy SMTP fallback) |
| `/ctrlaltjay/casebook/anthropic-api-key` | Casebook research function only |
| `/ctrlaltjay/github-token` | Town hall collector only. A fine-grained GitHub token with read-only Contents and Metadata on the repos the owner picked. |
| `/ctrlaltjay/upkeep-usage-key` | App and Casebook research function. Optional: the usage key Upkeep issued for this site. |
| `/ctrlaltjay/admin-totp-secret` | App (read, written and deleted from the sign-in security page). Delete it to turn the code step off if the authenticator and every recovery code are lost. |

## Data

| Table | Holds | Backups |
|---|---|---|
| `ctrlaltjay-portfolio-items` | Projects, experience, settings, rate-limit and session rows | Created outside the stack |
| `ctrlaltjay-resume-items` | Resume entries | Created outside the stack |
| `ctrlaltjay-skills` | Skills | Created outside the stack |
| `ctrlaltjay-casebooks` | Casebooks, their questions and sources, and the monthly research spend | Point-in-time recovery; retained if removed from the stack |
| `ctrlaltjay-stories` | The private story bank | Point-in-time recovery; retained if removed from the stack |
| `ctrlaltjay-town` | Town hall: every repo the token can see, dated stats snapshots, collector runs, tour drafts and the approvals log | Point-in-time recovery; retained if removed from the stack |
| `ctrlaltjay-public-city` | Only what the owner has published for Commit City and Source Map. The only Town hall table public pages read | Point-in-time recovery; retained if removed from the stack |

## Town hall collector

- `ctrlaltjay-town-collector` runs daily at 9:00 am Singapore time (EventBridge Scheduler, `ctrlaltjay-town-collector-daily`) and when the owner presses Refresh now in Town hall.
- It reads the GitHub token from `/ctrlaltjay/github-token`. To replace the token, overwrite that parameter; the next run uses the new one. Repos the new token can't see stay in Town hall, marked "Token can't see it", so their settings aren't lost.
- A run's outcome (done, rate limited, failed) and its GitHub call count are kept as `RUN` rows in `ctrlaltjay-town` and shown in Town hall. Runs make roughly four GitHub calls per repo, well inside GitHub's hourly limit for a personal token (inferred from GitHub's documented limits, not measured on a large account).
- The same function answers two synchronous calls from the app while the owner plots a tour: the file list and one file's lines. Each daily run also checks plotted tours and marks stops whose lines changed as "Needs a look"; the run's `needs_look` count says how many were newly marked. A failure in that check is recorded on the run (`stale_check`) without failing the stats.
- The schedule can't carry tags (EventBridge Scheduler schedules don't support them); everything else the stack creates is tagged `Project=CtrlAltJay`.

## Monitoring and cost

- A $25 AWS billing alarm covers the whole account.
- Casebook research, Drill feedback and Town hall draft help are the parts with a per-use cost (Claude API tokens, plus web searches for research). Each casebook shows what its runs cost, and the research panel shows the month's total.
- Drill feedback is capped by `CasebookDrillMaxUsdPerMonth` (default 1, 0 turns it off) on `CasebookDrillModel` (default `claude-opus-5-5`); the month's spend is `SPEND`/`DRILL#<YYYY-MM>` in `ctrlaltjay-casebooks` and shows under the button. A feedback request should cost about a cent (estimated from typical token counts, not measured).
- Draft help is capped by `TownDraftMaxUsdPerMonth` (default 1, 0 turns it off) and runs on `TownDraftModel` (default `claude-opus-5-5`). The month's spend is the `SPEND`/`DRAFT#<YYYY-MM>` row in `ctrlaltjay-town` and shows under the button. A draft should cost about a cent (estimated from typical token counts, not yet measured).
- The caps are stack parameters: `CasebookMaxUsdPerCase` (default 3), `CasebookMaxUsdPerMonth` (default 10), `CasebookMaxSearches` (default 25) and `CasebookModel` (default `claude-opus-5-5`). Change one with a parameter override on deploy; no code change is needed.
- A run won't start once less than US$0.50 of the month's budget is left. Inside a run, searching stops once three quarters of its budget is spent and the rest goes to writing up, so a run can go slightly over its cap but not far. Months are calendar months in UTC.
- Token and search prices are environment variables on the research function (`CASEBOOK_PRICE_*`), set from Anthropic's pricing page as checked on 19 Nov 2026: Opus 5.5 at US$4 per million input tokens and US$20 per million output tokens, web search at US$10 per 1,000 searches. Update them if Anthropic's prices change, or the costs shown will drift from the bill.
- The cost shown is worked out from each response's token and search counts. It is an estimate of the bill, not read from Anthropic's billing (inferred, not verified against an invoice).
- Month-to-date spend is the `SPEND` / `YYYY-MM` row in `ctrlaltjay-casebooks`.

## Claude spend in Upkeep

Every Claude response's model name and token counts can be reported to Upkeep, which prices them and shows the month's spend for this site next to the owner's other projects. It's off until both of these are in place:

1. Cut a usage key for CtrlAltJay in Upkeep and store it as a SecureString at `/ctrlaltjay/upkeep-usage-key` (the `UpkeepUsageKeySsmParam` stack parameter) in ap-southeast-1. Both functions' roles can already read that name.
2. Set the `UpkeepUsageUrl` stack parameter to Upkeep's origin, with no trailing slash: change its default in `template.yaml`, or add `UpkeepUsageUrl=...` to the `--parameter-overrides` in the deploy workflow. Then deploy.

The key is read once per Lambda container, so a new or replaced key is picked up at the next cold start; redeploying forces one. To turn reporting off, set `UpkeepUsageUrl` back to empty and deploy, or delete the parameter. A report that fails logs one line with the error type and HTTP status (never the key) and is not retried; the app's own work carries on either way. Searches made by research aren't token counts, so Upkeep doesn't see them; the casebook's own cost figure still includes them.
