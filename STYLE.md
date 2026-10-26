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
| `palette.hero` | your loudest colour, as a hex code like `#FF2D8A` | the masthead, totals and NAMED tags |
| `palette.accent` | a softer partner to the hero | the dividers in the info boxes |
| `palette.paper` | the background the receipt sits on | yes |
| `palette.paper_pink` | the receipt paper itself | yes |
| `palette.ink` | your text colour | yes |
| `palette.marker` | the colour of the handwritten scrawl | yes |
| `palette.plum` | a deep shade for small print | yes |
| `palette.gold` | a highlight colour | kept for other tools |
| `palette.cool` | one cool accent, used rarely | no |
| `fonts.masthead` | a big display font from Google Fonts | the AI RECEIPT title and THANK YOU! |
| `fonts.label` | a narrow font for labels | the small caps labels |
| `fonts.body` | a reading font | no (the receipt prints in mono) |
| `fonts.scrawl` | a handwriting or marker font | the scrawl |
| `fonts.mono` | a typewriter font | the receipt lines |
| `motif` | one of `guest-check`, `front-page`, `magazine-scrawl`, `pink-paper`, `sticker-collage`, `rotary`, `leopard`, `retro-tv`, `neutral` | no, this tool is always a guest check |
| `lines.scrawl` | a short line in your own words | the handwritten line under the total |
| `lines.masthead`, `headline`, `todo`, `stamp`, `celebrate`, `affirm` | more of your own lines | kept for other tools |
| `references` | 3 to 5 images or links that feel like you | Claude looks at these when it makes your style with you |
| `notes` | your look in one or two sentences | Claude reads this too |

## Good to know
- Colours must be hex codes (`#RRGGBB`). Anything else is skipped and the bundled colour is used for that slot.
- Fonts are Google Fonts names, letters, numbers and spaces only. If a font is not on Google Fonts, or you are offline, the receipt uses a similar font already on your computer.
- Leave `lines.scrawl` empty and the receipt prints no scrawl. Your receipt never borrows someone else's words.
