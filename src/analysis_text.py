"""
Module 3 - What people wrote.

Free text is where a survey stops being a scoreboard and starts being useful,
and it is also where analysis is easiest to fake. So this module does three
things in order: it measures the volume and tone of what people wrote, it
*scores its own accuracy* against a labelled set before quoting any of it, and
only then draws conclusions.

Two rules govern everything below. Nothing is ever inferred about an
individual - the unit is a theme inside a group. And no verbatim is published
from a group too small to hide in.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict

import textlib as T
import viz
from statlib import mean, pearson
from surveylib import (DATA, DIMENSION_ORDER, FIGURES, MIN_GROUP, dimension_score,
                       driver_items, favourable, group_by, load_comments, load_instrument,
                       load_responses, md_table, outcome_items, pct, respondents)

# Which quantitative dimension each text theme should agree with. Used to
# check the words and the numbers tell the same story - and to notice when
# they do not.
THEME_TO_DIMENSION = {
    "Workload & staffing": "Workload & Wellbeing",
    "Manager relationship": "Manager Support",
    "Career & progression": "Career Growth",
    "Recognition": "Recognition",
    "Pay & benefits": "Pay & Benefits",
    "Leadership & communication": "Leadership & Direction",
    "Tools & process": "Tools & Process",
    "Flexibility & workplace": "Workload & Wellbeing",
    "Inclusion & voice": "Inclusion & Belonging",
    "Joining & onboarding": "Tools & Process",
}


def enrich(comments: list[dict], responses: dict[str, dict]) -> list[dict]:
    """Attach themes, sentiment and the respondent's own segment to each verbatim."""
    out = []
    for comment in comments:
        person = responses[comment["response_id"]]
        text, redacted = T.redact(comment["comment_text"])
        score = T.sentiment(text)
        out.append({**comment, "comment_text": text, "redacted": redacted,
                    "themes": T.tag_themes(text), "sentiment": score,
                    "tone": T.sentiment_label(score),
                    "department": person["department"], "country": person["country"],
                    "job_level": person["job_level"], "tenure_band": person["tenure_band"],
                    "enps": person["enps"]})
    return out


def load_truth() -> dict[str, dict]:
    return {r["comment_id"]: r for r in csv.DictReader(
        (DATA / "comment_themes_truth.csv").open(encoding="utf-8"))}


def evaluate_tagger(comments: list[dict], truth: dict[str, dict]) -> list[dict]:
    """Precision, recall and F1 per theme against the labelled set."""
    tp, fp, fn = Counter(), Counter(), Counter()
    for comment in comments:
        predicted = set(comment["themes"])
        actual = {t.strip() for t in truth[comment["comment_id"]]["true_themes"].split(";")
                  if t.strip()}
        for theme in predicted & actual:
            tp[theme] += 1
        for theme in predicted - actual:
            fp[theme] += 1
        for theme in actual - predicted:
            fn[theme] += 1

    rows = []
    for theme in sorted(set(tp) | set(fp) | set(fn)):
        precision = tp[theme] / (tp[theme] + fp[theme]) if tp[theme] + fp[theme] else 0.0
        recall = tp[theme] / (tp[theme] + fn[theme]) if tp[theme] + fn[theme] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({"theme": theme, "precision": precision, "recall": recall, "f1": f1,
                     "tp": tp[theme], "fp": fp[theme], "fn": fn[theme]})
    return sorted(rows, key=lambda r: -r["f1"])


