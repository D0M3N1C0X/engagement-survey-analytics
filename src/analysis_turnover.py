"""
Module 4 - Does the survey tell us who will leave? Only team by team, and that is the point.

The survey is confidential: no answer may be traced to a person. Exits, though, sit in the HRIS. The only
honest way to set one against the other is the team: each team's scores from the survey, each team's
resignations in the twelve months after fieldwork from the HRIS, joined on the team and nothing finer.

That design answers a question leadership asks ("do low-scoring teams lose more people?") and refuses one it
sometimes asks ("which of the people who answered badly will leave?"). The survey cannot answer the second
without breaking its own promise, and it should not try.

Exits are modelled as counts per team with headcount as exposure (Poisson, with standard errors widened for
overdispersion). Teams below the five-respondent rule are left out, as everywhere else in this read-out.
"""

from __future__ import annotations

import csv
import math

import viz
from statlib import mean, poisson_regression, two_sided_p
from surveylib import (DATA, FIGURES, MIN_GROUP, driver_items, group_by, load_instrument, load_responses, load_teams,
                       md_table, outcome_items, respondent_favourable)

FOLLOWUP = DATA / "team_followup.csv"
PER = 0.10            # rate ratios are quoted per 10 points of favourable score


def load_followup() -> dict[str, dict] | None:
    if not FOLLOWUP.exists():
        return None
    with FOLLOWUP.open(encoding="utf-8-sig", newline="") as fh:
        return {r["team_id"]: {"headcount": int(r["headcount_at_survey"]),
                               "exits": int(r["voluntary_exits_12m"])} for r in csv.DictReader(fh)}


def team_frame() -> tuple[list[dict], dict]:
    rows, teams, follow = load_responses(), load_teams(), load_followup()
    instrument = load_instrument()
    outcome, dims = outcome_items(instrument), driver_items(instrument)
    frame, left_out = [], {"teams": 0, "headcount": 0, "exits": 0}
    for team_id, members in group_by(rows, "team_id").items():
        f = follow.get(team_id) if follow else None
        if f is None:
            continue
        answered = [r for r in members if r["responded"]]
        if len(answered) < MIN_GROUP:
            left_out["teams"] += 1
            left_out["headcount"] += f["headcount"]
            left_out["exits"] += f["exits"]
            continue
        score = lambda items: mean([v for r in answered if (v := respondent_favourable(r, items)) is not None])
        frame.append({"team_id": team_id, "department": teams[team_id]["department"],
                      "headcount": f["headcount"], "exits": f["exits"], "responded": len(answered),
                      "response_rate": len(answered) / len(members), "engagement": score(outcome),
                      **{f"dim:{d}": score(items) for d, items in dims.items()}})
    return frame, left_out


def rate_ratio(frame: list[dict], keys: list[str], controls: bool = True, per_sd: bool = False) -> dict:
    """Poisson rate ratios for `keys`, per 10 points or per standard deviation across teams, departments held."""
    depts = sorted({t["department"] for t in frame})[1:] if controls else []
    unit = {}
    for k in keys:
        vals = [t[k] for t in frame]
        m = mean(vals)
        unit[k] = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) if per_sd else PER
    X = [[1.0] + [t[k] / unit[k] for k in keys] + [float(t["department"] == d) for d in depts] for t in frame]
    fit = poisson_regression(X, [t["exits"] for t in frame], [float(t["headcount"]) for t in frame])
    out = {"dispersion": fit["dispersion"], "terms": {}}
    for i, k in enumerate(keys, start=1):
        b, se = fit["coef"][i], fit["se"][i]
        out["terms"][k] = {"rr": math.exp(b), "low": math.exp(b - 1.96 * se), "high": math.exp(b + 1.96 * se),
                           "p": fit["p"][i]}
    out["coef"] = fit["coef"]
    return out


def top_driver() -> str:
    """The strongest driver of engagement in section 2, by relative weight, so the two sections are read together."""
    import analysis_drivers
    rows = load_responses()
    instrument = load_instrument()
    dims = driver_items(instrument)
    columns, y, _ = analysis_drivers.build_matrix([r for r in rows if r["responded"]], dims, outcome_items(instrument))
    from statlib import relative_weights
    weights, _ = relative_weights(columns, y)
    return max(zip(analysis_drivers.DIMENSION_ORDER, weights), key=lambda t: t[1])[0]


