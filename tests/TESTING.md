# Testing

Everything below was run on 26 Oct 2026, on macOS with Python 3.12.8 and Google Chrome installed.

## 1. Smoke tests
```sh
python3 -m unittest discover -s tests -v
```
Result: **15 tests, all OK.** They cover:
- name extraction from bold text, list items and plain sentences, and that platforms (Google, Instagram) and sentence starts are not counted as names
- "and" no longer glues two names together (a real bug the tests caught)
- whole-word, case-insensitive matching of her name and aliases
- scoring on the sample: 3 of 10 questions named her, ChatGPT 1/10, Perplexity 3/10, 7 lost questions, Kilnhouse Retreats sent to instead on 9 questions
- the receipt HTML shows `recommended 3/11` with an extra question, 3 NAMED lines and 8 NOT NAMED lines, and escapes `<script>` in a question
- the fix list has exactly three sections, lists the lost questions and has no em dashes
- the command line writes receipt.html, receipt-card.html, fix-list.md and summary.json
- the sample PNG is 1080x1350
- API mode: parsing OpenAI and Perplexity reply shapes (fake replies, no network), and a clean exit with no keys set

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

## 3. Security gate
```sh
./scripts/security-check.sh
```
Result: 9 passed, 0 failed, **SAFE TO PUBLISH**.

## Not tested
- **Browser mode** against live ChatGPT and Perplexity. It needs the Claude in Chrome extension and a logged-in account,
  and it was not run against a real account for this build.
- **API mode** against the live APIs. No keys were used. The request shapes follow the OpenAI Responses API and the
  Perplexity chat completions API; the reply parsing is tested with fake replies only.
- **Claude Cowork** upload of the zip, and whether the Cowork sandbox has Chrome for the PNG. Without Chrome the tool
  prints a clear message and still writes the HTML receipt and fix list (that branch is code-reviewed, not run).
- Windows.
