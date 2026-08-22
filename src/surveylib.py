"""
Loading and survey-specific metrics.

Everything here follows the conventions an engagement survey is normally
reported with: favourable = the top two points of a five-point scale, eNPS =
promoters minus detractors, and no result published for a group smaller than
the confidentiality threshold.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from statlib import mean, two_proportion_z, wilson_interval

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIGURES = ROOT / "reports" / "figures"

SURVEY_NAME = "Voice 2026"
FIELD_WINDOW = "4-22 May 2026"

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
    return {r["item_id"]: r for r in csv.DictReader(
        (DATA / "survey_instrument.csv").open(encoding="utf-8"))}


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
    for r in csv.DictReader((DATA / "survey_responses.csv").open(encoding="utf-8")):
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
    for r in csv.DictReader((DATA / "teams.csv").open(encoding="utf-8")):
        r["team_size"] = int(r["team_size"])
        r["manager_tenure_months"] = int(r["manager_tenure_months"])
        teams[r["team_id"]] = r
    return teams


def load_comments() -> list[dict]:
    return list(csv.DictReader((DATA / "survey_comments.csv").open(encoding="utf-8")))


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


def dimension_values(rows: list[dict], items: list[str]) -> list[int]:
    """Every item answer inside a dimension, pooled across respondents."""
    return [r[item] for r in rows for item in items if r.get(item)]


def dimension_score(rows: list[dict], items: list[str]) -> dict:
    k, n, rate = favourable(dimension_values(rows, items))
    low, high = wilson_interval(k, n)
    scores = [r[item] for r in rows for item in items if r.get(item)]
    return {"favourable": rate, "n_answers": n, "n_respondents": len(rows),
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
    Favourable rate per segment, tested against everyone outside that segment.

    Reporting a segment as 'below average' without a test is how survey
    read-outs turn sampling noise into performance management.
    """
    out = []
    all_k, all_n, _ = favourable(dimension_values(rows, items))
    for value, group in sorted(group_by(rows, key).items()):
        if not reportable(group):
            out.append({"segment": value, "n": len(group), "suppressed": True})
            continue
        k, n, rate = favourable(dimension_values(group, items))
        z, p = two_proportion_z(k, n, all_k - k, all_n - n)
        low, high = wilson_interval(k, n)
        out.append({"segment": value, "n": len(group), "suppressed": False,
                    "favourable": rate, "ci_low": low, "ci_high": high,
                    "z": z, "p": p, "vs_company": rate - all_k / all_n})
    return out


def response_rate(rows: list[dict], key: str) -> list[dict]:
    """Response rate per segment, on the full invite list."""
    out = []
    for value, group in sorted(group_by(rows, key).items()):
        answered = sum(1 for r in group if r["responded"])
        low, high = wilson_interval(answered, len(group))
        out.append({"segment": value, "invited": len(group), "responded": answered,
                    "rate": answered / len(group), "ci_low": low, "ci_high": high})
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
        respondent_share = sum(1 for r in answered if r[key] == value) / len(answered)
        out.append({"segment": value, "invited_share": invited_share,
                    "respondent_share": respondent_share,
                    "gap_pp": (respondent_share - invited_share) * 100})
    return sorted(out, key=lambda d: d["gap_pp"])


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def md_table(headers: list[str], rows: list[list], align: str = "") -> str:
    align = align or "l" * len(headers)
    sep = {"l": ":---", "r": "---:", "c": ":---:"}
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "| " + " | ".join(sep[a] for a in align) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)
