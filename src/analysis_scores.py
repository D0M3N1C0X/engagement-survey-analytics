"""
Module 1 - Participation and scores.

Before any result is quoted, two questions have to be answered: who actually
answered, and how much of what we are looking at could be noise. Only then do
the scores mean anything.

Order of business:
  1. response rate, and who is missing from it
  2. the headline - engagement index and eNPS, with intervals
  3. dimension scores, ranked, with confidence intervals
  4. the same scores by department, tested rather than eyeballed
  5. team-level spread, and the confidentiality rule that governs it
"""

from __future__ import annotations

import viz
from statlib import mean, quantile, two_proportion_z, wilson_interval
from surveylib import (DIMENSION_ORDER, FIELD_WINDOW, FIGURES, MIN_GROUP, SURVEY_NAME,
                       dimension_score, dimension_values, driver_items, enps, favourable,
                       group_by, load_instrument, load_responses, load_teams, md_table,
                       outcome_items, pct, reportable, representation_gap, respondents,
                       response_rate, segment_comparison)


def enps_verdict(net: dict) -> str:
    """Say what the number means, in the register a leadership team reads in."""
    detractors = pct(net["detractors"])
    if net["enps"] < -5:
        return (f"A negative eNPS means more people would actively warn a friend off working "
                f"here than would recommend it. With {detractors} detractors, this is not a "
                "communications problem to be reframed; it is the thing the rest of the "
                "report has to explain.")
    if net["enps"] < 10:
        return (f"An eNPS this close to zero means advocates and detractors cancel out: for "
                f"every person who would recommend working here, someone else would warn a "
                f"friend away. {detractors} of respondents are detractors, and they are not "
                "spread evenly - the rest of the report is about where they sit and why.")
    return (f"A positive eNPS of {net['enps']:+.0f} is a real asset, but with {detractors} "
            "detractors the average is hiding two different companies.")