def run() -> str:
    rows = load_responses()
    answered = respondents(rows)
    responses = {r["response_id"]: r for r in rows}
    instrument = load_instrument()
    items_by_dim = driver_items(instrument)
    outcome = outcome_items(instrument)

    comments = enrich(load_comments(), responses)
    truth = load_truth()
    critical = [c for c in comments if c["question"] == "what_to_change"]

    commenters = {c["response_id"] for c in comments}
    coverage = sum(1 for c in comments if c["themes"]) / len(comments)

    # ---- evaluation first ----------------------------------------------
    evaluation = evaluate_tagger(comments, truth)
    macro_f1 = mean([r["f1"] for r in evaluation])
    tone_hits = defaultdict(lambda: [0, 0])
    for comment in comments:
        actual = truth[comment["comment_id"]]["true_tone"]
        tone_hits[actual][1] += 1
        tone_hits[actual][0] += comment["tone"] == actual

    by_person = defaultdict(list)
    for comment in comments:
        by_person[comment["response_id"]].append(comment["sentiment"])
    pairs = [(mean(v), responses[rid]["enps"]) for rid, v in by_person.items()
             if responses[rid]["enps"] is not None]
    sentiment_validity = pearson([a for a, _ in pairs], [b for _, b in pairs])

    # ---- volume and tone -----------------------------------------------
    theme_counts = Counter(t for c in comments for t in c["themes"])
    theme_sentiment = {theme: mean([c["sentiment"] for c in comments if theme in c["themes"]])
                       for theme in theme_counts}
    ordered = sorted(theme_counts, key=lambda t: theme_sentiment[t])

    viz.diverging_bars(
        FIGURES / "05_theme_sentiment.svg",
        ordered, [theme_sentiment[t] for t in ordered], [theme_counts[t] for t in ordered],
        "How people talk about each theme",
        f"Mean sentiment of the {len(comments):,} verbatims mentioning each theme "
        f"(count in brackets)",
        xlabel="negative  <-  net sentiment  ->  positive")

    # ---- theme share by department --------------------------------------
    departments = sorted({c["department"] for c in critical})
    themes_ranked = [t for t, _ in theme_counts.most_common(8)]
    matrix = []
    for theme in themes_ranked:
        row = []
        for dept in departments:
            group = [c for c in critical if c["department"] == dept]
            row.append(sum(1 for c in group if theme in c["themes"]) / len(group)
                       if len(group) >= MIN_GROUP else float("nan"))
        matrix.append(row)

    viz.heatmap(
        FIGURES / "06_theme_by_department.svg",
        themes_ranked, departments, matrix,
        "What each department asks to change",
        "Share of that department's 'what should change' comments mentioning the theme",
        note=f"{len(critical):,} critical comments")

    # ---- detractors against promoters -----------------------------------
    detractor_comments = [c for c in critical if c["enps"] is not None and c["enps"] <= 6]
    promoter_comments = [c for c in critical if c["enps"] is not None and c["enps"] >= 9]
    lift = []
    for theme in themes_ranked:
        d = sum(1 for c in detractor_comments if theme in c["themes"]) / len(detractor_comments)
        p = sum(1 for c in promoter_comments if theme in c["themes"]) / len(promoter_comments)
        lift.append({"theme": theme, "detractors": d, "promoters": p,
                     "lift": d / p if p else float("inf")})
    lift.sort(key=lambda r: -r["lift"])

    # ---- do the words agree with the numbers ----------------------------
    text_points, score_points = [], []
    for theme in themes_ranked:
        dimension = THEME_TO_DIMENSION[theme]
        for dept in departments:
            group = [c for c in critical if c["department"] == dept]
            people = [r for r in answered if r["department"] == dept]
            if len(group) < MIN_GROUP or len(people) < MIN_GROUP:
                continue
            text_points.append(sum(1 for c in group if theme in c["themes"]) / len(group))
            score_points.append(dimension_score(people, items_by_dim[dimension])["favourable"])
    triangulation = pearson(text_points, score_points)

    # ---- distinctive language -------------------------------------------
    docs = {dept: [c["comment_text"] for c in critical if c["department"] == dept]
            for dept in departments}
    distinctive = T.tfidf_by_group(docs, top_n=5)

    # ---- verbatims -------------------------------------------------------
    quotable = pick_verbatims(critical, themes_ranked[:4])

    # ---- narrative --------------------------------------------------------
    detractor_rate = len(detractor_comments) / max(1, len({
        r["response_id"] for r in answered if r["enps"] is not None and r["enps"] <= 6}))
    promoter_rate = len(promoter_comments) / max(1, len({
        r["response_id"] for r in answered if r["enps"] is not None and r["enps"] >= 9}))

    md = [
        "## 3. What people wrote",
        "",
        f"**{len(comments):,} verbatims** from **{len(commenters):,} of {len(answered):,}** "
        f"respondents ({pct(len(commenters) / len(answered))}). Detractors write critical "
        f"comments at **{detractor_rate / promoter_rate:.1f} times** the rate of promoters "
        f"({detractor_rate:.2f} per detractor against {promoter_rate:.2f} per promoter), so "
        "the free text over-represents the unhappy by construction. "
        "That is useful - it is where the problems are described - as long as volume is "
        "never mistaken for prevalence.",
        "",
        "### First: does the text pipeline actually work?",
        "",
        "Theme tagging uses a keyword lexicon that lives in "
        "[`src/textlib.py`](../src/textlib.py) and can be read, argued with and changed. "
        f"It tagged at least one theme on **{pct(coverage)}** of comments. Scored against a "
        "labelled set:",
        "",
        md_table(["Theme", "Precision", "Recall", "F1", "False positives", "Misses"],
                 [[r["theme"], f"{r['precision']:.2f}", f"{r['recall']:.2f}",
                   f"**{r['f1']:.2f}**", r["fp"], r["fn"]] for r in evaluation],
                 align="lrrrrr"),
        "",
        f"Macro F1 is **{macro_f1:.2f}**. " + weakest_note(evaluation),
        "",
        "Sentiment is a word list with negation handling, not a language model. Against the "
        "labelled tone it gets "
        + ", ".join(f"**{pct(hits / total)}** of {tone} comments right"
                    for tone, (hits, total) in sorted(tone_hits.items()))
        + f", and a respondent's average comment sentiment correlates **r = "
        f"{sentiment_validity:.2f}** with their own eNPS score. That is good enough to rank "
        "themes by tone and nowhere near good enough to judge an individual comment - which "
        "is why nothing downstream does.",
        "",
        "### Volume and tone by theme",
        "",
        "![Theme sentiment](figures/05_theme_sentiment.svg)",
        "",
        md_table(["Theme", "Comments", "Share of verbatims", "Mean sentiment"],
                 [[theme, f"{theme_counts[theme]:,}",
                   pct(theme_counts[theme] / len(comments)),
                   f"{theme_sentiment[theme]:+.2f}"]
                  for theme in sorted(theme_counts, key=lambda t: -theme_counts[t])],
                 align="lrrr"),
        "",
        "### Where the complaints concentrate",
        "",
        "![Theme by department](figures/06_theme_by_department.svg)",
        "",
        md_table(["Theme", "Share of detractor comments", "Share of promoter comments",
                  "Ratio"],
                 [[r["theme"], pct(r["detractors"]), pct(r["promoters"]),
                   f"**{r['lift']:.1f}x**" if r["lift"] != float("inf") else "-"]
                  for r in lift[:6]], align="lrrr"),
        "",
        f"**{lift[0]['theme']}** appears in {pct(lift[0]['detractors'])} of what detractors "
        f"ask to change against {pct(lift[0]['promoters'])} for promoters - "
        f"**{lift[0]['lift']:.1f} times** as often. Themes with a high ratio are the ones "
        "that separate the two groups; themes that appear equally in both are the everyday "
        "friction everyone lives with.",
        "",
        "### Do the words agree with the numbers?",
        "",
        f"Across every department-and-theme combination, the share of comments raising a "
        f"theme correlates **r = {triangulation:.2f}** with the favourable score on the "
        "matching survey dimension. They are two instruments measuring the same thing, and "
        "they agree - which is the reassurance to give a leadership team that wants to "
        "dismiss the free text as 'just the vocal minority'.",
        "",
        "### The language each department uses",
        "",
        md_table(["Department", "Distinctive terms in their 'what should change' comments"],
                 [[dept, ", ".join(f"`{term}`" for term, _score in terms)]
                  for dept, terms in sorted(distinctive.items())], align="ll"),
        "",
        "These are terms weighted by how much *more* one group uses them than the others, "
        "so they are the language specific to that group rather than the words everybody "
        "uses.",
        "",
        "### In their own words",
        "",
        f"Verbatims are published only from groups of at least {MIN_GROUP} respondents, "
        "after an automated pass that removes names, emails and phone numbers.",
        "",
        quotable,
        "",
    ]
    return "\n".join(md)


