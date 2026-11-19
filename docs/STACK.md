# Stack

Versions are from `requirements.txt` and `template.yaml` at the time of writing.

| Piece | What | Why |
|---|---|---|
| Language | Python 3.14 | The newest generally available Lambda Python runtime, on Amazon Linux 2023. Moved from 3.11 (Amazon Linux 2) so Pillow 13 installs from a wheel. |
| Web framework | Flask 3.1 | The app started as a Flask site and still is one. |
| Lambda adapter | apig-wsgi 2.20 | Runs the Flask app behind a Lambda function URL without rewriting it. |
| QR codes | segno 1.6 | Draws the authenticator setup QR code as SVG on the server, with no other dependencies. |
| Data | DynamoDB, on-demand | No server to run; a personal site's traffic costs almost nothing. |
| Static files and uploads | S3 behind CloudFront | Images and fonts never cost a Lambda invocation. |
| Edge | CloudFront, plus one CloudFront Function and a KeyValueStore | HTTPS on the custom domain, and the off-switch holding page with its owner preview link. |
| Infrastructure as code | AWS SAM (CloudFormation) | One template for the app, tables, edge and research worker. |
| Email | Amazon SES | Contact form delivery without an SMTP password. |
| Scheduling | EventBridge Scheduler | Runs the Town hall collector daily in Singapore time without a server. |
| GitHub data | GitHub REST API, version 2022-11-28, through Python's standard library | Repo stats for Commit City; no extra dependency for a handful of calls. |
| AI | Claude API (`anthropic` 0.119) | The site chat, Casebook research, Drill feedback and Town hall draft help. Model IDs are read from configuration. |
| Front end | Vanilla JavaScript, custom CSS, Tailwind (CDN) | No build step. |
| Fonts | IBM Plex Sans and Mono, self-hosted | Matches the code-editor look without a font request to a third party. |
| CI/CD | GitHub Actions with OIDC into AWS | No long-lived AWS keys in GitHub. |
