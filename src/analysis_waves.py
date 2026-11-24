"""
Module 5 - Did the action plan work? Two waves, and the trap between them.

A year after the first survey, half of the weakest teams on Manager Support had a manager-support action
plan, drawn at random from the eligible teams. The obvious read, comparing those teams before and after, is
the wrong one: teams chosen because they scored low were partly unlucky the first time, and score better the
second time with nothing done. That is regression to the mean, and it is why the eligible teams that did not
get the plan are the comparison that matters. The estimate is the difference in differences, with an interval
that resamples teams; in this synthetic data it can be checked against the true effect.

Teams are compared, not people: the survey is anonymous, and nobody is followed from one wave to the next.
"""

from __future__ import annotations

import csv
import random

import viz
from statlib import mean, quantile
from surveylib import (DATA, FIGURES, MIN_GROUP, driver_items, load_instrument, md_table, outcome_items,
                       respondent_favourable)

WAVE2 = DATA / "survey_responses_wave2.csv"
ACTIONS = DATA / "team_actions.csv"
TRUTH = DATA / "action_truth.csv"
REPS, SEED = 2000, 41
DIMENSION = "Manager Support"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def team_scores(path, items_by_name: dict[str, list[str]]) -> dict[str, dict]:
    """Per team: respondents, invitees and the favourable score of each named item set, from one wave's file."""
    by_team: dict[str, list[dict]] = {}
    for r in read(path):
        by_team.setdefault(r["team_id"], []).append(r)
    out = {}
    for team, rows in by_team.items():
        answered = [{k: (int(v) if v.strip().isdigit() else None) for k, v in r.items() if k in sum(items_by_name.values(), [])}
                    for r in rows if r["responded"].strip() == "1"]
        entry = {"invited": len(rows), "respondents": len(answered)}
        for name, items in items_by_name.items():
            shares = [s for a in answered if (s := respondent_favourable(a, items)) is not None]
            entry[name] = mean(shares) if shares else None
        out[team] = entry
    return out


def did(action: list[dict], comparison: list[dict], key: str) -> tuple[float, float, float]:
    """Difference in differences of team means, with a percentile interval resampling teams in each group."""
    change = lambda teams: mean([t[key][1] - t[key][0] for t in teams])
    estimate = change(action) - change(comparison)
    rng = random.Random(SEED)
    draws = sorted(change(rng.choices(action, k=len(action))) - change(rng.choices(comparison, k=len(comparison)))
                   for _ in range(REPS))
    return estimate, quantile(draws, 0.025), quantile(draws, 0.975)


