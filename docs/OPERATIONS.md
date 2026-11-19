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
| `ctrlaltjay-casebooks` | Casebooks and their questions, sources and evidence | Point-in-time recovery; retained if removed from the stack |
| `ctrlaltjay-stories` | The private story bank | Point-in-time recovery; retained if removed from the stack |

## Monitoring and cost

- A $25 AWS billing alarm covers the whole account.
- Casebook research is the only part with a per-use cost (Claude API tokens and web searches). It is capped per casebook and per month by configuration, and each casebook shows what it cost.
