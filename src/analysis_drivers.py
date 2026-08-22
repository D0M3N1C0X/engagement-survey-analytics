"""
Module 2 - Key driver analysis.

Every survey produces a list of things people are unhappy about. The useful
question is different: of the things people are unhappy about, which ones
actually move engagement? Those are the two axes of the priority map - impact
and performance - and only one quadrant deserves a budget.

Method note. Survey drivers are heavily correlated with one another, and
ordinary regression coefficients handle that badly: they assign shared
variance to whichever driver wins a near-tie, and the ranking then moves
around from one sample to the next. This module uses Johnson's relative weight
analysis (implemented in statlib.py) and checks the ranking with a bootstrap,
so the report can say which parts of the order are real and which are not.
"""

from __future__ import annotations

import random

import viz
from statlib import mean, pearson, quantile, relative_weights, ols_standardised
from surveylib import (DIMENSION_ORDER, FIGURES, dimension_score, driver_items,
                       engagement_index, favourable, group_by, load_instrument,
                       load_responses, md_table, outcome_items, pct,
                       respondent_dimension_means, respondents)

BOOTSTRAP_REPS = 120
BOOTSTRAP_SEED = 11


def build_matrix(answered: list[dict], items_by_dim: dict, outcome: list[str]
                 ) -> tuple[list[list[float]], list[float]]:
    """One row per respondent: eight dimension means, plus the engagement index."""
    columns: list[list[float]] = [[] for _ in DIMENSION_ORDER]
    y: list[float] = []
    for row in answered:
        dims = respondent_dimension_means(row, items_by_dim)
        index = engagement_index(row, outcome)
        if index is None or len(dims) < len(DIMENSION_ORDER):
            continue
        for i, dim in enumerate(DIMENSION_ORDER):
            columns[i].append(dims[dim])
        y.append(index)
    return columns, y


def bootstrap_weights(columns: list[list[float]], y: list[float]) -> list[list[float]]:
    """Relative weights recomputed on resampled respondents, to test the ranking."""
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(y)
    draws = []
    for _ in range(BOOTSTRAP_REPS):
        idx = [rng.randrange(n) for _ in range(n)]
        sample_cols = [[col[i] for i in idx] for col in columns]
        sample_y = [y[i] for i in idx]
        weights, _r2 = relative_weights(sample_cols, sample_y)
        draws.append(weights)
    return draws


