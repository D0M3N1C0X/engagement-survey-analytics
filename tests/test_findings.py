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


class ToolVectors(unittest.TestCase):
    """The committed cases the browser tool is checked on are what the Python reference computes today (within 1e-9)."""

    def test_the_vectors_are_current(self):
        import json
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        import tool_reference as ref

        with (ROOT / "tests" / "fixtures" / "tool_vectors.json").open(encoding="utf-8") as fh:
            committed = json.load(fh)

        def close(a, b, path):
            if isinstance(b, dict):
                self.assertEqual(set(a), set(b), path)
                for k in b:
                    close(a[k], b[k], f"{path}.{k}")
            elif isinstance(b, list):
                self.assertEqual(len(a), len(b), path)
                for i, (x, y) in enumerate(zip(a, b)):
                    close(x, y, f"{path}[{i}]")
            elif isinstance(b, float):
                self.assertAlmostEqual(a, b, delta=1e-9 * max(1.0, abs(b)), msg=path)
            else:
                self.assertEqual(a, b, path)

        for case in committed["cases"]:
            dims = dict(case["dims"])
            rows = ref.repo_case()[0] if "source" in case else case["rows"]
            fresh = json.loads(json.dumps(ref.analyse(rows, dims, case["outcome"])))
            close(fresh, case["result"], case["name"])


class TwoWaves(unittest.TestCase):
    """The plan's effect is estimated against a comparison group, and the interval covers the generator's truth."""

    def test_the_interval_covers_the_true_effect_and_beats_before_and_after(self):
        report = (ROOT / "reports" / "survey_report.md").read_text(encoding="utf-8")
        section = report[report.index("## 5."):]
        self.assertIn("The interval covers it", section)
        naive = float(re.search(r"The action teams rose \*\*([+-][\d.]+) points", section).group(1))
        truth = float(re.search(r"what the plan did: \*\*([+-][\d.]+) points", section).group(1))
        self.assertGreater(naive, truth)

    def test_actions_only_go_to_eligible_teams(self):
        import csv
        with (ROOT / "data" / "team_actions.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(all(r["eligible"] == "1" for r in rows if r["action"] == "1"))
        eligible = sum(r["eligible"] == "1" for r in rows)
        self.assertEqual(sum(r["action"] == "1" for r in rows), eligible // 2)


if __name__ == "__main__":
    unittest.main()
