"""Every figure the README quotes in "What the analysis found" is in the generated read-out.
Run after python3 src/run_all.py."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8").replace("−", "-")
REPORT = (ROOT / "reports" / "survey_report.md").read_text(encoding="utf-8").replace("−", "-")


class ReadmeMatchesTheReport(unittest.TestCase):
    def test_findings_figures_appear_in_the_report(self):
        section = README[README.index("## What the analysis found"):README.index("## The part most survey projects skip")]
        section = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", section)            # image links carry file numbers
        figures = set(re.findall(r"-?\d+(?:\.\d+)?%?", section))
        missing = sorted(f for f in figures if f not in REPORT)
        self.assertEqual(missing, [], f"README quotes figures the read-out does not contain: {missing}")


class SurveyAndTurnover(unittest.TestCase):
    """Exits are joined to the survey team by team, never person by person."""

    def test_the_followup_holds_team_totals_only(self):
        import csv
        with (ROOT / "data" / "team_followup.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(set(rows[0]), {"team_id", "headcount_at_survey", "voluntary_exits_12m", "involuntary_exits_12m"})
        with (ROOT / "data" / "teams.csv").open(encoding="utf-8") as fh:
            teams = {r["team_id"]: int(r["team_size"]) for r in csv.DictReader(fh)}
        self.assertEqual({r["team_id"]: int(r["headcount_at_survey"]) for r in rows}, teams)

    def test_the_report_states_the_team_rule_and_the_quartile_gap(self):
        report = (ROOT / "reports" / "survey_report.md").read_text(encoding="utf-8")
        section = report[report.index("## 4."):]
        self.assertIn("Only team by team", section)
        self.assertIn("nothing here should be used to guess", section)
        low = float(section.split("lowest-scoring quarter of teams lost ")[1].split("%")[0])
        high = float(section.split("; the highest, ")[1].split("%")[0])
        self.assertGreater(low, high)


if __name__ == "__main__":
    unittest.main()