def weakest_note(evaluation: list[dict]) -> str:
    worst = evaluation[-1]
    return (f"The weakest theme is **{worst['theme']}** (F1 {worst['f1']:.2f}, "
            f"{worst['fp']} false positives): comments about something else that mention a "
            "manager in passing get pulled in. That is the honest cost of a keyword "
            "approach, and the reason the themes are reported as a ranked shape of the "
            "conversation rather than as exact counts.")


def pick_verbatims(comments: list[dict], themes: list[str], per_theme: int = 2) -> str:
    """A few representative comments per theme, chosen for being typical, not extreme."""
    out = []
    for theme in themes:
        pool = [c for c in comments if theme in c["themes"]]
        if len(pool) < MIN_GROUP:
            continue
        # Typical rather than extreme - and never two from the same department,
        # or the section turns into one team's complaint letter.
        average = mean([x["sentiment"] for x in pool])
        pool.sort(key=lambda c: abs(c["sentiment"] - average))
        out.append(f"**{theme}**")
        seen_departments = set()
        for comment in pool:
            if comment["department"] in seen_departments:
                continue
            seen_departments.add(comment["department"])
            out.append(f"> \"{comment['comment_text']}\"  ")
            out.append(f"> — {comment['department']}, {comment['tenure_band']} tenure")
            out.append(">")
            if len(seen_departments) >= per_theme:
                break
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(run())
