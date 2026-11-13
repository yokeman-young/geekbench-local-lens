import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gblens import render  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "examples", "results", "sample-macbook-air-m5.gb7.json")


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.report, self.html = render.render_file(FIXTURE)

    def test_scores_are_extracted(self):
        self.assertEqual(self.report.single["score"], 3648)
        self.assertEqual(self.report.multi["score"], 17428)

    def test_workloads_have_rates(self):
        first = self.report.single["workloads"][0]
        self.assertTrue(first["name"])
        self.assertGreater(first["score"], 0)

    def test_html_is_self_contained(self):
        self.assertIn("<!doctype html>", self.html)
        self.assertIn("Single-Core Score", self.html)
        self.assertIn("3,648", self.html)
        self.assertNotIn("http://", self.html.split("<body>")[0])  # no external assets in head

    def test_terminal_table(self):
        table = render.to_terminal(self.report)
        self.assertIn("Score", table)
        self.assertIn("Multi-Core", table) if False else self.assertIn("MULTI", table)

    def test_unknown_schema_is_empty(self):
        report = render.parse_document({"foo": [1, 2, 3]})
        self.assertTrue(report.empty)

    def test_alternate_shape(self):
        doc = {
            "single_core": {"score": 1111, "workloads": [{"name": "A", "score": 12}]},
            "multi_core": {"score": 2222, "workloads": [{"name": "A", "score": 34}]},
        }
        report = render.parse_document(doc)
        self.assertEqual(report.single["score"], 1111)
        self.assertEqual(report.multi["score"], 2222)


class FixtureTests(unittest.TestCase):
    def test_fixture_is_scrubbed(self):
        with open(FIXTURE) as handle:
            doc = json.load(handle)
        for key in ("system_uuid", "uuid", "checksum", "commit"):
            self.assertNotIn(key, doc)


if __name__ == "__main__":
    unittest.main()
