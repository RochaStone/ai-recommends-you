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
        self.assertIn("make them say your name", page)
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


if __name__ == "__main__":
    unittest.main()
