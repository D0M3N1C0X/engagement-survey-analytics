"""Checks for the documented local CSV contract and respondent-level aggregation."""

import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from local_run import DatasetError, validate_dataset  # noqa: E402
from surveylib import md_table, segment_comparison  # noqa: E402


class LocalInputContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="survey-validation-")
        self.data = Path(self.temp.name) / "data"
        self.data.mkdir()
        for name in ("survey_instrument.csv", "survey_responses.csv", "teams.csv",
                     "survey_comments.csv", "comment_themes_truth.csv"):
            shutil.copy2(ROOT / "data" / name, self.data / name)

    def tearDown(self):
        self.temp.cleanup()

    def _rewrite_responses(self, change):
        path = self.data / "survey_responses.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers, rows = reader.fieldnames, list(reader)
        change(rows, headers)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def test_documented_synthetic_schema_validates(self):
        summary = validate_dataset(self.data)
        self.assertEqual(summary["invitees"], 3800)
        self.assertEqual(summary["respondents"], 2753)
        self.assertGreater(summary["comments"], 0)

    def test_duplicate_response_id_is_rejected(self):
        self._rewrite_responses(lambda rows, _headers: rows[1].update(
            response_id=rows[0]["response_id"]))
        with self.assertRaisesRegex(DatasetError, "duplicated"):
            validate_dataset(self.data)

    def test_out_of_range_enps_is_rejected_separately_from_likert_items(self):
        def set_invalid(rows, _headers):
            respondent = next(row for row in rows if row["responded"] == "1")
            respondent["enps"] = "11"

        self._rewrite_responses(set_invalid)
        with self.assertRaisesRegex(DatasetError, "eNPS must be from 0 to 10"):
            validate_dataset(self.data)


class RespondentLevelComparison(unittest.TestCase):
    def test_one_respondent_counts_once_even_when_they_answer_more_items(self):
        rows = [
            {"department": "A", "q1": 5, "q2": 5},
            *[{"department": "A", "q1": 1, "q2": None} for _ in range(4)],
            *[{"department": "B", "q1": 1, "q2": 1} for _ in range(5)],
        ]
        result = {row["segment"]: row for row in segment_comparison(rows, "department", ["q1", "q2"])}
        self.assertAlmostEqual(result["A"]["favourable"], 0.2)
        self.assertEqual(result["A"]["n"], 5)
        self.assertFalse(result["A"]["suppressed"])

    def test_segments_with_fewer_than_five_respondents_are_suppressed(self):
        rows = ([{"department": "A", "q1": 4}] * 4
                + [{"department": "B", "q1": 4}] * 5)
        result = {row["segment"]: row for row in segment_comparison(rows, "department", ["q1"])}
        self.assertTrue(result["A"]["suppressed"])
        self.assertNotIn("favourable", result["A"])
        self.assertFalse(result["B"]["suppressed"])

    def test_report_tables_escape_untrusted_labels(self):
        rendered = md_table(["Department"], [["</script>|[link](javascript:alert(1))"]])
        self.assertIn("&lt;/script&gt;", rendered)
        self.assertIn("&#124;", rendered)
        self.assertIn(r"\[link\]", rendered)


if __name__ == "__main__":
    unittest.main()
