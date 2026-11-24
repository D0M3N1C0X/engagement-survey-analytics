"""
The browser tool's calculations, in Python, so web/engine.js can be checked against them value by value.

The tool reads any survey export: one row per invitee (or per respondent), a group column, items scored 1-5
assigned to dimensions, one dimension marked as the engagement outcome, and optionally a responded column and
an eNPS column. These are the same definitions as the read-out:

  - a respondent's favourable share in a dimension is the share of their answers at 4 or 5;
  - a score is the mean of respondents' shares, its interval a percentile bootstrap that resamples groups,
    drawn with the xorshift generator the dashboard uses so JavaScript can reproduce it exactly;
  - groups under five respondents are never shown;
  - key drivers are Johnson's relative weights of the dimension means on the engagement mean, run only with
    50 complete respondents in five or more groups.

    python3 src/tool_reference.py    writes tests/fixtures/tool_vectors.json
"""

from __future__ import annotations

import json
import random

from statlib import mean, relative_weights
from surveylib import (DIMENSION_ORDER, MIN_GROUP, ROOT, driver_items, load_instrument, load_responses,
                       outcome_items)

VECTORS = ROOT / "tests" / "fixtures" / "tool_vectors.json"
REPS, SEED = 1000, 31
MIN_DRIVER_RESPONDENTS, MIN_DRIVER_GROUPS = 50, 5


def bootstrap(values: list[float], clusters: list[str]) -> list[float] | None:
    """The dashboard's interval: xorshift32 draws, cluster resampling when there is more than one group."""
    if not values:
        return None
    if len(values) == 1:
        return [values[0], values[0]]
    state = SEED

    def index(n: int) -> int:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        return state % n

    groups: dict[str, list[float]] = {}
    for v, c in zip(values, clusters):
        groups.setdefault(c, []).append(v)
    draws = []
    if len(groups) > 1:
        members = list(groups.values())
        for _ in range(REPS):
            total, count = 0.0, 0
            for _ in range(len(members)):
                for v in members[index(len(members))]:
                    total += v
                    count += 1
            draws.append(total / count)
    else:
        for _ in range(REPS):
            total = 0.0
            for _ in range(len(values)):
                total += values[index(len(values))]
            draws.append(total / len(values))
    draws.sort()
    lo = draws[int(0.025 * (REPS - 1))]
    hi = draws[_ceil(0.975 * (REPS - 1))]
    return [lo, hi]


def _ceil(x: float) -> int:
    i = int(x)
    return i if i == x else i + 1


def share(answers: list[int]) -> float | None:
    return sum(1 for a in answers if a >= 4) / len(answers) if answers else None


