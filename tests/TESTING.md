# Testing

Everything below was run on 26 Oct 2026, on macOS with Python 3.12.8 and Google Chrome installed.

## 1. Smoke tests
```sh
python3 -m unittest discover -s tests -v
```
Result: **29 tests, all OK.** They cover:
- the three motifs from one function: analog (receipt header), cyberpunk (the `rocheverse:~$` prompt, block cursor, block bars 1/10 and 3/10, Silkscreen loaded), y2k-blog (`ai-receipt.exe` window, mood line, hit counter `000,777`, guestbook link); the same data in all three; every share card carries exactly one box to fit; motif choice from `--motif`, then style.json, then analog, with old names mapped; no glow or drop shadow on type in any stylesheet; the CLI `--motif` flag
- style.json: a second palette, fonts, scrawl and owner/handle replace the bundled look; a blank scrawl prints none; bad colour and font values are not injected into the page; the fallback order (./style.json, then ~/.rocha-coded/style.json, then the bundled example); both bundled style files share the same keys; a user style borrows only missing palette and font entries, never the example's lines, owner, handle, name, references or notes
- name extraction from bold text, list items and plain sentences, and that platforms (Google, Instagram) and sentence starts are not counted as names
- "and" no longer glues two names together (a real bug the tests caught)
- whole-word, case-insensitive matching of her name and aliases
- scoring on the sample: 3 of 10 questions named her, ChatGPT 1/10, Perplexity 3/10, 7 lost questions, Kilnhouse Retreats sent to instead on 9 questions
- the receipt HTML shows `recommended 3/11` with an extra question, 3 NAMED lines and 8 NOT NAMED lines, and escapes `<script>` in a question
- the fix list has exactly three sections, lists the lost questions and has no em dashes
- the command line writes receipt.html, receipt-card.html, fix-list.md and summary.json
- the sample PNG is 1080x1350
- API mode: parsing OpenAI and Perplexity reply shapes (fake replies, no network), and a clean exit with no keys set or with a key but no model set

## 2. Sample receipt, end to end
```sh
python3 recommend.py examples/answers.sample.json --out out
```
Output:
```
Recommended 3 out of 10.
Receipt: out/receipt.html
Fix list: out/fix-list.md
Share card: out/receipt.png (1080x1350)
```
The PNG was opened and checked by eye: fonts loaded, all ten lines, the total, the red scrawl and THANK YOU! are visible.
The page receipt was also rendered at 390px wide (inside an iframe, since headless Chrome on macOS will not size a
window under 500px): no sideways scroll, lines stack, NAMED tags wrap under each question.

## 2b. The v2 look (27 Oct)
The sample was re-rendered in the current house look: plum ground, blush paper, Fraunces 900 wine masthead,
candy NAMED pills, ink-outlined NOT NAMED pills, Permanent Marker magenta scrawl, DM Mono lines, Bricolage Grotesque
labels, no glow and no coloured shadow. Checked by eye at 1080x1350.

## 3. A second style, by eye
A test style (teal and navy, Bodoni Moda, Oswald, IBM Plex Mono, Caveat, its own scrawl) was rendered with
`--style`. All colours, fonts, the scrawl and the credit line changed. Its taller fonts first pushed the credit line
off the card, so the card now shrinks the question list until everything fits. Re-rendered: it fits at 1080x1350.

## 3b. Three motifs, by eye (27 Oct)
`python3 scripts/make-readme-images.py` rendered all three share cards at 1080x1350 and the triptych at 1620x720.
Each was opened and checked: nothing cut off, no glow. Fixes made on the way: the cyberpunk total bar picked up the
big serif style, cyberpunk lines were stuck at 14px, and the y2k card had a gap mid-receipt. All three page versions
were also rendered side by side at 390px wide: page width stayed 390 in each, so no sideways scroll.

