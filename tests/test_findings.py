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


if __name__ == "__main__":
    unittest.main()