def analyse(rows: list[dict], dims: dict[str, list[str]], outcome: list[str]) -> dict:
    """rows: {"group", "responded", "enps", "items": {item: 1-5 or None}}; dims: dimension -> items, in order."""
    resp = [r for r in rows if r["responded"]]
    out = {"invited": len(rows), "respondents": len(resp),
           "response_rate": len(resp) / len(rows) if rows else None}

    def scored(items):
        vals, clus = [], []
        for r in resp:
            s = share([r["items"][i] for i in items if r["items"].get(i)])
            if s is not None:
                vals.append(s)
                clus.append(r["group"])
        return vals, clus

    vals, clus = scored(outcome)
    out["engagement"] = {"score": mean(vals) if vals else None, "people": len(vals), "ci": bootstrap(vals, clus)}
    out["dimensions"] = []
    for d, items in dims.items():
        v, c = scored(items)
        out["dimensions"].append({"dimension": d, "score": mean(v) if v else None, "people": len(v),
                                  "ci": bootstrap(v, c)})
    rated = [r["enps"] for r in resp if r.get("enps") is not None]
    out["enps"] = None
    if rated:
        pro, det = sum(1 for e in rated if e >= 9), sum(1 for e in rated if e <= 6)
        out["enps"] = {"score": (pro - det) / len(rated) * 100, "rated": len(rated), "promoters": pro, "detractors": det}

    out["groups"] = []
    for g in sorted({r["group"] for r in rows}):
        members = [r for r in resp if r["group"] == g]
        invited = sum(1 for r in rows if r["group"] == g)
        if len(members) < MIN_GROUP:
            out["groups"].append({"group": g, "invited": invited, "respondents": None})
            continue
        entry = {"group": g, "invited": invited, "respondents": len(members)}
        for name, items in [("engagement", outcome), *dims.items()]:
            s = [x for r in members if (x := share([r["items"][i] for i in items if r["items"].get(i)])) is not None]
            entry[name] = mean(s) if s else None
        out["groups"].append(entry)

    # Key drivers: respondent dimension means (1-5) against the engagement mean, complete cases only
    cols = [[] for _ in dims]
    y, groups = [], []
    for r in resp:
        means = []
        for items in dims.values():
            a = [r["items"][i] for i in items if r["items"].get(i)]
            means.append(sum(a) / len(a) if a else None)
        e = [r["items"][i] for i in outcome if r["items"].get(i)]
        if None in means or not e:
            continue
        for k, m in enumerate(means):
            cols[k].append(m)
        y.append(sum(e) / len(e))
        groups.append(r["group"])
    out["drivers"] = None
    if len(y) >= MIN_DRIVER_RESPONDENTS and len(set(groups)) >= MIN_DRIVER_GROUPS and len(dims) >= 2:
        try:
            weights, r2 = relative_weights(cols, y)
            out["drivers"] = {"n": len(y), "r2": r2, "weights": dict(zip(dims, weights))}
        except (ValueError, ZeroDivisionError):
            out["drivers"] = None
    return out


# ------------------------------------------------------------------ vectors

def repo_case() -> tuple[list[dict], dict, list[str]]:
    instrument = load_instrument()
    dims = {d: driver_items(instrument)[d] for d in DIMENSION_ORDER}
    outcome = outcome_items(instrument)
    rows = [{"group": r["team_id"], "responded": bool(r["responded"]), "enps": r["enps"],
             "items": {i: r[i] for i in [*sum(dims.values(), []), *outcome]}} for r in load_responses()]
    return rows, dims, outcome


def random_case(rng: random.Random) -> tuple[list[dict], dict, list[str]]:
    n_dims = rng.randint(1, 5)
    dims = {f"D{k + 1}": [f"d{k + 1}_{j + 1}" for j in range(rng.randint(1, 3))] for k in range(n_dims)}
    outcome = [f"eng_{j + 1}" for j in range(rng.randint(1, 3))]
    groups = [f"G{g:02d}" for g in range(rng.randint(1, 12))]
    rows = []
    for _ in range(rng.choice([4, 30, 120, 400])):
        latent = rng.gauss(0, 1)
        responded = rng.random() < 0.75
        items = {}
        for it in [*sum(dims.values(), []), *outcome]:
            items[it] = (max(1, min(5, round(3 + latent + rng.gauss(0, 1)))) if responded and rng.random() > 0.05 else None)
        rows.append({"group": rng.choice(groups), "responded": responded,
                     "enps": max(0, min(10, round(6 + 2 * latent + rng.gauss(0, 1.5)))) if responded and rng.random() > 0.1 else None,
                     "items": items})
    return rows, dims, outcome


def write_vectors() -> int:
    rng = random.Random(2026)
    rows, dims, outcome = repo_case()
    cases = [{"name": "repository data", "source": "data", "dims": list(dims.items()), "outcome": outcome,
              "result": analyse(rows, dims, outcome)}]
    for k in range(25):
        rows, dims, outcome = random_case(rng)
        cases.append({"name": f"random {k + 1}", "rows": rows, "dims": list(dims.items()), "outcome": outcome,
                      "result": analyse(rows, dims, outcome)})
    VECTORS.parent.mkdir(parents=True, exist_ok=True)
    VECTORS.write_text(json.dumps({"cases": cases}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(cases)


if __name__ == "__main__":
    print(f"     tests/fixtures/tool_vectors.json ({write_vectors()} cases)")
