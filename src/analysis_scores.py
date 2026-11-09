"""
Module 1 - Participation and scores.

Before any result is quoted, two questions have to be answered: who actually
answered, and how much of what we are looking at could be noise. Only then do
the scores mean anything.

Order of business:
  1. response rate, and who is missing from it
  2. the headline - engagement index and eNPS, with intervals
  3. dimension scores, ranked, with confidence intervals
  4. the same scores by department, compared descriptively
  5. team-level spread, and the confidentiality rule that governs it
"""

from __future__ import annotations

import viz
from statlib import bootstrap_mean_interval, quantile
from surveylib import (DIMENSION_ORDER, FIELD_WINDOW, FIGURES, MIN_GROUP, PRIVATE_MODE, SURVEY_NAME,
                       dimension_score, driver_items, enps, group_by,
                       load_instrument, load_responses, load_teams, md_table, md_text, outcome_items,
                       pct, reportable, representation_gap, respondent_favourable,
                       respondents, response_rate, segment_comparison)


def enps_verdict(net: dict) -> str:
    """Say what the number means, in the register a leadership team reads in."""
    if not net["n"]:
        return "eNPS is unavailable because no respondent supplied a valid 0-10 rating."
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
    rate_low, rate_high = bootstrap_mean_interval(
        [1.0 if row["responded"] else 0.0 for row in rows], seed=13,
        clusters=[row.get("team_id") for row in rows])

    # ---- 1. participation ---------------------------------------------
    by_department = response_rate(rows, "department")
    visible_rates = [d for d in by_department if not d.get("suppressed")]
    worst = min(visible_rates, key=lambda d: d["rate"]) if visible_rates else None
    best = max(visible_rates, key=lambda d: d["rate"]) if visible_rates else None
    gaps = [g for g in representation_gap(rows, "department")
            if not g.get("suppressed")]
    under = gaps[0] if gaps else None

    if visible_rates:
        participation_summary = (
            f"Response rate runs from **{pct(worst['rate'])} in {md_text(worst['segment'])}** to "
            f"**{pct(best['rate'])} in {md_text(best['segment'])}**."
        )
        department_table = md_table(
            ["Department", "Invited", "Responded", "Rate", "Share gap"],
            [[d["segment"], f"{d['invited']:,}", f"{d['responded']:,}", pct(d["rate"]),
              f"{next(g['gap_pp'] for g in gaps if g['segment'] == d['segment']):+.1f} pp"]
             for d in sorted(visible_rates, key=lambda d: d["rate"])], align="lrrrr")
        under_summary = (f"**{md_text(under['segment'])}** is the most under-represented reportable "
                         f"group at **{under['gap_pp']:+.1f} pp**.")
    else:
        participation_summary = (f"Department-level response rates are withheld because no "
                                 f"department has at least {MIN_GROUP} respondents.")
        department_table = "Department table withheld at the reporting threshold."
    if under:
        under_summary = (f"**{md_text(under['segment'])}** is the most under-represented reportable "
                         f"group at **{under['gap_pp']:+.1f} pp**.")
    else:
        under_summary = "Department representation gaps are withheld at the reporting threshold."

    shift = [r for r in rows if r["shift_worker"]]
    shift_responded = sum(1 for r in shift if r["responded"])
    shift_rate = shift_responded / len(shift) if shift else None
    desk = [r for r in rows if not r["shift_worker"]]
    desk_responded = sum(1 for r in desk if r["responded"])
    desk_rate = desk_responded / len(desk) if desk else None
    if PRIVATE_MODE and min(shift_responded, desk_responded, len(shift), len(desk)) < MIN_GROUP:
        shift_summary = "Shift-worker and desk-worker response rates are withheld at the reporting threshold."
    elif shift_rate is not None and desk_rate is not None:
        shift_summary = (f"Shift workers answered at **{pct(shift_rate)}** against "
                         f"**{pct(desk_rate)}** for everyone else.")
    else:
        shift_summary = "Work-model response-rate comparison is unavailable."

    # ---- 2. headline ---------------------------------------------------
    engagement_rows = [(r, respondent_favourable(r, outcome)) for r in answered]
    engagement_rows = [(r, value) for r, value in engagement_rows if value is not None]
    engagement_by_person = [value for _row, value in engagement_rows]
    engagement_fav = sum(engagement_by_person) / len(engagement_by_person)
    eng_low, eng_high = bootstrap_mean_interval(
        engagement_by_person, clusters=[r.get("team_id") for r, _value in engagement_rows])
    n_out = len(engagement_by_person)
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
    department_counts = {dept: sum(1 for r in answered if r["department"] == dept)
                         for dept in {r["department"] for r in answered}}
    departments = sorted(dept for dept, count in department_counts.items() if count >= MIN_GROUP)
    matrix = []
    flagged = []
    for dim in DIMENSION_ORDER:
        entries = {entry["segment"]: entry for entry in
                   segment_comparison(answered, "department", items_by_dim[dim])}
        row_values = []
        for dept in departments:
            entry = entries[dept]
            if entry["suppressed"]:
                row_values.append(float("nan"))
                continue
            row_values.append(entry["favourable"])
            if entry["vs_company"] < 0:
                flagged.append((entry["segment"], dim, entry["favourable"],
                                entry["vs_company"], entry["ci_low"], entry["ci_high"]))
        matrix.append(row_values)

    viz.heatmap(
        FIGURES / "02_dimension_by_department.svg",
        DIMENSION_ORDER, departments, matrix,
        "Favourable score by dimension and department",
        "Each respondent contributes one mean score; no group below "
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
        person_rates = [value for r in group
                        if (value := respondent_favourable(r, outcome)) is not None]
        rate = sum(person_rates) / len(person_rates)
        low, high = bootstrap_mean_interval(person_rates, seed=23)
        team_scores.append({"team_id": team_id, "n": len(person_rates), "favourable": rate,
                            "ci_low": low, "ci_high": high,
                            "department": teams[team_id]["department"]})

    stable = [t for t in team_scores if t["n"] >= 15]
    stable_range = stable or team_scores
    values = [t["favourable"] for t in stable_range]
    p10, p90 = (quantile(values, 0.10), quantile(values, 0.90)) if values else (float("nan"), float("nan"))

    viz.histogram(
        FIGURES / "03_team_distribution.svg", values,
        "How much teams differ from each other",
        f"Engagement index favourable score, {len(stable_range)} teams with at least "
        f"{15 if stable else MIN_GROUP} respondents",
        xlabel="team engagement score", ylabel="teams",
        markers=[(engagement_fav, "company", viz.SECONDARY),
                 (p10, "bottom decile", viz.ORANGE)])

    # An exploratory descriptive screen only: intervals are not adjusted for
    # comparing many teams, and the company mean includes each team's members.
    below = sorted((t for t in stable_range if t["ci_high"] < engagement_fav),
                   key=lambda t: t["favourable"])
    bottom = below[:10]
    if stable_range:
        team_floor = 15 if stable else MIN_GROUP
        team_basis = (f"teams with at least {team_floor} respondents" if stable else
                      f"reportable teams with at least {team_floor} respondents")
        team_spread = (
            f"Across {len(stable_range)} {team_basis}, respondent-level engagement ranges "
            f"from **{pct(min(t['favourable'] for t in stable_range))}** to "
            f"**{pct(max(t['favourable'] for t in stable_range))}**. The bottom decile sits at "
            f"**{pct(p10)}** and the top at **{pct(p90)}** - a "
            f"**{(p90 - p10) * 100:.0f} percentage point** spread. These are descriptive "
            "signals for follow-up, not evidence that a manager or team caused the difference."
        )
    else:
        team_spread = (f"No team has at least {MIN_GROUP} respondents, so team-level scores "
                       "are withheld.")
    if PRIVATE_MODE:
        team_detail = "Team-level labels and row-level comparisons are withheld in local mode."
    else:
        team_detail = (
            f"**{len(below)} teams have a 95% within-team bootstrap interval below the observed "
            "company mean. This is an exploratory screen, not a significance test: team "
            "comparisons are not adjusted for multiplicity and the company mean includes each "
            "team.** The ten lowest descriptive results:"
            + "\n\n" + md_table(
                ["Team", "Department", "Respondents", "Engagement index", "95% bootstrap interval"],
                [[t["team_id"], t["department"], t["n"], pct(t["favourable"]),
                  f"{pct(t['ci_low'])}-{pct(t['ci_high'])}"] for t in bottom], align="llrrr")
        )

    # ---- narrative ------------------------------------------------------
    md = [
        f"## 1. Participation and scores",
        "",
        f"**{md_text(SURVEY_NAME)}** ran {md_text(FIELD_WINDOW)}. **{len(answered):,} of {len(rows):,}** "
        f"employees responded - **{pct(overall_rate, 1)}** "
        f"(95% bootstrap interval {pct(rate_low, 1)}-{pct(rate_high, 1)}).",
        "",
        "### Who answered, and who did not",
        "",
        f"{participation_summary} {shift_summary} That gap is not an administrative detail: "
        "it affects whose experience the results describe.",
        "",
        department_table,
        "",
        f"{under_summary} Response-rate differences show coverage gaps, but they do not tell us "
        "what non-respondents would have said. Interpret the company score as a description "
        "of respondents, not the full workforce.",
        "",
        "### The headline",
        "",
        md_table(["Measure", "Result", "Read"],
                 [["Engagement index",
                   f"**{pct(engagement_fav)} favourable**",
                   f"95% bootstrap interval {pct(eng_low, 1)}-{pct(eng_high, 1)}, "
                   f"{n_out:,} respondents"],
                  ["eNPS", f"**{net['enps']:+.0f}**" if net["n"] else "Not available",
                   (f"{pct(net['promoters'])} promoters, {pct(net['passives'])} passives, "
                    f"{pct(net['detractors'])} detractors") if net["n"] else "No valid ratings"],
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
        md_table(["Dimension", "Favourable", "95% bootstrap interval",
                  "Mean (1-5)", "Respondents", "Item answers"],
                 [[dim, f"**{pct(s['favourable'])}**",
                   f"{pct(s['ci_low'])}-{pct(s['ci_high'])}", f"{s['mean']:.2f}",
                   f"{s['n_respondents']:,}", f"{s['n_answers']:,}"] for dim, s in ranked],
                 align="lrrrrr"),
        "",
        f"The observed spread is **{ranked[0][0]}** at {pct(ranked[0][1]['favourable'])} "
        f"to **{ranked[-1][0]}** at {pct(ranked[-1][1]['favourable'])}. The bootstrap "
        "intervals reflect sampling variation under the reported bootstrap unit; overlapping intervals do not "
        "support a firm ranking between dimensions.",
        "",
        "### Where it differs by department",
        "",
        "![Dimension by department](figures/02_dimension_by_department.svg)",
        "",
        "Cells show descriptive respondent-level means. The table lists the largest observed "
        "gaps below the company mean; no significance claims are made for these multiple cuts:",
        "",
        md_table(["Department", "Dimension", "Favourable", "vs company mean"],
                 [[dept, dim, pct(rate), f"{gap * 100:+.1f} pp"]
                  for dept, dim, rate, gap, _low, _high in flagged[:10]], align="llrr"),
        "",
        "### The company average hides the teams",
        "",
        "![Team distribution](figures/03_team_distribution.svg)",
        "",
        team_spread,
        "",
        f"**{suppressed} teams are suppressed** because they have fewer than "
        f"{MIN_GROUP} respondents.",
        "",
        team_detail,
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
