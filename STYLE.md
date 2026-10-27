# style.json

One file holds your look. Every Rocha Coded tool reads the same file, so you make it once.

## Where it goes
The tool looks in this order and uses the first one it finds:
1. `style.json` in the folder you are working in (your Cowork folder, or wherever you run Claude Code)
2. `~/.rocha-coded/style.json`, to use one look across every project
3. `examples/style.rocha-coded.json`, the bundled example (Rocha's look)

Start from `style.example.json`: copy it to `style.json` and fill it in. Or ask Claude to make one with you.

## The keys
| Key | What to put there | Used by this tool |
|---|---|---|
| `name` | your brand or studio name | no |
| `owner` | your name, as you sign things | yes, printed at the foot of the receipt |
| `handle` | your Instagram or main social handle, with the @ | yes, next to your name |
| `site` | your website address | no |
| `palette.hero` | your ground colour, the deep one everything sits on, as a hex code like `#50163C` | the page behind the receipt (never a fill) |
| `palette.wine` | a second deep colour for headlines | the AI RECEIPT title, numbers, labels, the total and THANK YOU! |
| `palette.accent` | your one bright accent | the NAMED pills |
| `palette.paper` | a light paper colour | the info boxes |
| `palette.paper_pink` | the receipt paper itself | yes |
| `palette.ink` | your text colour | the receipt text, rules and NOT NAMED outlines |
| `palette.marker` | the colour of the handwritten scrawl | yes |
| `palette.plum` | a deep shade | kept for other tools |
| `palette.gold` | a highlight colour for thin rules | the rule under the title |
| `palette.cool` | one cool accent, used rarely | no |
| `fonts.masthead` | a big display font from Google Fonts | the AI RECEIPT title, the total and THANK YOU! |
| `fonts.label` | a font for labels and small print | the labels, pills and your name line |
| `fonts.body` | a reading font | no (the receipt prints in mono) |
| `fonts.scrawl` | a handwriting or marker font | the scrawl |
| `fonts.script` | a signature script font | no |
| `fonts.mono` | a typewriter font | the numbers and question lines |
| `motif` | one of `guest-check`, `front-page`, `magazine-scrawl`, `pink-paper`, `sticker-collage`, `rotary`, `leopard`, `retro-tv`, `neutral` | no, this tool is always a guest check |
| `lines.scrawl` | a short line in your own words | the handwritten line under the total |
| `lines.masthead`, `headline`, `todo`, `stamp`, `celebrate`, `affirm`, `invite`, `magazine` | more of your own lines | kept for other tools |
| `references` | 3 to 5 images or links that feel like you | Claude looks at these when it makes your style with you |
| `notes` | your look in one or two sentences | Claude reads this too |

## Good to know
- Colours must be hex codes (`#RRGGBB`). Anything else is skipped and the bundled colour is used for that slot.
- Fonts are Google Fonts names, letters, numbers and spaces only. If a font is not on Google Fonts, or you are offline, the receipt uses a similar font already on your computer.
- Any colour or font you leave empty borrows the bundled example's, so the receipt always looks finished.
- Your words and your name never borrow. Leave `lines.scrawl`, `owner` or `handle` empty and the receipt prints nothing there.
