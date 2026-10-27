"""Smoke tests. Run from the repo root: python3 -m unittest discover -s tests -v"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ask_api  # noqa: E402
import recommend  # noqa: E402

SAMPLE = ROOT / "examples" / "answers.sample.json"


class TestExtraction(unittest.TestCase):
    def test_list_items_and_bold(self):
        text = ("Here are a few options:\n\n1. **Kilnhouse Retreats** - weekend retreats.\n"
                "2. **The Clay Hours** - evening classes.\n- Saltmarsh Studio: phone-free sessions\n")
        self.assertEqual(recommend.extract_entities(text),
                         ["Kilnhouse Retreats", "The Clay Hours", "Saltmarsh Studio"])

    def test_capitalised_phrases_in_prose(self):
        text = "I could not find much. Compare with Kilnhouse Retreats or The Clay Hours in Port Halcyon."
        found = recommend.extract_entities(text, ignore=["Port Halcyon"])
        self.assertIn("Kilnhouse Retreats", found)
        self.assertIn("The Clay Hours", found)
        self.assertNotIn("Port Halcyon", found)
        self.assertNotIn("Clay Hours", found)

    def test_platforms_and_sentence_starts_are_not_names(self):
        text = "Here are some ideas. Check Google Reviews and Instagram first. Best of luck."
        self.assertEqual(recommend.extract_entities(text), [])

    def test_name_match_is_whole_word_and_case_insensitive(self):
        self.assertTrue(recommend.name_matches("Hush Hour Studio", [], "try hush hour studio.", []))
        self.assertTrue(recommend.name_matches("Hush Hour Studio", ["Hush Hour"], "Hush Hour is lovely", []))
        self.assertFalse(recommend.name_matches("Hush", [], "Hushabye Pottery", []))


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.meta, self.answers = recommend.load_answers(SAMPLE)
        self.result = recommend.score(self.answers, "Hush Hour Studio", ["Hush Hour"], ["Port Halcyon"])

    def test_sample_totals(self):
        self.assertEqual(self.result["total"], 10)
        self.assertEqual(self.result["named"], 3)
        self.assertEqual(self.result["sources"]["ChatGPT"], {"asked": 10, "named": 1})
        self.assertEqual(self.result["sources"]["Perplexity"], {"asked": 10, "named": 3})
        self.assertEqual(len(self.result["lost"]), 7)

    def test_sent_instead_ranking(self):
        top = self.result["sent_instead"]
        self.assertEqual(top[0], {"name": "Kilnhouse Retreats", "questions": 9})
        names = [t["name"] for t in top]
        self.assertNotIn("Hush Hour Studio", names)
        self.assertNotIn("Clay Hours", names)

    def test_agent_named_list_and_flag_win(self):
        answers = [{"question": "q1", "source": "Claude", "answer": "Try the studio by the pier.",
                    "named": ["Pier Clay Co"], "you_named": True}]
        r = recommend.score(answers, "Hush Hour Studio", [], [])
        self.assertEqual(r["named"], 1)
        self.assertEqual(r["questions"][0]["named"], ["Pier Clay Co"])

    def test_plain_list_format_loads(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            p.write_text(json.dumps(self.answers[:2]))
            meta, answers = recommend.load_answers(p)
            self.assertEqual(meta, {})
            self.assertEqual(len(answers), 2)


class TestRender(unittest.TestCase):
    def test_html_counts_and_escaping(self):
        meta, answers = recommend.load_answers(SAMPLE)
        answers = answers + [{"question": "<script>alert(1)</script> best?", "source": "Claude",
                              "answer": "Kilnhouse Retreats"}]
        r = recommend.score(answers, "Hush Hour Studio", [], ["Port Halcyon"])
        page = recommend.render_receipt(r, meta, "Hush Hour Studio")
        self.assertIn("AI RECEIPT", page)
        self.assertIn("THANK YOU!", page)
        self.assertIn("build your founder world", page)
        self.assertIn("recommended <b>3/11</b>", page)
        self.assertEqual(len(re.findall(r'class="line hit"', page)), 3)
        self.assertEqual(len(re.findall(r'class="line"', page)), 8)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_fix_list_names_lost_questions(self):
        meta, answers = recommend.load_answers(SAMPLE)
        r = recommend.score(answers, "Hush Hour Studio", [], ["Port Halcyon"])
        md = recommend.render_fix_list(r, meta, "Hush Hour Studio")
        self.assertIn("3 out of 10", md)
        self.assertIn("moonlit pottery class", md)
        self.assertEqual(len(re.findall(r"^## \d\.", md, re.M)), 3)
        self.assertNotIn("\u2014", md)  # no em dashes

    def test_cli_writes_files(self):
        with tempfile.TemporaryDirectory() as d:
            code = recommend.main([str(SAMPLE), "--out", d, "--no-png"])
            self.assertEqual(code, 0)
            for f in ("receipt.html", "receipt-card.html", "fix-list.md", "summary.json"):
                self.assertTrue((Path(d) / f).exists(), f)
            s = json.loads((Path(d) / "summary.json").read_text())
            self.assertEqual((s["named"], s["total"]), (3, 10))

    def test_png_reader(self):
        png = ROOT / "examples" / "receipt.sample.png"
        if png.exists():
            self.assertEqual(recommend.png_size(png), (1080, 1350))


class TestApiParsing(unittest.TestCase):
    def test_openai_output_shapes(self):
        self.assertEqual(ask_api.openai_text({"output_text": " hi "}), "hi")
        data = {"output": [{"type": "web_search_call"},
                           {"type": "message", "content": [{"type": "output_text", "text": "A"}]}]}
        self.assertEqual(ask_api.openai_text(data), "A")

    def test_perplexity_with_citations(self):
        data = {"choices": [{"message": {"content": "Try Kilnhouse."}}], "citations": ["https://x.example"]}
        out = ask_api.pplx_text(data)
        self.assertTrue(out.startswith("Try Kilnhouse."))
        self.assertIn("- https://x.example", out)

    def test_key_without_model_exits_cleanly(self):
        import os
        names = ("OPENAI_API_KEY", "PERPLEXITY_API_KEY", "OPENAI_MODEL", "PERPLEXITY_MODEL")
        saved = {k: os.environ.pop(k) for k in names if k in os.environ}
        os.environ["OPENAI_API_KEY"] = "placeholder-for-test"
        try:
            with tempfile.TemporaryDirectory() as d:
                q = Path(d) / "q.json"
                q.write_text(json.dumps({"questions": ["best pottery"]}))
                code = ask_api.main([str(q), "--out", str(Path(d) / "a.json"), "--env", str(Path(d) / "none")])
                self.assertEqual(code, 3)
                self.assertFalse((Path(d) / "a.json").exists())
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.update(saved)

    def test_no_keys_exits_cleanly(self):
        import os
        saved = {k: os.environ.pop(k) for k in ("OPENAI_API_KEY", "PERPLEXITY_API_KEY") if k in os.environ}
        try:
            with tempfile.TemporaryDirectory() as d:
                q = Path(d) / "q.json"
                q.write_text(json.dumps({"questions": ["best pottery"]}))
                code = ask_api.main([str(q), "--out", str(Path(d) / "a.json"), "--env", str(Path(d) / "none")])
                self.assertEqual(code, 3)
        finally:
            os.environ.update(saved)


class TestStyle(unittest.TestCase):
    def setUp(self):
        meta, answers = recommend.load_answers(SAMPLE)
        self.meta = meta
        self.result = recommend.score(answers, "Hush Hour Studio", [], ["Port Halcyon"])

    def test_second_palette_changes_colours_and_scrawl(self):
        rocha = recommend.render_receipt(self.result, self.meta, "Hush Hour Studio")
        other = {"owner": "Wren", "handle": "@wrenmakes",
                 "palette": {"hero": "#0A2F35", "wine": "#0A7E8C", "paper_pink": "#E8F4F1", "marker": "#1B3A6B"},
                 "fonts": {"masthead": "Bodoni Moda"}, "lines": {"scrawl": "slow hands, full kilns"}}
        page = recommend.render_receipt(self.result, self.meta, "Hush Hour Studio", style=other)
        override = lambda html: html.split("<style>:root {")[-1].split("</style>")[0]
        self.assertIn("--ground: #50163C;", override(rocha))
        self.assertIn("--wine: #682047;", override(rocha))
        self.assertIn("build your founder world", rocha)
        self.assertIn("--ground: #0A2F35;", override(page))
        self.assertIn("--wine: #0A7E8C;", override(page))
        self.assertIn("--paper: #E8F4F1;", override(page))
        self.assertIn("--marker: #1B3A6B;", override(page))
        self.assertNotIn("#50163C", override(page))
        self.assertNotIn("#682047", override(page))
        self.assertIn('--serif: "Bodoni Moda"', page)
        self.assertIn("family=Bodoni+Moda", page)
        self.assertIn("slow hands, full kilns", page)
        self.assertNotIn("build your founder world", page)
        self.assertIn("Wren · @wrenmakes · made with Rocha Coded", page)

    def test_blank_scrawl_prints_no_scrawl(self):
        page = recommend.render_receipt(self.result, self.meta, "X", style={"lines": {"scrawl": ""}})
        self.assertNotIn('class="scrawl"', page)

    def test_bad_values_are_not_injected(self):
        bad = {"palette": {"hero": "red;}body{display:none"}, "fonts": {"masthead": 'X";}</style>'}}
        page = recommend.render_receipt(self.result, self.meta, "X", style=bad)
        self.assertNotIn("display:none", page)
        self.assertNotIn('X";}', page)

    def test_fallback_order(self):
        with tempfile.TemporaryDirectory() as d:
            cwd, home = Path(d) / "work", Path(d) / "home"
            (home / ".rocha-coded").mkdir(parents=True)
            cwd.mkdir()
            self.assertEqual(recommend.find_style(cwd=cwd, home=home), recommend.STYLE_EXAMPLE)
            (home / ".rocha-coded" / "style.json").write_text("{}")
            self.assertEqual(recommend.find_style(cwd=cwd, home=home), home / ".rocha-coded" / "style.json")
            (cwd / "style.json").write_text("{}")
            self.assertEqual(recommend.find_style(cwd=cwd, home=home), cwd / "style.json")

    def test_user_style_inherits_only_palette_and_fonts(self):
        rocha = json.loads(recommend.STYLE_EXAMPLE.read_text())
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "style.json"
            p.write_text(json.dumps({"palette": {"hero": "#0A7E8C"}, "fonts": {"masthead": ""}, "lines": {}}))
            style = recommend.load_style(p)
        self.assertEqual(style["palette"]["hero"], "#0A7E8C")
        self.assertEqual(style["palette"]["marker"], rocha["palette"]["marker"])
        self.assertEqual(style["fonts"]["masthead"], rocha["fonts"]["masthead"])
        for key in ("owner", "handle", "name", "references", "notes"):
            self.assertFalse(style.get(key), key)
        self.assertEqual(style["lines"], {})
        page = recommend.render_receipt(self.result, self.meta, "X", style=style)
        for hers in [rocha["lines"]["scrawl"], rocha["handle"], rocha["owner"] + " ·"]:
            self.assertNotIn(hers, page)
        self.assertIn('<div class="credit">made with Rocha Coded</div>', page)

    def test_bundled_examples_share_keys(self):
        rocha = json.loads(recommend.STYLE_EXAMPLE.read_text())
        blank = json.loads((ROOT / "style.example.json").read_text())
        self.assertEqual(set(rocha), set(blank))
        for k in ("palette", "fonts", "lines"):
            self.assertEqual(set(rocha[k]), set(blank[k]))


class TestMotifs(unittest.TestCase):
    def setUp(self):
        meta, answers = recommend.load_answers(SAMPLE)
        self.meta = meta
        self.result = recommend.score(answers, "Hush Hour Studio", [], ["Port Halcyon"])

    def render(self, motif, card=False, style=None):
        return recommend.render_receipt(self.result, self.meta, "Hush Hour Studio", card=card, style=style, motif=motif)

    def test_each_motif_has_its_signature(self):
        analog, cyber, y2k = (self.render(m) for m in recommend.MOTIFS)
        self.assertIn('class="page m-analog"', analog)
        self.assertIn("AI RECEIPT", analog)
        self.assertIn('class="page m-cyberpunk"', cyber)
        self.assertIn("rocheverse:~$</span> ask --for", cyber)
        self.assertIn('class="cursor"', cyber)
        self.assertIn('class="page m-y2k-blog"', y2k)
        self.assertIn("ai-receipt.exe", y2k)
        self.assertIn("visitor no.<br><b>000,777</b>", y2k)
        self.assertIn("mood</h3><p>delulu ✧", y2k)
        self.assertIn("github.com/RochaStone/ai-recommends-you/issues", y2k)
        self.assertIn("AI RECEIPT", y2k)  # the receipt sits inside the window

    def test_same_data_in_every_motif(self):
        for m in recommend.MOTIFS:
            page = self.render(m)
            self.assertIn("3/10", page, m)
            self.assertIn("Kilnhouse Retreats", page, m)
            self.assertIn("build your founder world", page, m)

    def test_cyberpunk_block_bars(self):
        cyber = self.render("cyberpunk")
        self.assertIn('<b>█</b>░░░░░░░░░', cyber)       # ChatGPT 1/10
        self.assertIn('<b>███</b>░░░░░░░', cyber)       # Perplexity 3/10 and the total 3/10
        self.assertIn("family=Silkscreen", cyber)        # pixel labels
        self.assertNotIn("family=Silkscreen", self.render("analog"))

    def test_cards_carry_the_fit_script(self):
        for m in recommend.MOTIFS:
            card = self.render(m, card=True)
            self.assertIn(f'class="card m-{m}"', card)
            self.assertIn('querySelector(".fit")', card)
            self.assertEqual(len(re.findall(r'class="[^"]*\bfit\b', card)), 1, m)  # exactly one box to fit

    def test_motif_choice_and_aliases(self):
        self.assertEqual(recommend.resolve_motif(None, {}), "analog")
        self.assertEqual(recommend.resolve_motif(None, {"motif": "guest-check"}), "analog")
        self.assertEqual(recommend.resolve_motif(None, {"motif": "retro-tv"}), "cyberpunk")
        self.assertEqual(recommend.resolve_motif(None, {"motif": "sticker-collage"}), "y2k-blog")
        self.assertEqual(recommend.resolve_motif("cyberpunk", {"motif": "y2k-blog"}), "cyberpunk")
        self.assertEqual(recommend.resolve_motif(None, {"motif": "something else"}), "analog")

    def test_no_glow_in_any_skin(self):
        for f in ("receipt.css", "motif-cyberpunk.css", "motif-y2k.css"):
            css = (ROOT / "assets" / f).read_text()
            self.assertNotIn("text-shadow", css, f)
            self.assertNotIn("drop-shadow", css, f)

    def test_cli_motif_flag(self):
        with tempfile.TemporaryDirectory() as d:
            code = recommend.main([str(SAMPLE), "--out", d, "--no-png", "--motif", "y2k-blog"])
            self.assertEqual(code, 0)
            self.assertIn("ai-receipt.exe", (Path(d) / "receipt.html").read_text())
            self.assertIn('class="card m-y2k-blog"', (Path(d) / "receipt-card.html").read_text())


if __name__ == "__main__":
    unittest.main()
