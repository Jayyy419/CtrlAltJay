# CtrlAltJay

The personal portfolio at [ctrlaltjay.dev](https://ctrlaltjay.dev): projects, experience, resume and skills, presented as a code editor. Visitors browse it; the owner edits everything from an admin panel on the same site, and keeps a private Casebook for interview and application prep.

## Who uses it

- **Visitors** (recruiters, collaborators): browse projects, experience, the resume and the skill tree, chat with an assistant that answers from the portfolio, and use the contact form.
- **The owner**: signs in with a passcode and an authenticator app code to edit content, publish drafts, switch the site on or off, use Casebook, and run Town hall (Commit City and Source Map, in progress).

## Run it locally

Needs Python 3.11 and AWS credentials that can reach the DynamoDB tables (or a local mock).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in SECRET_KEY and an admin passcode at minimum
flask --app app run     # http://127.0.0.1:5000
```

There is no test suite in the repo yet; changes have been checked with moto-backed scripts and Playwright (see `docs/ROADMAP.md`).

## Deploy

Pushing to `main` deploys through GitHub Actions (`.github/workflows/deploy-lambda.yml`): `sam build`, `sam deploy`, a static-asset sync to S3 and a CloudFront invalidation. The site's on/off state is carried forward, so a routine deploy never switches it back on. Details in `docs/OPERATIONS.md`.

## Docs

- [Architecture](docs/ARCHITECTURE.md): how the pieces connect
- [Stack](docs/STACK.md): what it is built with, and why
- [Operations](docs/OPERATIONS.md): deploys, on/off, preview links, costs
- [Roadmap](docs/ROADMAP.md): done, in progress, next
- [Decisions](docs/DECISIONS.md): significant choices and what was set aside
- [Changelog](docs/CHANGELOG.md)
- [Security](SECURITY.md): the owner-only area
- [Usage](docs/USAGE.md): the admin panel
- [Portfolio entry](PORTFOLIO.md)