## 4. Security gate
```sh
./scripts/security-check.sh
```
Result: 9 passed, 0 failed, **SAFE TO PUBLISH**.

## 5. The five free fixes (28 Oct 2026, Python 3.12.8, macOS, Chrome installed)
```sh
python3 -m unittest discover -s tests -v
```
Result: **57 tests: 56 OK, 1 skipped.** The skipped one is the egeo integration test. It runs only when
egeo is importable and on the PATH, and egeo was not installed here. Every other test runs only our own code.
The 28 new tests in `tests/test_solutions.py` cover:
- to_gaps: one row per buyer question with only `query`, `cited` and `sources` (the generic gaps shape egeo's
  CLI docs describe); `cited` matches the receipt; `sources` are the links from answers that missed her; a clean
  error with no name
- entity page: the JSON-LD block parses, holds Organization, Service and FAQPage in one graph, links the service to
  her, and switches to Person when she trades under her own name; the direct answer comes before everything else;
  `</script>` in her text cannot close the block; a `javascript:` site is dropped; the page is signed with her name,
  not Rocha's; a missing name is a kind error and exit code 2
- three motifs for the entity page (sheet, `rocheverse:~$` prompt, hit counter 000,777), one JSON-LD block in each,
  no glow in `page.css`
- answers: one file per lost question with a FAQPage block that parses, her own written answer used word for word,
  the rest marked DRAFT, duplicate slugs kept apart, lost questions read from summary.json or scored from answers.json
- mentions: places with no link or no source are dropped, duplicates dropped, capped at ten; no web search gives a
  checklist and the Podcast Outreach Engine hand-off; every pitch is three lines starting with her name
- llms.txt: exactly one H1, a blockquote, H2 sections About, Answers, Optional, every list item `[name](url): notes`,
  one answer link per lost question; works with no site (links start with `/`); the crawler note lists the robots
- compare: "last month 1/10, today 3/10" for runs 30 days apart, a dated line otherwise, which questions moved,
  the line printed on the receipt in all three motifs, `delta.json` and `out/history/summary-<date>.json` written,
  a previous answers.json works too, and a broken previous file still produces today's receipt
- inheritance: a user style borrows missing palette entries and never Rocha's owner or handle; no em dashes in any output

By hand: the full chain (`recommend.py --compare`, `entity_page.py`, `answers.py`, `mentions.py`, `llms.py`,
`to_gaps.py`) was run on the fictional sample into a scratch folder. The entity page was rendered to PNG in all three
motifs and checked by eye; that caught the lead line and proof repeating in "In short", now fixed.
`python3 scripts/make-readme-images.py` rendered the new fixes panel at 1080x1350 and it was checked by eye; the first
two tries left a third of the card empty and then overflowed, and the card CSS was tuned until it fit.

## Not tested
- **egeo** (`egeo optimize` and `egeo fix-gaps`). It is optional and was not installed. The command lines follow
  egeo's published CLI docs (egeoagents.com/docs/cli). `fix-gaps` also needs her own `project.yaml`, which we do not write.
- **Fix 3 with live web search.** The agent does the searching; the script only cleans and formats what it is given.
- **JSON-LD in a validator.** The blocks parse as JSON and use schema.org types, but were not run through Google's
  Rich Results Test or the schema.org validator.
- **Publishing the entity page, answers or llms.txt** on a real site, Substack or GitHub Pages.
- **Browser mode** against live ChatGPT and Perplexity. It needs the Claude in Chrome extension and a logged-in account,
  and it was not run against a real account for this build.
- **API mode** against the live APIs. No keys were used. The request shapes follow the OpenAI Responses API and the
  Perplexity chat completions API; the reply parsing is tested with fake replies only.
- **Claude Cowork** upload of the zip, and whether the Cowork sandbox has Chrome for the PNG. Without Chrome the tool
  prints a clear message and still writes the HTML receipt and fix list (that branch is code-reviewed, not run).
- Windows.