def run() -> str:
    if not (WAVE2.exists() and ACTIONS.exists()):
        return ("## 5. Did the action plan work?\n\nSkipped: no second wave (`survey_responses_wave2.csv`) and "
                "action table (`team_actions.csv`) were provided.\n")
    instrument = load_instrument()
    sets = {DIMENSION: driver_items(instrument)[DIMENSION], "engagement": outcome_items(instrument)}
    w1, w2 = team_scores(DATA / "survey_responses.csv", sets), team_scores(WAVE2, sets)
    actions = {r["team_id"]: r for r in read(ACTIONS)}
    teams = []
    for team, a in actions.items():
        if team in w1 and team in w2 and w1[team]["respondents"] >= MIN_GROUP and w2[team]["respondents"] >= MIN_GROUP:
            group = "action" if a["action"] == "1" else "comparison" if a["eligible"] == "1" else "rest"
            teams.append({"team": team, "group": group,
                          DIMENSION: (w1[team][DIMENSION], w2[team][DIMENSION]),
                          "engagement": (w1[team]["engagement"], w2[team]["engagement"]),
                          "rate": (w1[team]["respondents"] / w1[team]["invited"], w2[team]["respondents"] / w2[team]["invited"])})
    groups = {g: [t for t in teams if t["group"] == g] for g in ("action", "comparison", "rest")}
    avg = lambda g, key, wave: mean([t[key][wave] for t in groups[g]])
    naive = avg("action", DIMENSION, 1) - avg("action", DIMENSION, 0)
    rtm = avg("comparison", DIMENSION, 1) - avg("comparison", DIMENSION, 0)
    est, lo, hi = did(groups["action"], groups["comparison"], DIMENSION)
    e_est, e_lo, e_hi = did(groups["action"], groups["comparison"], "engagement")
    truth = float(read(TRUTH)[0]["true_effect"]) if TRUTH.exists() else None

    names = {"action": "Action plan", "comparison": "Eligible, no plan", "rest": "All other teams"}
    viz.paired_bars(FIGURES / "09_action_plan_waves.svg", [f"{names[g]} ({len(groups[g])})" for g in groups],
                    [avg(g, DIMENSION, 0) for g in groups], [avg(g, DIMENSION, 1) for g in groups],
                    "Manager Support, a year apart",
                    "Team favourable scores at the two surveys; only the comparison separates the plan from chance")

    rows = [[names[g], str(len(groups[g])), f"{avg(g, DIMENSION, 0):.1%}", f"{avg(g, DIMENSION, 1):.1%}",
             f"{(avg(g, DIMENSION, 1) - avg(g, DIMENSION, 0)) * 100:+.1f} pts",
             f"{avg(g, 'rate', 0):.0%} → {avg(g, 'rate', 1):.0%}"] for g in groups]
    covered = truth is not None and lo <= truth <= hi
    md = [
        "## 5. Did the action plan work? Two waves, and the trap between them",
        "",
        "A year after the first survey, half of the teams in the bottom third on Manager Support had a "
        "manager-support action plan, the half drawn at random. Teams are compared, never people: the survey is "
        f"anonymous at both waves. Teams with at least {MIN_GROUP} respondents in both waves are kept.",
        "",
        md_table(["Teams", "Count", "Wave 1", "Wave 2", "Change", "Response rate"], rows, align="lrrrrr"),
        "",
        "![Manager Support a year apart](figures/09_action_plan_waves.svg)",
        "",
        f"**Before and after is not the effect.** The action teams rose **{naive * 100:+.1f} points**. The eligible "
        f"teams that had no plan moved **{rtm * 100:+.1f} points** with nothing done, and the strongest teams "
        f"{(avg('rest', DIMENSION, 1) - avg('rest', DIMENSION, 0)) * 100:+.1f}: teams picked for a low score were partly "
        "unlucky, and the luck does not repeat. That is regression to the mean, and a before-and-after comparison "
        "credits it to the plan. "
        + ("Here the bounce is small, because Manager Support differences between teams are mostly real; on a noisier "
           "score, or smaller teams, it can be most of the change."
           if abs(rtm) < 0.25 * abs(naive) else
           "Here it is a large part of the change."),
        "",
        f"**The effect of the plan is the difference: {est * 100:+.1f} points** of Manager Support favourable "
        f"(95% interval {lo * 100:+.1f} to {hi * 100:+.1f}, resampling teams). On engagement the same comparison gives "
        f"{e_est * 100:+.1f} points ({e_lo * 100:+.1f} to {e_hi * 100:+.1f})"
        + (": a manager plan shows first where it acts, and reaches engagement more slowly and less surely."
           if e_lo <= 0 else "."),
        "",
    ]
    if truth is not None:
        md += [
            f"**Checked against the truth.** The generator knows what the plan did: **{truth * 100:+.1f} points** for "
            "the people in those teams. "
            + (f"The interval covers it; the naive before-and-after, {naive * 100:+.1f}, is "
               f"{naive / truth:.1f} times the real effect." if covered else
               f"The interval misses it, which happens one time in twenty; the naive before-and-after, "
               f"{naive * 100:+.1f}, is {naive / truth:.1f} times the real effect.")
            + (f" The difference in differences lands {abs(est - truth) * 100:.1f} points "
               f"{'above' if est > truth else 'below'} the truth as well, about {abs(est - truth) / ((hi - lo) / 3.92):.1f} "
               f"standard errors: with {len(groups['action'])} and {len(groups['comparison'])} teams a side, an honest "
               "estimate is a wide one, and the interval is the part to report."
               if abs(est - truth) > (hi - lo) / 3.92 else ""),
            "",
        ]
    md += [
        "**What makes this possible is the comparison group.** Had every weak team received the plan, nothing in the "
        "data could separate the plan from the bounce. Piloting it on part of the eligible teams, chosen at random "
        "or in a fixed order, costs a year's wait for the rest and is what turns a survey into evidence.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
