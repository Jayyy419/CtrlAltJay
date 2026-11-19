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

## Data

| Table | Holds | Backups |
|---|---|---|
| `ctrlaltjay-portfolio-items` | Projects, experience, settings, rate-limit and session rows | Created outside the stack |
| `ctrlaltjay-resume-items` | Resume entries | Created outside the stack |
| `ctrlaltjay-skills` | Skills | Created outside the stack |
| `ctrlaltjay-casebooks` | Casebooks, their questions and sources, and the monthly research spend | Point-in-time recovery; retained if removed from the stack |
| `ctrlaltjay-stories` | The private story bank | Point-in-time recovery; retained if removed from the stack |

## Monitoring and cost

- A $25 AWS billing alarm covers the whole account.
- Casebook research is the only part with a per-use cost (Claude API tokens and web searches). Each casebook shows what its runs cost, and the research panel shows the month's total.
- The caps are stack parameters: `CasebookMaxUsdPerCase` (default 3), `CasebookMaxUsdPerMonth` (default 10), `CasebookMaxSearches` (default 25) and `CasebookModel` (default `claude-opus-5-5`). Change one with a parameter override on deploy; no code change is needed.
- A run won't start once less than US$0.50 of the month's budget is left. Inside a run, searching stops once three quarters of its budget is spent and the rest goes to writing up, so a run can go slightly over its cap but not far. Months are calendar months in UTC.
- Token and search prices are environment variables on the research function (`CASEBOOK_PRICE_*`), set from Anthropic's pricing page as checked on 19 Nov 2026: Opus 5.5 at US$4 per million input tokens and US$20 per million output tokens, web search at US$10 per 1,000 searches. Update them if Anthropic's prices change, or the costs shown will drift from the bill.
- The cost shown is worked out from each response's token and search counts. It is an estimate of the bill, not read from Anthropic's billing (inferred, not verified against an invoice).
- Month-to-date spend is the `SPEND` / `YYYY-MM` row in `ctrlaltjay-casebooks`.
