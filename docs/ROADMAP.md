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
- Casebook step 6: questions for them you can edit and pick, the Day-of sheet (Boarding pass direction, picked from three) and Save as PDF.
- Claude spend reported to Upkeep (model and token counts only), switched on once the owner adds the URL and key.
- Casebook step 7: Drill, with Flashcards and an Interview room (the owner picked both of three directions), self-rating that orders the next round, and capped Claude feedback.

## In progress: Commit City and Source Map
1. ~~Read the codebase; confirm sign-in.~~ Done: an authenticator app code was added first.
2. ~~Town hall shell, tables, the GitHub token and the collector with Refresh now.~~ Done.
3. ~~Commit City with seeded, clearly marked sample data.~~ Done in the Night city direction (picked from three); live at `/city`, unlinked until step 4.
4. ~~Real stats, repo modes, approval and the public snapshot.~~ Done.
5. ~~Source Map with a sample tour.~~ Done in the Night districts direction (picked from three); live at `/map/sample`.
6. ~~Plotting tours in Town hall, the secret scan, publishing, stale checks.~~ Done in the Plot on the map direction (picked from three).
7. ~~Draft help from the Claude API.~~ Done: "Draft with Claude" on each stop, capped at US$1 a month.

## Next
- Optionally read PORTFOLIO.md, DECISIONS.md and CHANGELOG.md from listed repos as more evidence for Casebook, through the Town hall collector so the token stays with it.
- Skill tags on older portfolio items, so the skill tree shows every skill that has evidence.
- A fuller automated test suite. The repo has unit tests for Upkeep usage reporting only; other changes were checked with moto-backed scripts and Playwright outside the repo.

## Later
- A passkey as a second sign-in factor (set aside on 19 Nov 2026; see `DECISIONS.md`).
- Remove the unused guestbook endpoint (`/api/notes`) and its stored rows.
