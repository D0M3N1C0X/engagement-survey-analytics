"""
Loading and survey-specific metrics.

Everything here follows the conventions an engagement survey is normally
reported with: favourable = the top two points of a five-point scale, eNPS =
promoters minus detractors, and no result published for a group smaller than
the confidentiality threshold.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

from statlib import bootstrap_mean_interval, mean

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("SURVEY_DATA_DIR", ROOT / "data")).expanduser().resolve()
OUTPUT = Path(os.environ.get("SURVEY_OUTPUT_DIR", ROOT / "reports")).expanduser().resolve()
FIGURES = OUTPUT / "figures"
PRIVATE_MODE = os.environ.get("SURVEY_PRIVATE_MODE") == "1"

SURVEY_NAME = os.environ.get("SURVEY_NAME", "Voice 2026")
FIELD_WINDOW = os.environ.get("SURVEY_FIELD_WINDOW", "4-22 May 2026")

# Confidentiality: no score is ever published for a group below this many
# respondents. It is the promise that makes people answer honestly, and
# breaking it once is enough to lose the next survey.
MIN_GROUP = 5

FAVOURABLE_POINTS = (4, 5)
UNFAVOURABLE_POINTS = (1, 2)

DIMENSION_ORDER = [
    "Manager Support",
    "Career Growth",
    "Recognition",
    "Workload & Wellbeing",
    "Leadership & Direction",
    "Pay & Benefits",
    "Inclusion & Belonging",
    "Tools & Process",
]

SEGMENTS = ["department", "country", "job_level", "tenure_band", "work_model"]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_instrument() -> dict[str, dict]:
    """item_id -> {dimension, wording, type}."""
    return {r["item_id"].strip(): {key: value.strip() for key, value in r.items()}
            for r in csv.DictReader(
                (DATA / "survey_instrument.csv").open(encoding="utf-8-sig", newline=""))}


def driver_items(instrument: dict[str, dict]) -> dict[str, list[str]]:
    """dimension -> item ids, in questionnaire order."""
    out: dict[str, list[str]] = defaultdict(list)
    for item_id, meta in instrument.items():
        if meta["type"] == "driver":
            out[meta["dimension"]].append(item_id)
    return dict(out)


def outcome_items(instrument: dict[str, dict]) -> list[str]:
    return [i for i, m in instrument.items() if m["type"] == "outcome" and i != "enps"]


def load_responses() -> list[dict]:
    rows = []
    instrument = load_instrument()
    for r in csv.DictReader((DATA / "survey_responses.csv").open(encoding="utf-8-sig", newline="")):
        r = {key: value.strip() for key, value in r.items()}
        r["responded"] = r["responded"] == "1"
        r["shift_worker"] = r["shift_worker"] == "1"
        r["enps"] = int(r["enps"]) if r["enps"] else None
        for item_id in instrument:
            if item_id in r:
                r[item_id] = int(r[item_id]) if r[item_id] else None
        rows.append(r)
    return rows


def load_teams() -> dict[str, dict]:
    teams = {}
    for r in csv.DictReader((DATA / "teams.csv").open(encoding="utf-8-sig", newline="")):
        r = {key: value.strip() for key, value in r.items()}
        r["team_size"] = int(r["team_size"])
        r["manager_tenure_months"] = int(r.get("manager_tenure_months") or 0)
        teams[r["team_id"]] = r
    return teams


def load_comments() -> list[dict]:
    path = DATA / "survey_comments.csv"
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    for row in rows:
        for key in ("comment_id", "response_id", "question"):
            row[key] = row[key].strip()
    return rows


def respondents(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["responded"]]


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def favourable(values: list[int]) -> tuple[int, int, float]:
    """(favourable count, valid answers, favourable rate) for a list of item scores."""
    valid = [v for v in values if v]
    if not valid:
        return (0, 0, float("nan"))
    k = sum(1 for v in valid if v in FAVOURABLE_POINTS)
    return (k, len(valid), k / len(valid))


def respondent_favourable(row: dict, items: list[str]) -> float | None:
    """Favourable share for one respondent, keeping the person as the analysis unit."""
    values = [row[item] for item in items if row.get(item)]
    if not values:
        return None
    return sum(1 for value in values if value in FAVOURABLE_POINTS) / len(values)


def dimension_values(rows: list[dict], items: list[str]) -> list[int]:
    """Every item answer inside a dimension, pooled across respondents."""
    return [r[item] for r in rows for item in items if r.get(item)]


def dimension_score(rows: list[dict], items: list[str]) -> dict:
    eligible = [(r, respondent_favourable(r, items)) for r in rows]
    eligible = [(r, score) for r, score in eligible if score is not None]
    person_rates = [score for _row, score in eligible]
    rate = mean(person_rates)
    low, high = bootstrap_mean_interval(
        person_rates, clusters=[r.get("team_id") for r, _score in eligible])
    scores = [r[item] for r in rows for item in items if r.get(item)]
    return {"favourable": rate, "n_answers": len(scores),
            "n_respondents": len(person_rates),
            "ci_low": low, "ci_high": high, "mean": mean(scores) if scores else float("nan")}


def respondent_dimension_means(row: dict, items_by_dim: dict[str, list[str]]) -> dict[str, float]:
    """One score per dimension for a single respondent - the regression inputs."""
    out = {}
    for dim, items in items_by_dim.items():
        scores = [row[i] for i in items if row.get(i)]
        if scores:
            out[dim] = mean(scores)
    return out


def engagement_index(row: dict, outcome: list[str]) -> float | None:
    scores = [row[i] for i in outcome if row.get(i)]
    return mean(scores) if scores else None


def enps(scores: list[int]) -> dict:
    """Employee Net Promoter Score: promoters (9-10) minus detractors (0-6)."""
    valid = [s for s in scores if s is not None]
    if not valid:
        return {"enps": float("nan"), "n": 0}
    promoters = sum(1 for s in valid if s >= 9)
    passives = sum(1 for s in valid if 7 <= s <= 8)
    detractors = sum(1 for s in valid if s <= 6)
    n = len(valid)
    return {"enps": (promoters - detractors) / n * 100, "n": n,
            "promoters": promoters / n, "passives": passives / n,
            "detractors": detractors / n,
            "promoter_n": promoters, "detractor_n": detractors}


# --------------------------------------------------------------------------
# Segments
# --------------------------------------------------------------------------

def group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return dict(out)


def reportable(group: list[dict]) -> bool:
    """The confidentiality gate. Call it before publishing any group result."""
    return len(group) >= MIN_GROUP


def segment_comparison(rows: list[dict], key: str, items: list[str]) -> list[dict]:
    """
    Descriptive respondent-level favourable rates by segment.

    Items from one respondent are not independent observations, so segments
    use one mean per respondent and bootstrap those people as the sampling unit.
    These intervals are descriptive; this function makes no significance claim.
    """
    out = []
    all_values = [score for r in rows
                  if (score := respondent_favourable(r, items)) is not None]
    company_rate = mean(all_values)
    for value, group in sorted(group_by(rows, key).items()):
        eligible = [(r, respondent_favourable(r, items)) for r in group]
        eligible = [(r, score) for r, score in eligible if score is not None]
        person_rates = [score for _row, score in eligible]
        if len(person_rates) < MIN_GROUP:
            out.append({"segment": value, "n": len(person_rates), "suppressed": True})
            continue
        rate = mean(person_rates)
        low, high = bootstrap_mean_interval(
            person_rates, seed=17, clusters=[r.get("team_id") for r, _score in eligible])
        out.append({"segment": value, "n": len(person_rates), "suppressed": False,
                    "favourable": rate, "ci_low": low, "ci_high": high,
                    "vs_company": rate - company_rate})
    return out


def response_rate(rows: list[dict], key: str) -> list[dict]:
    """Response rate per segment, on the full invite list."""
    out = []
    for value, group in sorted(group_by(rows, key).items()):
        answered = sum(1 for r in group if r["responded"])
        if len(group) < MIN_GROUP or answered < MIN_GROUP:
            out.append({"segment": value, "invited": len(group), "responded": answered,
                        "rate": float("nan"), "ci_low": float("nan"),
                        "ci_high": float("nan"), "suppressed": True})
            continue
        rates = [1.0 if row["responded"] else 0.0 for row in group]
        low, high = bootstrap_mean_interval(
            rates, seed=19, clusters=[row.get("team_id") for row in group])
        out.append({"segment": value, "invited": len(group), "responded": answered,
                    "rate": answered / len(group), "ci_low": low, "ci_high": high,
                    "suppressed": False})
    return out


def representation_gap(rows: list[dict], key: str) -> list[dict]:
    """
    How each segment's share of respondents compares with its share of headcount.

    A survey that over-represents head-office and under-represents the shop
    floor will report a healthier company than the one that exists.
    """
    answered = [r for r in rows if r["responded"]]
    out = []
    for value, group in sorted(group_by(rows, key).items()):
        invited_share = len(group) / len(rows)
        respondent_count = sum(1 for r in answered if r[key] == value)
        respondent_share = respondent_count / len(answered)
        out.append({"segment": value, "invited_share": invited_share,
                    "respondent_share": respondent_share,
                    "gap_pp": (respondent_share - invited_share) * 100,
                    "suppressed": respondent_count < MIN_GROUP or len(group) < MIN_GROUP})
    return sorted(out, key=lambda d: d["gap_pp"])


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def md_table(headers: list[str], rows: list[list], align: str = "") -> str:
    def cell(value) -> str:
        return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("|", "&#124;").replace("\r", " ").replace("\n", " ")
                .replace("[", "\\[").replace("]", "\\]"))

    align = align or "l" * len(headers)
    sep = {"l": ":---", "r": "---:", "c": ":---:"}
    out = ["| " + " | ".join(cell(h) for h in headers) + " |",
           "| " + " | ".join(sep[a] for a in align) + " |"]
    for row in rows:
        out.append("| " + " | ".join(cell(c) for c in row) + " |")
    return "\n".join(out)


def md_text(value: str) -> str:
    """Render an external label as plain Markdown text, not raw HTML or markup."""
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("|", "&#124;").replace("\r", " ").replace("\n", " ")
            .replace("[", "\\[").replace("]", "\\]").replace("`", "\\`"))
