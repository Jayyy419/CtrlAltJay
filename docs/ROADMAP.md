# Roadmap

## Done
- Moved from Elastic Beanstalk to Lambda, DynamoDB, S3 and CloudFront.
- Site on/off switch with a holding page, and an owner preview link.
- Owner sessions that expire and end on sign-out.
- Skill tree in the Stack panel.
- Casebook step 2: tables, owner-only API, research worker shell, key separation.
- Casebook step 3: the case form and casebook view, with a marked sample casebook.
- Casebook step 4: evidence matching and coverage, STAR outlines with gaps, the story bank.
- Casebook step 5: research with web search in the background, provenance checked in code, caps and cost.

## In progress: Casebook
6. Questions for them, the day-of sheet and PDF export.
7. Drill (flashcards and feedback), only once the owner says go.

## Next
- Optionally read PORTFOLIO.md, DECISIONS.md and CHANGELOG.md from listed repos through a read-only GitHub token, as more evidence for Casebook. Needs a token, so it waits for the owner.
- Skill tags on older portfolio items, so the skill tree shows every skill that has evidence.
- An automated test suite in the repo. Changes so far were checked with moto-backed scripts and Playwright outside the repo.

## Later
- A passkey as a second sign-in factor (set aside on 19 Nov 2026; see `DECISIONS.md`).
- Remove the unused guestbook endpoint (`/api/notes`) and its stored rows.
