# Roadmap

## Done
- Moved from Elastic Beanstalk to Lambda, DynamoDB, S3 and CloudFront.
- Site on/off switch with a holding page, and an owner preview link.
- Owner sessions that expire and end on sign-out.
- Skill tree in the Stack panel.
- Casebook step 2: tables, owner-only API, research worker shell, key separation.
- Casebook step 3: the case form and casebook view, with a marked sample casebook.

## In progress: Casebook
4. Evidence mapping from existing portfolio data, coverage view, STAR outlines with visible gaps, story bank.
5. Research with web search as a background job, with provenance labels, sources, caps and cost.
6. Questions for them, the day-of sheet and PDF export.
7. Drill (flashcards and feedback), only once the owner says go.

## Next
- Skill tags on older portfolio items, so the skill tree shows every skill that has evidence.
- An automated test suite in the repo. Changes so far were checked with moto-backed scripts and Playwright outside the repo.

## Later
- A passkey as a second sign-in factor (set aside on 19 Nov 2026; see `DECISIONS.md`).
- Remove the unused guestbook endpoint (`/api/notes`) and its stored rows.