def quartiles(frame: list[dict]) -> list[dict]:
    ranked = sorted(frame, key=lambda t: (t["engagement"], t["team_id"]))
    out = []
    for q in range(4):
        part = ranked[q * len(ranked) // 4:(q + 1) * len(ranked) // 4]
        head, ex = sum(t["headcount"] for t in part), sum(t["exits"] for t in part)
        out.append({"teams": len(part), "headcount": head, "exits": ex, "rate": ex / head,
                    "low": part[0]["engagement"], "high": part[-1]["engagement"]})
    return out


def run() -> str:
    if load_followup() is None:
        return ("## 4. Does the survey tell us who will leave?\n\nSkipped: no `team_followup.csv` with resignations "
                "per team was provided. Add one (team_id, headcount_at_survey, voluntary_exits_12m) to set the "
                "survey against turnover, team by team.\n")
    frame, left_out = team_frame()
    heads, exits = sum(t["headcount"] for t in frame), sum(t["exits"] for t in frame)
    q = quartiles(frame)
    main = rate_ratio(frame, ["engagement"])
    eng = main["terms"]["engagement"]
    dims = [k for k in frame[0] if k.startswith("dim:")]
    by_dim = sorted(((k[4:], rate_ratio(frame, [k], per_sd=True)["terms"][k]) for k in dims), key=lambda t: t[1]["rr"])
    driver_top = top_driver()
    best = by_dim[0][1]
    leaders = [d for d, r in by_dim if r["rr"] <= best["high"]]       # inside the best one's interval
    part = rate_ratio(frame, ["engagement", "response_rate"])["terms"]["response_rate"]

    # the fitted rate across the range of team engagement, departments at their average mix
    b0, b1 = main["coef"][0], main["coef"][1]
    mix = [sum(t["department"] == d for t in frame) / len(frame) for d in sorted({t["department"] for t in frame})[1:]]
    base = b0 + sum(c * m for c, m in zip(main["coef"][2:], mix))
    curve = [(x / 100, math.exp(base + b1 * (x / 100) / PER)) for x in range(10, 96, 5)]
    viz.team_scatter(FIGURES / "07_team_engagement_vs_exits.svg",
                     [t["engagement"] for t in frame], [t["exits"] / t["headcount"] for t in frame],
                     [t["headcount"] for t in frame],
                     "Teams that score lower lose more people",
                     f"{len(frame)} teams: engagement at fieldwork against resignations in the next 12 months",
                     xlabel="team engagement index, favourable", ylabel="resigned within 12 months", curve=curve)
    viz.dot_plot_ci(FIGURES / "08_dimension_rate_ratios.svg", [d for d, _ in by_dim], [r["rr"] for _, r in by_dim],
                    [r["low"] for _, r in by_dim], [r["high"] for _, r in by_dim],
                    "Which team scores go with fewer resignations",
                    "Rate ratio per standard deviation of team score, departments held constant (1 = no link)",
                    reference=1.0, fmt=lambda v: f"{v:.2f}", xlabel="resignations, times the rate")

    top, bottom = q[3], q[0]
    md = [
        "## 4. Does the survey tell us who will leave? Only team by team",
        "",
        "The survey is confidential, so no answer can be traced to a person; resignations sit in the HRIS. The only "
        "honest join is the team: each team's scores at fieldwork against its resignations over the next twelve "
        f"months. **{len(frame)} teams** with at least {MIN_GROUP} respondents cover {heads:,} employees and "
        f"{exits} resignations ({exits / heads:.1%}); {left_out['teams']} smaller teams, {left_out['headcount']} "
        "people, are left out by the same rule that protects them everywhere else.",
        "",
        "![Team engagement against resignations](figures/07_team_engagement_vs_exits.svg)",
        "",
        md_table(["Teams by engagement", "Score range", "Teams", "Employees", "Resigned", "Rate"],
                 [[name, f"{r['low']:.0%}-{r['high']:.0%}", str(r["teams"]), f"{r['headcount']:,}", str(r["exits"]),
                   f"{r['rate']:.1%}"] for name, r in zip(["Lowest quarter", "Second", "Third", "Highest quarter"], q)],
                 align="lrrrrr"),
        "",
        f"**The lowest-scoring quarter of teams lost {bottom['rate']:.1%} of its people in a year; the highest, "
        f"{top['rate']:.1%}.** Every 10 points of team engagement go with **{eng['rr']:.2f} times** the resignation "
        f"rate (95% interval {eng['low']:.2f}-{eng['high']:.2f}, departments held constant).",
        "",
        "![Rate ratios by dimension](figures/08_dimension_rate_ratios.svg)",
        "",
        md_table(["Dimension", "Rate ratio per SD of team score", "95% interval", "p"],
                 [[d, f"{r['rr']:.2f}", f"{r['low']:.2f}-{r['high']:.2f}", "<0.001" if r["p"] < 0.001 else f"{r['p']:.3f}"]
                  for d, r in by_dim], align="lrrr"),
        "",
        (f"**{by_dim[0][0]} is the team score most tied to keeping people**: a team one standard deviation higher "
         f"on it loses people at {by_dim[0][1]['rr']:.2f} times the rate. " if len(leaders) == 1 else
         f"**{', '.join(leaders[:-1])} and {leaders[-1]} lead, and cannot be told apart**: a team one standard "
         f"deviation higher on any of them loses people at {by_dim[0][1]['rr']:.2f} to "
         f"{by_dim[len(leaders) - 1][1]['rr']:.2f} times the rate, with intervals that overlap. ")
        + (f"{driver_top} is also the strongest driver of engagement in section 2."
           if driver_top in leaders else
           f"Section 2 found {driver_top} the strongest driver of engagement: what makes people engaged and what "
           "keeps them are related but not the same question.")
        + (" Pay & Benefits, the loudest theme in the comments, has the weakest link to who stays."
           if by_dim[-1][0] == "Pay & Benefits" else "")
        + " Each dimension is read on its own and the eight move together, so the order matters more than the "
        "exact sizes.",
        "",
        ("**Participation is a signal too.** " if part["high"] < 1 else "**Participation.** ")
        + f"With engagement held constant, every 10 points of response rate go with "
        f"{part['rr']:.2f} times the resignation rate (95% interval {part['low']:.2f}-{part['high']:.2f}): "
        + ("teams that stay silent lose more people, which is what the non-response analysis in section 1 warned "
           "about. A low response rate is worth a conversation on its own."
           if part["high"] < 1 else
           "no clear link once engagement is known."),
        "",
        "**What it does not say.** These are team averages. They show where to look and how much a team's climate "
        "is worth in people kept; they say nothing about which individuals will leave, and nothing here should be "
        "used to guess. The survey's confidentiality is what makes people answer honestly; spending it on a "
        "prediction would cost the next survey its answers.",
        "",
        (f"*Counts per team are more variable than a Poisson model allows (dispersion {main['dispersion']:.2f}); "
         "the intervals are widened accordingly.*" if main["dispersion"] > 1 else
         f"*Team counts are no more variable than a Poisson model allows (dispersion {main['dispersion']:.2f}), "
         "so the intervals need no widening.*"),
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