def run() -> str:
    rows = load_responses()
    answered = respondents(rows)
    instrument = load_instrument()
    items_by_dim = driver_items(instrument)
    outcome = outcome_items(instrument)

    columns, y = build_matrix(answered, items_by_dim, outcome)
    weights, r2 = relative_weights(columns, y)
    betas, r2_ols = ols_standardised(columns, y)
    correlations = [pearson(col, y) for col in columns]

    scores = {dim: dimension_score(answered, items_by_dim[dim])["favourable"]
              for dim in DIMENSION_ORDER}

    draws = bootstrap_weights(columns, y)
    intervals = []
    for i in range(len(DIMENSION_ORDER)):
        column = [d[i] for d in draws]
        intervals.append((quantile(column, 0.05), quantile(column, 0.95)))
    rank_ranges = []
    for i in range(len(DIMENSION_ORDER)):
        ranks = [sorted(range(len(d)), key=lambda j: -d[j]).index(i) + 1 for d in draws]
        rank_ranges.append((min(ranks), max(ranks)))

    table = sorted(
        [{"dimension": dim, "weight": weights[i], "beta": betas[i], "r": correlations[i],
          "favourable": scores[dim], "ci": intervals[i], "rank": rank_ranges[i]}
         for i, dim in enumerate(DIMENSION_ORDER)],
        key=lambda d: -d["weight"])

    mean_weight = mean([t["weight"] for t in table])
    mean_score = mean([t["favourable"] for t in table])
    priorities = [t for t in table if t["weight"] > mean_weight and t["favourable"] < mean_score]

    viz.quadrant(
        FIGURES / "04_impact_vs_performance.svg",
        [t["dimension"] for t in table],
        [t["weight"] for t in table],
        [t["favourable"] for t in table],
        "What matters against what scores well",
        f"Impact is each driver's share of explained variance in engagement "
        f"(relative weight analysis, R² = {r2:.2f})",
        xlabel="impact - share of explained variance",
        ylabel="performance - favourable score")

    # Observed contrast rather than a model extrapolation: what separates the
    # teams that score well on the top driver from the teams that do not.
    top = table[0]["dimension"]
    team_rows = []
    for team_id, group in group_by(answered, "team_id").items():
        if len(group) < 10:
            continue
        _k, _n, driver_rate = favourable([r[i] for r in group
                                          for i in items_by_dim[top] if r.get(i)])
        _k2, _n2, engagement = favourable([r[i] for r in group for i in outcome if r.get(i)])
        team_rows.append((driver_rate, engagement))
    team_rows.sort(key=lambda t: t[0])
    quartile = max(1, len(team_rows) // 4)
    bottom_q = mean([e for _d, e in team_rows[:quartile]])
    top_q = mean([e for _d, e in team_rows[-quartile:]])

    md = [
        "## 2. What actually drives engagement",
        "",
        f"Eight dimensions explain **{r2:.0%}** of the variation in the engagement index "
        f"across {len(y):,} respondents. Below, *impact* is each dimension's share of that "
        "explained variance, and *performance* is its favourable score.",
        "",
        "![Impact against performance](figures/04_impact_vs_performance.svg)",
        "",
        md_table(["Dimension", "Impact", "90% bootstrap range", "Rank range",
                  "Favourable", "Correlation", "Std. beta"],
                 [[t["dimension"], f"**{t['weight']:.0%}**",
                   f"{t['ci'][0]:.0%}-{t['ci'][1]:.0%}",
                   f"{t['rank'][0]}-{t['rank'][1]}" if t["rank"][0] != t["rank"][1]
                   else f"{t['rank'][0]}",
                   pct(t["favourable"]), f"{t['r']:.2f}", f"{t['beta']:+.2f}"]
                  for t in table], align="lrrrrrr"),
        "",
        f"**{table[0]['dimension']}** carries **{table[0]['weight']:.0%}** of the explained "
        f"variance, more than the bottom four dimensions combined "
        f"({sum(t['weight'] for t in table[-4:]):.0%}). "
        f"**{table[-1]['dimension']}** carries **{table[-1]['weight']:.0%}** - it is not "
        "unimportant to people, it is simply not what separates an engaged employee from a "
        "disengaged one here.",
        "",
        "### How much of this ranking can we trust",
        "",
        f"The weights were recomputed on **{BOOTSTRAP_REPS} bootstrap resamples** of the "
        "respondent pool. The rank range column shows where each dimension landed across "
        "those runs.",
        "",
        stability_note(table),
        "",
        "### The priority quadrant",
        "",
        f"High impact and a low score is the only quadrant that earns investment: "
        + ", ".join(f"**{t['dimension']}** ({t['weight']:.0%} impact, "
                    f"{pct(t['favourable'])} favourable)" for t in priorities) + ".",
        "",
        f"Compare that with **Pay & Benefits** at {pct(scores['Pay & Benefits'])} favourable "
        f"but only {[t['weight'] for t in table if t['dimension'] == 'Pay & Benefits'][0]:.0%} "
        "impact. Pay is the loudest complaint in the free text and one of the lowest scores "
        "in the survey, and it still is not what moves engagement in this company. A pay "
        "review would buy goodwill; it would not buy engagement. That is an uncomfortable "
        "finding to present, which is exactly why it needs the bootstrap behind it.",
        "",
        "### What the gap is worth",
        "",
        f"Rather than extrapolate from the model, compare like with like: among teams with "
        f"at least 10 respondents, those in the **top quartile on {top}** score "
        f"**{pct(top_q)}** on the engagement index, against **{pct(bottom_q)}** for the "
        f"bottom quartile - a **{(top_q - bottom_q) * 100:.0f} percentage point** difference. "
        "That is an observed contrast between teams, not a promise about what a programme "
        "would deliver; teams differ in more ways than one dimension. It does say that the "
        "difference between a good and a poor experience of "
        f"{top.lower()} is visible at the size that matters.",
        "",
    ]
    return "\n".join(md)


def stability_note(table: list[dict]) -> str:
    """Describe what the bootstrap actually showed, rather than assuming it was clean."""
    parts = []
    # Dimensions already described as the leader or the second tier are not
    # listed again as unstable - that would say two things about one name.
    unstable = [t for t in table[3:] if t["rank"][1] - t["rank"][0] >= 2]
    top = table[0]
    if top["rank"] == (1, 1):
        parts.append(f"**{top['dimension']}** finished first in every single resample, so "
                     "the headline of this analysis is not a sampling artefact.")
    elif top["rank"][1] <= 2:
        parts.append(f"**{top['dimension']}** finished first or second in every resample.")
    else:
        parts.append("Even the top position moves between runs, so treat the leading "
                     "dimensions as a group rather than a ranking.")

    tier = table[1:3]
    ceiling = max(t["rank"][1] for t in tier)
    if ceiling <= 4:
        names = " and ".join(f"**{t['dimension']}**" for t in tier)
        parts.append(f"{names} never fell below {ceiling}th, so they are the second tier - "
                     "but they trade places with each other, and arguing about which of them "
                     "is second is arguing about noise.")

    if unstable:
        named = ", ".join(f"**{t['dimension']}**" for t in unstable[:3])
        rest = f" and {len(unstable) - 3} others" if len(unstable) > 3 else ""
        parts.append(f"{named}{rest} move by two or more places between resamples. Their "
                     "order relative to each other is not a finding, and a read-out that "
                     "calls one of them 'the fifth priority' is reading noise.")
    else:
        parts.append("No dimension moved by more than one place, which is unusually stable "
                     "for a survey of this size.")
    return " ".join(parts)


if __name__ == "__main__":
    print(run())