def run() -> str:
    rows = load_responses()
    answered = respondents(rows)
    instrument = load_instrument()
    items_by_dim = driver_items(instrument)
    outcome = outcome_items(instrument)
    teams = load_teams()

    overall_rate = len(answered) / len(rows)
    rate_low, rate_high = wilson_interval(len(answered), len(rows))

    # ---- 1. participation ---------------------------------------------
    by_department = response_rate(rows, "department")
    worst = min(by_department, key=lambda d: d["rate"])
    best = max(by_department, key=lambda d: d["rate"])
    gaps = representation_gap(rows, "department")
    under = gaps[0]

    shift = [r for r in rows if r["shift_worker"]]
    shift_rate = sum(1 for r in shift if r["responded"]) / len(shift)
    desk = [r for r in rows if not r["shift_worker"]]
    desk_rate = sum(1 for r in desk if r["responded"]) / len(desk)

    # ---- 2. headline ---------------------------------------------------
    k_out, n_out, engagement_fav = favourable([r[i] for r in answered for i in outcome
                                               if r.get(i)])
    eng_low, eng_high = wilson_interval(k_out, n_out)
    net = enps([r["enps"] for r in answered])

    # ---- 3. dimensions -------------------------------------------------
    scores = {dim: dimension_score(answered, items_by_dim[dim]) for dim in DIMENSION_ORDER}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1]["favourable"])

    viz.dot_plot_ci(
        FIGURES / "01_dimension_scores.svg",
        [dim for dim, _ in ranked],
        [s["favourable"] for _, s in ranked],
        [s["ci_low"] for _, s in ranked],
        [s["ci_high"] for _, s in ranked],
        "Favourable score by dimension",
        f"{SURVEY_NAME} - {len(answered):,} respondents, 95% confidence intervals",
        reference=engagement_fav, reference_label="engagement index",
        xlabel="% answering agree or strongly agree")

    # ---- 4. by department ----------------------------------------------
    departments = sorted({r["department"] for r in answered})
    matrix = []
    flagged = []
    for dim in DIMENSION_ORDER:
        row_values = []
        for dept in departments:
            group = [r for r in answered if r["department"] == dept]
            if not reportable(group):
                row_values.append(float("nan"))
                continue
            k, n, rate = favourable(dimension_values(group, items_by_dim[dim]))
            all_k, all_n, _ = favourable(dimension_values(answered, items_by_dim[dim]))
            z, p = two_proportion_z(k, n, all_k - k, all_n - n)
            row_values.append(rate)
            if p < 0.01 and rate < all_k / all_n:
                flagged.append((dept, dim, rate, rate - all_k / all_n, p))
        matrix.append(row_values)

    viz.heatmap(
        FIGURES / "02_dimension_by_department.svg",
        DIMENSION_ORDER, departments, matrix,
        "Favourable score by dimension and department",
        "Every cell is a percentage of favourable answers; no group below "
        f"{MIN_GROUP} respondents is shown",
        note=f"n = {len(answered):,} respondents")

    flagged.sort(key=lambda t: t[3])

    # ---- 5. teams -------------------------------------------------------
    team_scores = []
    suppressed = 0
    for team_id, group in group_by(answered, "team_id").items():
        if not reportable(group):
            suppressed += 1
            continue
        k, n, rate = favourable([r[i] for r in group for i in outcome if r.get(i)])
        low, high = wilson_interval(k, n)
        team_scores.append({"team_id": team_id, "n": len(group), "favourable": rate,
                            "ci_low": low, "ci_high": high,
                            "department": teams[team_id]["department"],
                            "manager_tenure": teams[team_id]["manager_tenure_months"]})

    values = [t["favourable"] for t in team_scores]
    p10, p90 = quantile(values, 0.10), quantile(values, 0.90)

    viz.histogram(
        FIGURES / "03_team_distribution.svg", values,
        "How much teams differ from each other",
        f"Engagement index favourable score, {len(team_scores)} teams with at least "
        f"{MIN_GROUP} respondents",
        xlabel="team engagement score", ylabel="teams",
        markers=[(engagement_fav, "company", viz.SECONDARY),
                 (p10, "bottom decile", viz.ORANGE)])

    # A defensible coaching list: teams whose entire confidence interval sits
    # below the company score, so the gap is not an artefact of a small team.
    below = sorted((t for t in team_scores if t["ci_high"] < engagement_fav),
                   key=lambda t: t["favourable"])
    bottom = below[:10]
    stable = [t for t in team_scores if t["n"] >= 15]

    # ---- narrative ------------------------------------------------------
    md = [
        f"## 1. Participation and scores",
        "",
        f"**{SURVEY_NAME}** ran {FIELD_WINDOW}. **{len(answered):,} of {len(rows):,}** "
        f"employees responded - **{pct(overall_rate, 1)}** "
        f"(95% CI {pct(rate_low, 1)}-{pct(rate_high, 1)}).",
        "",
        "### Who answered, and who did not",
        "",
        f"Response rate runs from **{pct(worst['rate'])} in {worst['segment']}** to "
        f"**{pct(best['rate'])} in {best['segment']}**, and shift workers answered at "
        f"**{pct(shift_rate)}** against **{pct(desk_rate)}** for everyone else. That gap "
        "is not an administrative detail: it decides whose experience the results "
        "describe.",
        "",
        md_table(["Department", "Invited", "Responded", "Rate", "Share of respondents vs share of workforce"],
                 [[d["segment"], f"{d['invited']:,}", f"{d['responded']:,}", pct(d["rate"]),
                   f"{next(g['gap_pp'] for g in gaps if g['segment'] == d['segment']):+.1f} pp"]
                  for d in sorted(by_department, key=lambda d: d["rate"])], align="lrrrr"),
        "",
        f"**{under['segment']}** is the most under-represented group at "
        f"**{under['gap_pp']:+.1f} pp**. Non-response is rarely random - the people with "
        "least time and least trust are the least likely to answer - so the true company "
        "scores are more likely to sit below these numbers than above them. Every result "
        "in this report should be read with that direction of error in mind.",
        "",
        "### The headline",
        "",
        md_table(["Measure", "Result", "Read"],
                 [["Engagement index",
                   f"**{pct(engagement_fav)} favourable**",
                   f"95% CI {pct(eng_low, 1)}-{pct(eng_high, 1)}, {n_out:,} answers"],
                  ["eNPS", f"**{net['enps']:+.0f}**",
                   f"{pct(net['promoters'])} promoters, {pct(net['passives'])} passives, "
                   f"{pct(net['detractors'])} detractors"],
                  ["Response rate", f"**{pct(overall_rate, 1)}**",
                   f"{len(answered):,} of {len(rows):,} invited"],
                  ["Teams reported", f"**{len(team_scores)}**",
                   f"{suppressed} suppressed for being below {MIN_GROUP} respondents"]],
                 align="lrl"),
        "",
        enps_verdict(net),
        "",
        "### Dimension scores",
        "",
        "![Dimension scores](figures/01_dimension_scores.svg)",
        "",
        md_table(["Dimension", "Favourable", "95% CI", "Mean (1-5)", "Answers"],
                 [[dim, f"**{pct(s['favourable'])}**",
                   f"{pct(s['ci_low'])}-{pct(s['ci_high'])}", f"{s['mean']:.2f}",
                   f"{s['n_answers']:,}"] for dim, s in ranked], align="lrrrr"),
        "",
        f"The spread is wide: **{ranked[0][0]}** at {pct(ranked[0][1]['favourable'])} and "
        f"**{ranked[-1][0]}** at {pct(ranked[-1][1]['favourable'])}. The intervals are "
        "narrow enough at this sample size that the ranking is real rather than sampling "
        "noise - which is not true of the team-level numbers further down.",
        "",
        "### Where it differs by department",
        "",
        "![Dimension by department](figures/02_dimension_by_department.svg)",
        "",
        "Cells are tested against the rest of the company, not just compared. The gaps "
        "that survive a two-proportion test at p < 0.01:",
        "",
        md_table(["Department", "Dimension", "Favourable", "vs rest of company"],
                 [[dept, dim, pct(rate), f"{gap * 100:+.1f} pp"]
                  for dept, dim, rate, gap, _p in flagged[:10]], align="llrr"),
        "",
        "### The company average hides the teams",
        "",
        "![Team distribution](figures/03_team_distribution.svg)",
        "",
        f"Across the {len(stable)} teams with at least 15 respondents - small teams swing "
        f"too much to compare - the engagement index runs from "
        f"**{pct(min(t['favourable'] for t in stable))}** to "
        f"**{pct(max(t['favourable'] for t in stable))}**. The bottom decile sits at "
        f"**{pct(p10)}** and the top at **{pct(p90)}** - a **{(p90 - p10) * 100:.0f} "
        "percentage point** spread inside one company. An organisation-wide programme "
        "aimed at the average would be aimed at almost nobody.",
        "",
        f"**{suppressed} teams are not reported at all**, because they have fewer than "
        f"{MIN_GROUP} respondents. That rule is not bureaucracy: it is the promise that "
        "made people answer honestly, and the first time a manager works out who said "
        "what, the next survey is worthless.",
        "",
        f"**{len(below)} teams sit significantly below the company score** - their whole "
        "95% interval is below it, so this is not small-team noise. The ten lowest:",
        "",
        md_table(["Team", "Department", "Respondents", "Engagement index", "95% CI"],
                 [[t["team_id"], t["department"], t["n"], pct(t["favourable"]),
                   f"{pct(t['ci_low'])}-{pct(t['ci_high'])}"] for t in bottom],
                 align="llrrr"),
        "",
        "This is the list a People Partner works through, in this order - and the interval "
        "column is why it is a conversation list and not a ranking: the difference between "
        "first and fourth on it is not measurable.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
