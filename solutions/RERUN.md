# Run it again in 30 days

The fixes take a few weeks to reach the assistants. Thirty days later, ask the same ten questions again
and watch the total move.

Every time you build a receipt, the tool keeps a dated copy of the numbers in `out/history/`.
So the first run leaves a file like `out/history/summary-2026-09-28.json`. You do not need to do anything to keep it.

## In Claude Code or Cowork
Say this to Claude, in your own words if you like:
```
It has been a month. Run my AI receipt again with the same questions and compare it to last time.
```
Claude reuses `out/questions.json`, asks the assistants again, and builds the new receipt with the compare.

## By hand
This builds today's receipt and compares it to the run you name:
```sh
python3 recommend.py out/answers.json --out out/ --compare out/history/summary-2026-09-28.json
```
You will see a line like:
```
Recommended 5 out of 10.
Last month 3/10, today 5/10.
  now named: best pottery retreat in Port Halcyon
```
The same line is printed on the receipt under SINCE LAST TIME, and the details land in `out/delta.json`.
If the runs are not about a month apart, the line names the date instead ("on 2026-10-20 3/10, today 5/10").

## Keep it honest
- Use the same ten questions. A new question makes the numbers incomparable.
- Use the same modes if you can. Browser answers and API answers differ.
- AI answers change from day to day. One run is a snapshot. Two runs a month apart show a direction.
