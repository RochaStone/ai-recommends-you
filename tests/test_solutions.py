"""Tests for the five free fixes. Run from the repo root: python3 -m unittest discover -s tests -v

Only our own code runs here. The egeo integration test is skipped unless egeo is importable.
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import recommend  # noqa: E402
from solutions import answers, common, entity_page, llms, mentions, to_gaps  # noqa: E402
from solutions.page_render import render_page  # noqa: E402

SAMPLE = ROOT / "examples" / "answers.sample.json"
ENTITY = ROOT / "examples" / "entity.sample.json"
PREVIOUS = ROOT / "examples" / "summary.previous.sample.json"
EXAMPLE_STYLE = json.loads((ROOT / "examples" / "style.rocha-coded.json").read_text())


def scored():
    meta, ans = recommend.load_answers(SAMPLE)
    return meta, ans, recommend.score(ans, meta["name"], meta["aliases"], [meta["location"], meta["niche"]])


class TestToGaps(unittest.TestCase):
    def test_shape_matches_egeo_generic_gaps(self):
        meta, ans, result = scored()
        rows = to_gaps.to_gaps(meta, ans)
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertTrue(set(r) <= {"query", "cited", "sources"}, r)
            self.assertIsInstance(r["cited"], bool)
        self.assertEqual(sum(1 for r in rows if not r["cited"]), len(result["lost"]))
        self.assertEqual({r["query"] for r in rows if not r["cited"]}, set(result["lost"]))

    def test_sources_are_urls_from_answers_that_missed_her(self):
        ans = [{"question": "best kiln", "source": "Perplexity",
                "answer": "Try Kilnhouse (https://kilnhouse.example/retreats). Sources: https://guide.example."},
               {"question": "is Hush Hour Studio good", "source": "ChatGPT",
                "answer": "Hush Hour Studio is lovely, see https://hushhour.example"}]
        rows = to_gaps.to_gaps({"name": "Hush Hour Studio"}, ans)
        self.assertEqual(rows[0]["sources"], ["https://kilnhouse.example/retreats", "https://guide.example"])
        self.assertNotIn("sources", rows[1])

    def test_cli_writes_json_array(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "gaps.json"
            self.assertEqual(to_gaps.main([str(SAMPLE), "--out", str(out)]), 0)
            self.assertIsInstance(json.loads(out.read_text()), list)

    def test_needs_a_name(self):
        with self.assertRaises(ValueError):
            to_gaps.to_gaps({}, [{"question": "q", "answer": "a"}])


class TestEntityPage(unittest.TestCase):
    def setUp(self):
        self.ent = common.load_entity(ENTITY)

    def build(self, motif):
        with tempfile.TemporaryDirectory() as d:
            folder = entity_page.build(self.ent, Path(d), EXAMPLE_STYLE, motif, "2026-10-28")
            return (folder / "index.html").read_text(), (folder / "index.md").read_text()

    def test_jsonld_parses_with_org_service_faq(self):
        page, _ = self.build("analog")
        blocks = common.ld_blocks(page)
        self.assertEqual(len(blocks), 1)
        types = [n["@type"] for n in blocks[0]["@graph"]]
        self.assertEqual(types, ["Organization", "Service", "FAQPage"])
        org, service, faq = blocks[0]["@graph"]
        self.assertEqual(org["name"], "Hush Hour Studio")
        self.assertEqual(org["founder"]["name"], "Mara Quill")
        self.assertEqual(service["provider"]["@id"], org["@id"])
        self.assertEqual(len(faq["mainEntity"]), 2)  # her FAQ + her one written lost-question answer

    def test_direct_answer_comes_first_and_lines_carry_her_name(self):
        page, md = self.build("analog")
        body = page.split("<body", 1)[1]
        self.assertLess(body.index('class="answer"'), body.index("In short"))
        self.assertTrue(md.splitlines()[2].startswith("Hush Hour Studio"))
        for s in common.quotables(self.ent)[:4]:
            self.assertIn("Hush Hour Studio", s)

    def test_person_kind_and_script_escaping(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.json"
            p.write_text(json.dumps({"name": "Mara Quill", "person": "Mara Quill", "what": "clay </script><b>x",
                                     "site": "javascript:alert(1)"}))
            ent = common.load_entity(p)
            self.assertEqual(ent["kind"], "Person")
            self.assertEqual(ent["site"], "")
            page = entity_page.build(ent, Path(d), EXAMPLE_STYLE, "analog", "2026-10-28").joinpath("index.html").read_text()
            self.assertEqual(common.ld_blocks(page)[0]["@graph"][0]["@type"], "Person")
            self.assertNotIn("</script><b>", page)
            self.assertNotIn("javascript:", page)

    def test_missing_name_is_a_kind_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.json"
            p.write_text(json.dumps({"what": "pottery"}))
            with self.assertRaises(common.EntityError):
                common.load_entity(p)
            self.assertEqual(entity_page.main([str(p), "--out", d]), 2)

    def test_three_motifs(self):
        marks = {"analog": "pg-sheet", "cyberpunk": "rocheverse:~$", "y2k-blog": "000,777"}
        for motif, mark in marks.items():
            page, _ = self.build(motif)
            self.assertIn(mark, page, motif)
            self.assertIn(f"m-{motif}", page)
            self.assertEqual(len(common.ld_blocks(page)), 1, motif)

    def test_her_page_is_signed_with_her_name(self):
        page, md = self.build("y2k-blog")
        self.assertIn("Hush Hour Studio · made with Rocha Coded", page)
        self.assertNotIn("@rocheverse", page)
        self.assertEqual(md.count("Hush Hour Studio runs moonlit"), 1)  # the lead line is not repeated

    def test_no_glow_in_page_css(self):
        css = (ROOT / "assets" / "page.css").read_text()
        self.assertNotIn("text-shadow", css)
        self.assertNotIn("drop-shadow", css)


class TestAnswers(unittest.TestCase):
    def test_one_file_per_lost_question_with_valid_faq(self):
        ent = common.load_entity(ENTITY)
        _, _, result = scored()
        with tempfile.TemporaryDirectory() as d:
            res = answers.build(result["lost"], ent, Path(d), EXAMPLE_STYLE, "cyberpunk", "2026-10-28", use_egeo=False)
            files = sorted((Path(d) / "answers").glob("*.md"))
            self.assertEqual(len(files), len(result["lost"]))
            for f in files:
                text = f.read_text()
                self.assertEqual(common.ld_blocks(text)[0]["@type"], "FAQPage")
            mine = [x for x in res["items"] if not x["draft"]]
            self.assertEqual(len(mine), 1)
            self.assertTrue(mine[0]["answer"].startswith("Hush Hour Studio is a pottery retreat"))
            faq = json.loads((Path(d) / "answers" / "faq.json").read_text())
            self.assertEqual(len(faq["mainEntity"]), len(result["lost"]))
            self.assertIn("rocheverse:~$", (Path(d) / "answers" / "index.html").read_text())

    def test_reads_lost_from_summary_or_answers(self):
        _, _, result = scored()
        self.assertEqual(common.lost_questions(SAMPLE), result["lost"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "summary.json"
            p.write_text(json.dumps({"lost": ["q one", "q two"]}))
            self.assertEqual(common.lost_questions(p), ["q one", "q two"])

    def test_duplicate_slugs_stay_apart(self):
        ent = common.load_entity(ENTITY)
        with tempfile.TemporaryDirectory() as d:
            res = answers.build(["Best kiln?", "best kiln!"], ent, Path(d), EXAMPLE_STYLE, None, "2026-10-28", False)
            self.assertEqual([x["slug"] for x in res["items"]], ["best-kiln", "best-kiln-2"])

    @unittest.skipUnless(importlib.util.find_spec("egeo") and common.egeo_path(), "egeo is not installed")
    def test_egeo_optimize_runs_when_installed(self):
        import os
        os.environ.setdefault("GEO_EVAL_MOCK", "1")
        ent = common.load_entity(ENTITY)
        with tempfile.TemporaryDirectory() as d:
            res = answers.build(["moonlit pottery class"], ent, Path(d), EXAMPLE_STYLE, None, "2026-10-28", True)
            self.assertTrue(res["egeo"] and res["egeo"][0]["ok"], res["egeo"])


class TestMentions(unittest.TestCase):
    def setUp(self):
        self.ent = common.load_entity(ENTITY)

    def test_drops_places_without_link_or_source(self):
        raw = [{"name": "Real Dir", "url": "https://dir.example/list", "kind": "directory", "found_via": "search: x"},
               {"name": "No Link", "kind": "podcast", "found_via": "search: y"},
               {"name": "No Source", "url": "https://pod.example"},
               {"name": "Dupe", "url": "https://dir.example/list", "found_via": "z"}]
        keep, dropped = mentions.clean_places(raw)
        self.assertEqual([p["name"] for p in keep], ["Real Dir"])
        self.assertEqual(dropped, 3)

    def test_caps_at_ten(self):
        raw = [{"name": f"P{i}", "url": f"https://p{i}.example", "found_via": "s"} for i in range(14)]
        keep, dropped = mentions.clean_places(raw)
        self.assertEqual(len(keep), 10)
        self.assertEqual(dropped, 4)

    def test_no_search_gives_a_checklist_and_the_handoff(self):
        plan = mentions.render_plan(self.ent, "pottery retreats", [], 0)
        self.assertIn("- [ ] search:", plan)
        self.assertIn("podcast-outreach-engine", plan)
        self.assertNotIn("\u2014", plan)

    def test_pitch_is_three_lines_in_her_words(self):
        for kind in mentions.KINDS:
            lines = mentions.pitch(kind, self.ent)
            self.assertEqual(len(lines), 3)
            self.assertIn("Mara Quill", lines[0])
            self.assertEqual(lines[1], self.ent["proof"][0])


class TestLlms(unittest.TestCase):
    def test_llms_txt_follows_the_spec(self):
        ent = common.load_entity(ENTITY)
        _, _, result = scored()
        with tempfile.TemporaryDirectory() as d:
            answers.build(result["lost"], ent, Path(d), EXAMPLE_STYLE, None, "2026-10-28", use_egeo=False)
            folder = llms.build(ent, Path(d))
            txt = (folder / "llms.txt").read_text()
            lines = txt.splitlines()
            self.assertEqual(lines[0], "# Hush Hour Studio")
            self.assertEqual(sum(1 for x in lines if x.startswith("# ")), 1)
            self.assertTrue(lines[2].startswith("> "))
            h2 = [x for x in lines if x.startswith("## ")]
            self.assertEqual(h2, ["## About", "## Answers", "## Optional"])
            items = [x for x in lines if x.startswith("- ")]
            self.assertTrue(items)
            for item in items:
                self.assertRegex(item, r"^- \[[^\]]+\]\([^)\s]+\)(: .+)?$")
            self.assertEqual(sum(1 for x in items if "/faq#" in x), len(result["lost"]))
            full = (folder / "llms-full.txt").read_text()
            self.assertIn("## moonlit pottery class", full)
            note = (folder / "AI-CRAWLERS.md").read_text()
            self.assertIn("OAI-SearchBot", note)
            self.assertIn("PerplexityBot", note)

    def test_no_site_still_writes_valid_links(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.json"
            p.write_text(json.dumps({"name": "Mara Quill", "what": "pottery"}))
            txt = llms.llms_txt(common.load_entity(p), [])
            self.assertIn("- [Mara Quill](/): ", txt)


class TestCompare(unittest.TestCase):
    def test_last_month_line_and_moves(self):
        _, _, result = scored()
        prev = json.loads(PREVIOUS.read_text())
        d = recommend.compare(prev, result, "2026-10-26")
        self.assertEqual(d["line"], "last month 1/10, today 3/10")
        self.assertEqual(d["change"], 2)
        self.assertEqual(len(d["newly_named"]), 2)
        self.assertEqual(d["newly_lost"], [])

    def test_label_when_not_a_month(self):
        _, _, result = scored()
        prev = {"named": 5, "total": 10, "date": "2026-10-20", "questions": []}
        self.assertEqual(recommend.compare(prev, result, "2026-10-26")["line"], "on 2026-10-20 5/10, today 3/10")
        prev["date"] = ""
        self.assertEqual(recommend.compare(prev, result, "2026-10-26")["line"], "last time 5/10, today 3/10")

    def test_cli_compare_stamps_receipt_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(recommend.main([str(SAMPLE), "--out", d, "--no-png", "--compare", str(PREVIOUS)]), 0)
            self.assertIn("last month 1/10, today 3/10", (Path(d) / "receipt.html").read_text())
            self.assertTrue((Path(d) / "delta.json").is_file())
            hist = json.loads((Path(d) / "history" / "summary-2026-10-26.json").read_text())
            self.assertEqual(hist["named"], 3)
            # a previous answers.json works too, scored the same way
            self.assertEqual(recommend.main([str(SAMPLE), "--out", d, "--no-png", "--compare", str(SAMPLE)]), 0)
            self.assertIn("3/10, today 3/10", (Path(d) / "receipt.html").read_text())

    def test_delta_line_in_every_motif(self):
        _, _, result = scored()
        meta = json.loads(SAMPLE.read_text())["meta"]
        for motif in recommend.MOTIFS:
            page = recommend.render_receipt(result, meta, meta["name"], style=EXAMPLE_STYLE, motif=motif,
                                            delta="last month 1/10, today 3/10")
            self.assertIn("last month 1/10, today 3/10", page, motif)
        plain = recommend.render_receipt(result, meta, meta["name"], style=EXAMPLE_STYLE, motif="analog")
        self.assertNotIn("SINCE LAST TIME", plain)

    def test_bad_previous_file_still_makes_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("not json")
            self.assertEqual(recommend.main([str(SAMPLE), "--out", d, "--no-png", "--compare", str(bad)]), 0)
            self.assertTrue((Path(d) / "receipt.html").is_file())


class TestInheritanceOnPages(unittest.TestCase):
    def test_user_style_never_borrows_rochas_words(self):
        user = recommend.inherit_style({"palette": {"hero": "#112233"}, "lines": {}})
        page = render_page("t", "<p>x</p>", style=user, motif="analog")
        self.assertIn("--ground: #112233", page)
        self.assertIn("--gold: #E9B949", page)  # missing palette entries fall back
        self.assertNotIn("Rocha", page.split("<body", 1)[1].replace("Rocha Coded", ""))
        self.assertNotIn("@rocheverse", page)
        with_owner = render_page("t", "<p>x</p>", style=EXAMPLE_STYLE, motif="analog")
        self.assertIn("@rocheverse", with_owner)

    def test_no_em_dashes_in_any_output(self):
        ent = common.load_entity(ENTITY)
        _, _, result = scored()
        with tempfile.TemporaryDirectory() as d:
            entity_page.build(ent, Path(d), EXAMPLE_STYLE, "y2k-blog", "2026-10-28")
            answers.build(result["lost"], ent, Path(d), EXAMPLE_STYLE, None, "2026-10-28", use_egeo=False)
            llms.build(ent, Path(d))
            for f in Path(d).rglob("*"):
                if f.is_file() and f.suffix in (".md", ".txt", ".html", ".json"):
                    self.assertFalse(re.search("\u2014", f.read_text()), f)


if __name__ == "__main__":
    unittest.main()
