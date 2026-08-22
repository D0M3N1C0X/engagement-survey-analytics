"""
Synthetic engagement-survey generator.

Builds a complete annual survey for a fictional European services group
(~3,800 invited employees across 4 countries and 148 teams):

    data/teams.csv             one row per team, with its manager
    data/survey_responses.csv  one row per *invited* employee - answers only
                               where the person actually responded
    data/survey_comments.csv   free-text verbatims

The invite list is included in full, non-respondents and all, because response
rate and non-response bias are part of the analysis rather than a footnote.

Everything is stdlib with a fixed seed, so the files are byte-identical on
every machine. The effects deliberately planted here - the true driver
weights, the team variation, the comment themes and the response bias - are
listed in data/README.md so the analysis can be judged on whether it recovers
them.
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SEED = 7
N_EMPLOYEES = 3800
SURVEY_NAME = "Voice 2026"
FIELD_START = "2026-05-04"
FIELD_END = "2026-05-22"

rng = random.Random(SEED)

# --------------------------------------------------------------------------
# Survey instrument
# --------------------------------------------------------------------------

# dimension -> (target favourable rate company-wide, true weight on engagement)
# The weights are the ground truth the key-driver analysis has to recover:
# Career Growth and Recognition matter a lot and score badly (the priority
# quadrant), while Pay scores badly but carries little weight - the finding
# every engagement survey produces and every leadership team argues about.
DIMENSIONS = {
    "Manager Support":          (0.68, 0.26),
    "Career Growth":            (0.42, 0.22),
    "Recognition":              (0.46, 0.15),
    "Workload & Wellbeing":     (0.63, 0.12),
    "Leadership & Direction":   (0.57, 0.10),
    "Pay & Benefits":           (0.42, 0.06),
    "Inclusion & Belonging":    (0.73, 0.06),
    "Tools & Process":          (0.60, 0.03),
}

# item id -> (dimension, wording, item difficulty offset)
ITEMS = {
    "mgr_01": ("Manager Support", "My manager gives me feedback that helps me improve", 0.0),
    "mgr_02": ("Manager Support", "My manager treats me with respect", 0.55),
    "mgr_03": ("Manager Support", "My manager is available when I need support", -0.15),
    "mgr_04": ("Manager Support", "My manager acts on the concerns I raise", -0.35),
    "grw_01": ("Career Growth", "I can see a realistic path to progress here", -0.30),
    "grw_02": ("Career Growth", "I have opportunities to learn and develop", 0.10),
    "grw_03": ("Career Growth", "Promotion decisions in my area are made fairly", -0.25),
    "rec_01": ("Recognition", "Good work is recognised in my team", 0.05),
    "rec_02": ("Recognition", "I receive recognition beyond my direct manager", -0.30),
    "wlb_01": ("Workload & Wellbeing", "My workload is manageable most weeks", -0.10),
    "wlb_02": ("Workload & Wellbeing", "I can switch off outside working hours", -0.25),
    "wlb_03": ("Workload & Wellbeing", "My team has enough people to do the work", -0.20),
    "ldr_01": ("Leadership & Direction", "I understand where the company is going", 0.20),
    "ldr_02": ("Leadership & Direction", "Senior leaders communicate openly and honestly", -0.20),
    "ldr_03": ("Leadership & Direction", "Decisions are explained well enough to act on", -0.10),
    "pay_01": ("Pay & Benefits", "I am paid fairly for the work I do", -0.15),
    "pay_02": ("Pay & Benefits", "Our benefits meet my needs", 0.15),
    "inc_01": ("Inclusion & Belonging", "I can be myself at work", 0.20),
    "inc_02": ("Inclusion & Belonging", "My opinion counts in my team", -0.15),
    "inc_03": ("Inclusion & Belonging", "People here are treated fairly regardless of background", 0.05),
    "tls_01": ("Tools & Process", "I have the tools I need to do my job well", 0.10),
    "tls_02": ("Tools & Process", "Our processes help rather than get in the way", -0.35),
}

# Outcome items - the engagement index, kept separate from the drivers so the
# regression is not predicting a variable that contains its own predictors.
OUTCOME_ITEMS = {
    "eng_01": "I am proud to work here",
    "eng_02": "I would go beyond what is expected to help this company succeed",
    "eng_03": "I see myself still working here in two years",
}

RESPONSE_LABELS = {1: "Strongly disagree", 2: "Disagree", 3: "Neither",
                   4: "Agree", 5: "Strongly agree"}

# --------------------------------------------------------------------------
# Organisation
# --------------------------------------------------------------------------

COUNTRIES = {"IT": 0.29, "PL": 0.33, "DE": 0.22, "ES": 0.16}

# department -> (share of headcount, share of shift-based roles)
DEPARTMENTS = {
    "Operations": (0.31, 0.75),
    "Customer Service": (0.24, 0.55),
    "Commercial": (0.14, 0.05),
    "Technology": (0.13, 0.02),
    "Finance & Legal": (0.09, 0.0),
    "People & Workplace": (0.09, 0.05),
}

LEVELS = {"Individual contributor": 0.72, "Team lead": 0.18,
          "Manager": 0.08, "Senior leader": 0.02}
TENURES = {"< 1 year": 0.19, "1-2 years": 0.24, "3-5 years": 0.27,
           "6-10 years": 0.19, "10 years +": 0.11}
WORK_MODELS = {"Onsite": 0.46, "Hybrid": 0.40, "Remote": 0.14}

# Country and department pull each dimension around a little, so the heatmap
# has real structure instead of noise.
COUNTRY_EFFECT = {"IT": -0.05, "PL": 0.08, "DE": -0.10, "ES": 0.06}
DEPARTMENT_EFFECT = {
    "Operations": {"Workload & Wellbeing": -0.45, "Career Growth": -0.30,
                   "Tools & Process": -0.25, "Pay & Benefits": -0.20},
    "Customer Service": {"Workload & Wellbeing": -0.30, "Recognition": -0.25,
                         "Career Growth": -0.20},
    "Technology": {"Pay & Benefits": 0.25, "Tools & Process": 0.20,
                   "Leadership & Direction": -0.20},
    "Commercial": {"Recognition": 0.15, "Workload & Wellbeing": -0.15},
    "Finance & Legal": {"Career Growth": -0.15},
    "People & Workplace": {"Inclusion & Belonging": 0.20, "Pay & Benefits": -0.15},
}
LEVEL_EFFECT = {"Individual contributor": -0.10, "Team lead": 0.05,
                "Manager": 0.25, "Senior leader": 0.55}
TENURE_EFFECT = {"< 1 year": 0.35, "1-2 years": 0.05, "3-5 years": -0.10,
                 "6-10 years": -0.12, "10 years +": 0.02}


# --------------------------------------------------------------------------
# Small maths helpers
# --------------------------------------------------------------------------

def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


def probit(p: float) -> float:
    """Inverse normal CDF by bisection - accurate enough and dependency-free."""
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pick(weights: dict) -> str:
    keys = list(weights)
    w = [weights[k][0] if isinstance(weights[k], tuple) else weights[k] for k in keys]
    return rng.choices(keys, weights=w, k=1)[0]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# Latent responses are mapped to the 1-5 scale with these cut points; the
# spread of the latent variable is roughly one standard deviation.
CUTS = (-1.15, -0.35, 0.35, 1.15)
LATENT_SD = 0.95


def to_scale(latent: float) -> int:
    return 1 + sum(latent > c for c in CUTS)


def dimension_base(target_favourable: float) -> float:
    """Centre a dimension so that the company-wide favourable rate lands on target."""
    return CUTS[2] - probit(1 - target_favourable) * LATENT_SD


DIM_BASE = {dim: dimension_base(target) for dim, (target, _w) in DIMENSIONS.items()}
WEIGHTS = {dim: w for dim, (_t, w) in DIMENSIONS.items()}


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------

def make_teams() -> list[dict]:
    teams = []
    team_no = 0
    for dept, (share, _shift) in DEPARTMENTS.items():
        headcount = int(N_EMPLOYEES * share)
        assigned = 0
        while assigned < headcount:
            size = min(headcount - assigned, max(4, int(rng.triangular(4, 60, 18))))
            if headcount - assigned - size < 4:
                size = headcount - assigned
            team_no += 1
            country = pick(COUNTRIES)

            # Manager quality is the single biggest source of team-to-team
            # variation in any real survey, so it gets its own latent value.
            manager_quality = rng.gauss(0, 0.52)
            teams.append({
                "team_id": f"T{team_no:03d}",
                "team_name": f"{dept.split(' ')[0]} {country} {team_no:03d}",
                "department": dept,
                "country": country,
                "manager_id": f"M{team_no:03d}",
                "manager_tenure_months": int(clamp(rng.expovariate(1 / 30) + 2, 2, 140)),
                "team_size": size,
                "_manager_quality": manager_quality,
                "_team_effect": rng.gauss(0, 0.22),
            })
            assigned += size
    return teams


# --------------------------------------------------------------------------
# Respondents
# --------------------------------------------------------------------------

def make_responses(teams: list[dict]) -> list[dict]:
    rows = []
    person_no = 0

    for team in teams:
        dept = team["department"]
        shift_share = DEPARTMENTS[dept][1]

        for _ in range(team["team_size"]):
            person_no += 1
            level = pick(LEVELS)
            tenure = pick(TENURES)
            work_model = "Onsite" if rng.random() < shift_share else pick(WORK_MODELS)
            shift_worker = int(work_model == "Onsite" and rng.random() < shift_share)

            # ---- latent satisfaction per dimension ----------------------
            latent = {}
            for dim in DIMENSIONS:
                value = (DIM_BASE[dim]
                         + team["_team_effect"]
                         + COUNTRY_EFFECT[team["country"]]
                         + DEPARTMENT_EFFECT.get(dept, {}).get(dim, 0.0)
                         + LEVEL_EFFECT[level]
                         + TENURE_EFFECT[tenure]
                         + rng.gauss(0, 0.55))
                if dim == "Manager Support":
                    value += team["_manager_quality"] * 1.10
                elif dim in ("Recognition", "Career Growth"):
                    value += team["_manager_quality"] * 0.45
                if shift_worker and dim in ("Workload & Wellbeing", "Tools & Process"):
                    value -= 0.30
                latent[dim] = value

            engagement_latent = (sum(WEIGHTS[d] * latent[d] for d in DIMENSIONS)
                                 / sum(WEIGHTS.values()) + rng.gauss(0, 0.42))

            # ---- who actually responds ---------------------------------
            # Disengaged people and shift workers answer less often: the
            # non-response bias the representativeness check has to find.
            p_response = clamp(0.74
                               + 0.11 * engagement_latent
                               + 0.10 * (level in ("Manager", "Senior leader"))
                               - 0.16 * shift_worker
                               - 0.07 * (dept == "Operations")
                               + 0.06 * (work_model == "Remote"),
                               0.22, 0.96)
            responded = int(rng.random() < p_response)

            row = {
                "response_id": f"R{person_no:05d}",
                "team_id": team["team_id"],
                "department": dept,
                "country": team["country"],
                "job_level": level,
                "tenure_band": tenure,
                "work_model": work_model,
                "shift_worker": shift_worker,
                "responded": responded,
                "submitted_date": "",
                "enps": "",
            }
            for item_id in ITEMS:
                row[item_id] = ""
            for item_id in OUTCOME_ITEMS:
                row[item_id] = ""

            if responded:
                row["submitted_date"] = random_field_date()
                for item_id, (dim, _text, bias) in ITEMS.items():
                    row[item_id] = to_scale(latent[dim] + bias + rng.gauss(0, 0.5))
                for i, item_id in enumerate(OUTCOME_ITEMS):
                    row[item_id] = to_scale(engagement_latent + (0.15, -0.10, -0.25)[i]
                                            + rng.gauss(0, 0.5))
                row["enps"] = enps_score(engagement_latent)

            row["_latent"] = latent
            row["_engagement"] = engagement_latent
            rows.append(row)

    return rows


def random_field_date() -> str:
    """Responses cluster in the first days of fieldwork and after the reminder."""
    day = rng.choices(range(19), weights=[9, 8, 6, 4, 3, 2, 2, 3, 3, 2, 2,
                                          7, 6, 4, 3, 2, 3, 5, 8], k=1)[0]
    return f"2026-05-{4 + day:02d}"


def enps_score(engagement_latent: float) -> int:
    """0-10 recommendation score, driven by the same latent engagement."""
    raw = 6.15 + 2.1 * engagement_latent + rng.gauss(0, 1.15)
    return int(clamp(round(raw), 0, 10))


# --------------------------------------------------------------------------
# Free-text comments
# --------------------------------------------------------------------------

# Each theme carries fragments for both survey questions and for both tones.
# The wording deliberately overlaps between themes ("workload" language shows
# up inside manager comments too) so that keyword tagging has to cope with
# ambiguity rather than sorting a clean set of buckets.
THEMES = {
    "workload": {
        "dimension": "Workload & Wellbeing",
        "negative": [
            "We are permanently short-staffed and the overtime has stopped feeling optional.",
            "Every week is firefighting; there is no capacity left for anything planned.",
            "Two people left my team last year and neither was replaced, so the work just moved to us.",
            "I answer messages at 10pm because there is no other way to keep up.",
            "Holiday requests get refused because we do not have the cover.",
        ],
        "positive": [
            "My team lead protects our workload and it makes a real difference.",
            "Since we added two people the pressure has come down a lot.",
        ],
    },
    "manager": {
        "dimension": "Manager Support",
        "negative": [
            "My manager cancels our one to ones more often than we hold them.",
            "I raised the same issue three times and nothing came back.",
            "Feedback only arrives when something goes wrong.",
            "My manager avoids difficult conversations, so problems in the team just continue.",
        ],
        "positive": [
            "My manager is genuinely supportive and gives me feedback I can use.",
            "I always know where I stand with my manager, which I value.",
            "My team lead backs us up when things go wrong and that builds trust.",
        ],
    },
    "career": {
        "dimension": "Career Growth",
        "negative": [
            "There is no visible route from my role to the next one.",
            "Promotions here go to people who are visible to leadership, not to people who deliver.",
            "I have been in the same grade for four years with no conversation about what comes next.",
            "Training budget exists on paper but every request gets postponed.",
            "We hire externally for roles that people inside could grow into.",
        ],
        "positive": [
            "The internal move I made last year was handled really well.",
            "My development plan is real and we actually review it.",
        ],
    },
    "recognition": {
        "dimension": "Recognition",
        "negative": [
            "Good work is expected and never mentioned; mistakes are mentioned immediately.",
            "Recognition stops at my manager and never travels further up.",
            "The team delivered a difficult project and nobody outside noticed.",
        ],
        "positive": [
            "The team shout-outs in our monthly meeting are a small thing that works.",
            "My manager makes a point of recognising good work publicly.",
        ],
    },
    "pay": {
        "dimension": "Pay & Benefits",
        "negative": [
            "My salary has not kept up with inflation for two years running.",
            "New joiners are hired above people already doing the job.",
            "The pay bands are a secret, which makes it impossible to trust the process.",
            "Benefits are fine but the base salary is below what I am offered elsewhere.",
        ],
        "positive": [
            "The pension contribution and the extra leave days are genuinely good.",
        ],
    },
    "leadership": {
        "dimension": "Leadership & Direction",
        "negative": [
            "Strategy changes every quarter and nobody explains why.",
            "We hear about decisions that affect us from other teams first.",
            "Town halls are broadcasts, not conversations - questions get filtered.",
            "Leadership talks about transparency and then reorganises without warning.",
        ],
        "positive": [
            "The last town hall actually answered the hard questions honestly.",
            "The direction for the year is clear and I can see how my work fits.",
        ],
    },
    "tools": {
        "dimension": "Tools & Process",
        "negative": [
            "The approval process takes longer than the work itself.",
            "Our systems do not talk to each other so we rekey the same data twice.",
            "Getting access to a tool takes weeks and nobody owns the process.",
        ],
        "positive": [
            "The new scheduling tool has saved us hours every week.",
        ],
    },
    "hybrid": {
        "dimension": "Workload & Wellbeing",
        "negative": [
            "The office rules changed twice this year with no explanation.",
            "I commute an hour to sit on video calls I could take from home.",
            "Shift patterns get published too late to plan anything around them.",
        ],
        "positive": [
            "The hybrid arrangement works well for me and my team coordinates it sensibly.",
            "Flexibility around school hours is the main reason I stay.",
        ],
    },
    "inclusion": {
        "dimension": "Inclusion & Belonging",
        "negative": [
            "The same voices dominate every meeting and the rest of us stop trying.",
            "Everything important is decided in English at a speed that excludes half the room.",
        ],
        "positive": [
            "My team is genuinely welcoming and people look out for each other.",
            "I can raise a concern here without worrying about how it will be taken.",
        ],
    },
    "onboarding": {
        "dimension": "Tools & Process",
        "negative": [
            "My first month was three days of induction and then nothing.",
            "I did not have a laptop for my first week, which set the tone.",
        ],
        "positive": [
            "My onboarding buddy made the first weeks much easier.",
        ],
    },
}

# The label each generated theme corresponds to in the analyst's lexicon
# (src/textlib.py). Writing these out as ground truth is what lets the text
# pipeline be scored instead of admired.
THEME_LABELS = {
    "workload": "Workload & staffing",
    "manager": "Manager relationship",
    "career": "Career & progression",
    "recognition": "Recognition",
    "pay": "Pay & benefits",
    "leadership": "Leadership & communication",
    "tools": "Tools & process",
    "hybrid": "Flexibility & workplace",
    "inclusion": "Inclusion & voice",
    "onboarding": "Joining & onboarding",
}

OPENERS_NEGATIVE = ["", "", "", "Honestly, ", "To be direct: ", "The main issue is that "]
OPENERS_POSITIVE = ["", "", "Genuinely, ", "One thing that works: "]
# How a complaint ends depends on how the person feels about the company as a
# whole: the disengaged sign off with an exit threat, the engaged with a
# caveat. This is what gives free text information the scores do not already
# carry - and what makes validating a sentiment model against eNPS meaningful.
CLOSERS_ANGRY = [" It is the main reason people are looking elsewhere.",
                 " I am already looking at other options.",
                 " Nothing has changed since the last survey.",
                 " Frankly it is exhausting."]
CLOSERS_NEUTRAL = ["", "", " This needs fixing this year.", " It should not be this hard."]
CLOSERS_SOFT = ["", " Otherwise this is a good place to work.",
                " It is the one thing I would change.",
                " The rest of my experience here is positive."]
CLOSERS_POSITIVE = ["", "", " Please keep it.", " That should be the standard everywhere."]


def make_comments(responses: list[dict]) -> list[dict]:
    comments = []
    comment_no = 0

    for row in responses:
        if not row["responded"]:
            continue
        if rng.random() > comment_probability(row):
            continue

        latent = row["_latent"]
        weakest = sorted(latent, key=lambda d: latent[d])[:3]
        strongest = sorted(latent, key=lambda d: -latent[d])[:2]

        for question in ("what_to_change", "what_works"):
            negative = question == "what_to_change"
            # People comment about their own low scores, which is what makes
            # text and numbers agree - and what the analysis then shows.
            pool = [name for name, theme in THEMES.items()
                    if theme["dimension"] in (weakest if negative else strongest)]
            if not pool:
                pool = list(THEMES)
            # Whether someone answers the critical question, the positive one,
            # or both is itself driven by how they feel: detractors write far
            # more "what to change" than promoters. The comment mix carries
            # signal before a single word is read.
            engagement = row["_engagement"]
            if negative:
                p_write = clamp(0.80 - 0.22 * engagement, 0.35, 0.97)
            else:
                p_write = clamp(0.45 + 0.28 * engagement, 0.08, 0.90)
            if rng.random() > p_write:
                continue

            theme_name = rng.choice(pool)
            theme = THEMES[theme_name]
            bank = theme["negative"] if negative else theme["positive"]
            if not bank:
                continue
            themes_used = [theme_name]

            text = rng.choice(bank)
            opener = rng.choice(OPENERS_NEGATIVE if negative else OPENERS_POSITIVE)
            if opener:
                text = opener + text[0].lower() + text[1:]
            if negative:
                engagement = row["_engagement"]
                if engagement < -0.35:
                    pool = CLOSERS_ANGRY if rng.random() < 0.8 else CLOSERS_NEUTRAL
                elif engagement > 0.35:
                    pool = CLOSERS_SOFT if rng.random() < 0.8 else CLOSERS_NEUTRAL
                else:
                    pool = CLOSERS_NEUTRAL
                text += rng.choice(pool)
            else:
                text += rng.choice(CLOSERS_POSITIVE)

            # A second sentence from another theme, sometimes - real verbatims
            # are rarely single-topic.
            if rng.random() < 0.22:
                other = rng.choice([n for n in THEMES if n != theme_name])
                bank2 = THEMES[other]["negative"] if negative else THEMES[other]["positive"]
                if bank2:
                    text += " " + rng.choice(bank2)
                    themes_used.append(other)

            comment_no += 1
            comments.append({
                "comment_id": f"C{comment_no:05d}",
                "response_id": row["response_id"],
                "question": question,
                "comment_text": text.strip(),
                "_true_themes": themes_used,
                "_true_tone": "positive" if not negative else "negative",
            })

    return comments


def comment_probability(row: dict) -> float:
    """Unhappy people and long-tenure people write more; new joiners write less."""
    p = 0.42 - 0.12 * row["_engagement"]
    if row["tenure_band"] in ("6-10 years", "10 years +"):
        p += 0.06
    if row["tenure_band"] == "< 1 year":
        p -= 0.08
    return clamp(p, 0.12, 0.8)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict], drop: tuple[str, ...] = ()) -> None:
    fields = [f for f in rows[0] if not f.startswith("_") and f not in drop]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_instrument(path: Path) -> None:
    """The questionnaire itself, so the dataset is readable without the code."""
    rows = [{"item_id": item_id, "dimension": dim, "wording": text, "type": "driver"}
            for item_id, (dim, text, _bias) in ITEMS.items()]
    rows += [{"item_id": item_id, "dimension": "Engagement (outcome)",
              "wording": text, "type": "outcome"}
             for item_id, text in OUTCOME_ITEMS.items()]
    rows.append({"item_id": "enps", "dimension": "Engagement (outcome)",
                 "wording": "How likely are you to recommend this company as a place to "
                            "work? (0-10)", "type": "outcome"})
    write_csv(path, rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    teams = make_teams()
    responses = make_responses(teams)
    comments = make_comments(responses)

    write_csv(DATA / "teams.csv", teams)
    write_csv(DATA / "survey_responses.csv", responses)
    write_csv(DATA / "survey_comments.csv", comments)
    write_instrument(DATA / "survey_instrument.csv")

    # Ground truth for the text pipeline: which themes each verbatim was built
    # from. A real corpus has nothing like this, which is exactly why it is
    # useful here - it turns "the tagger looks reasonable" into a measured
    # precision and recall per theme.
    write_csv(DATA / "comment_themes_truth.csv",
              [{"comment_id": c["comment_id"],
                "true_themes": "; ".join(THEME_LABELS[t] for t in c["_true_themes"]),
                "true_tone": c["_true_tone"]} for c in comments])

    answered = sum(r["responded"] for r in responses)
    print(f"teams.csv              : {len(teams):>6,} teams")
    print(f"survey_responses.csv   : {len(responses):>6,} invited, {answered:,} responded "
          f"({answered / len(responses):.1%})")
    print(f"survey_comments.csv    : {len(comments):>6,} verbatims")
    print(f"survey_instrument.csv  : {len(ITEMS) + len(OUTCOME_ITEMS) + 1:>6,} questions")


if __name__ == "__main__":
    main()
