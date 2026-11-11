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
import math
from collections import Counter, defaultdict

import textlib as T
import viz
from statlib import mean, pearson
from surveylib import (DATA, FIGURES, MIN_GROUP, PRIVATE_MODE, driver_items,
                       load_comments, load_instrument, load_responses, md_table, pct,
                       respondent_favourable, respondents)

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
    path = DATA / "comment_themes_truth.csv"
    if not path.exists():
        return {}
    return {r["comment_id"]: r for r in csv.DictReader(
        path.open(encoding="utf-8-sig", newline=""))}


def evaluate_tagger(comments: list[dict], truth: dict[str, dict]) -> list[dict]:
    """Precision, recall and F1 per theme against the labelled set."""
    tp, fp, fn = Counter(), Counter(), Counter()
    for comment in comments:
        if comment["comment_id"] not in truth:
            continue
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

    comments = enrich(load_comments(), responses)
    truth = load_truth()
    critical = [c for c in comments if c["question"] == "what_to_change"]

    if not comments:
        return "## 3. What people wrote\n\nNo comment file was supplied; free-text analysis was skipped."
    if not critical:
        return ("## 3. What people wrote\n\nNo `what_to_change` comments were supplied; "
                "department-level free-text comparisons were skipped.")

    critical_commenters = {c["response_id"] for c in critical}
    if PRIVATE_MODE and len(critical_commenters) < MIN_GROUP:
        return ("## 3. What people wrote\n\nFree-text aggregates are withheld because fewer "
                f"than {MIN_GROUP} distinct respondents contributed to the reportable question.")

    commenters = {c["response_id"] for c in comments}
    coverage = sum(1 for c in comments if c["themes"]) / len(comments)

    # ---- evaluation first ----------------------------------------------
    evaluation = evaluate_tagger(comments, truth) if truth else []
    macro_f1 = mean([r["f1"] for r in evaluation]) if evaluation else None
    labelled_comment_count = sum(1 for c in comments if c["comment_id"] in truth)
    tone_hits = defaultdict(lambda: [0, 0])
    if truth:
        for comment in comments:
            if comment["comment_id"] not in truth:
                continue
            actual = truth[comment["comment_id"]]["true_tone"]
            tone_hits[actual][1] += 1
            tone_hits[actual][0] += comment["tone"] == actual

    by_person = defaultdict(list)
    for comment in comments:
        by_person[comment["response_id"]].append(comment["sentiment"])
    pairs = [(mean(v), responses[rid]["enps"]) for rid, v in by_person.items()
             if responses[rid]["enps"] is not None]
    sentiment_validity = (pearson([a for a, _ in pairs], [b for _, b in pairs])
                          if len(pairs) >= MIN_GROUP else float("nan"))
    sentiment_correlation_reportable = len(pairs) >= MIN_GROUP and math.isfinite(sentiment_validity)

    # ---- volume and tone -----------------------------------------------
    comments_by_theme = defaultdict(list)
    for comment in comments:
        for theme in comment["themes"]:
            comments_by_theme[theme].append(comment)
    authors_by_theme = {theme: {c["response_id"] for c in group}
                        for theme, group in comments_by_theme.items()}
    theme_counts = Counter({theme: len(authors) for theme, authors in authors_by_theme.items()
                            if len(authors) >= MIN_GROUP})
    theme_sentiment = {}
    for theme in theme_counts:
        by_author = defaultdict(list)
        for comment in comments_by_theme[theme]:
            by_author[comment["response_id"]].append(comment["sentiment"])
        theme_sentiment[theme] = mean([mean(scores) for scores in by_author.values()])
    ordered = sorted(theme_counts, key=lambda t: theme_sentiment[t])

    viz.diverging_bars(
        FIGURES / "05_theme_sentiment.svg",
        ordered, [theme_sentiment[t] for t in ordered], [theme_counts[t] for t in ordered],
        "How people talk about each theme",
        f"Mean sentiment of the {len(comments):,} verbatims mentioning each theme "
        f"(count in brackets)",
        xlabel="negative  <-  net sentiment  ->  positive")

    # ---- theme share by department --------------------------------------
    department_commenters = {
        dept: {c["response_id"] for c in critical if c["department"] == dept}
        for dept in {c["department"] for c in critical}
    }
    departments = sorted(dept for dept, authors in department_commenters.items()
                         if len(authors) >= MIN_GROUP)
    themes_ranked = [t for t, _ in theme_counts.most_common(8)]
    matrix = []
    for theme in themes_ranked:
        row = []
        for dept in departments:
            group = [c for c in critical if c["department"] == dept]
            commenters_in_group = {c["response_id"] for c in group}
            theme_authors = {c["response_id"] for c in group if theme in c["themes"]}
            row.append(len(theme_authors) / len(commenters_in_group)
                       if len(commenters_in_group) >= MIN_GROUP and len(theme_authors) >= MIN_GROUP
                       else float("nan"))
        matrix.append(row)

    viz.heatmap(
        FIGURES / "06_theme_by_department.svg",
        themes_ranked, departments, matrix,
        "What each department asks to change",
        "Share of distinct commenters mentioning each theme; cells below five contributors are hidden",
        note=f"{len(critical):,} critical comments")

    # ---- detractors against promoters -----------------------------------
    detractor_comments = [c for c in critical if c["enps"] is not None and c["enps"] <= 6]
    promoter_comments = [c for c in critical if c["enps"] is not None and c["enps"] >= 9]
    detractor_authors = {c["response_id"] for c in detractor_comments}
    promoter_authors = {c["response_id"] for c in promoter_comments}
    lift = []
    for theme in themes_ranked:
        d_authors = {c["response_id"] for c in detractor_comments if theme in c["themes"]}
        p_authors = {c["response_id"] for c in promoter_comments if theme in c["themes"]}
        if min(len(detractor_authors), len(promoter_authors), len(d_authors), len(p_authors)) < MIN_GROUP:
            continue
        d = len(d_authors) / len(detractor_authors)
        p = len(p_authors) / len(promoter_authors)
        lift.append({"theme": theme, "detractors": d, "promoters": p,
                     "lift": d / p if p else float("inf")})
    lift.sort(key=lambda r: -r["lift"])

    # ---- do the words agree with the numbers ----------------------------
    text_points, score_points = [], []
    for theme in themes_ranked:
        dimension = THEME_TO_DIMENSION[theme]
        for dept in departments:
            group = [c for c in critical if c["department"] == dept]
            commenters_in_group = {c["response_id"] for c in group}
            theme_authors = {c["response_id"] for c in group if theme in c["themes"]}
            people = [r for r in answered if r["department"] == dept]
            if (len(commenters_in_group) < MIN_GROUP or len(theme_authors) < MIN_GROUP
                    or len(people) < MIN_GROUP):
                continue
            person_scores = [score for person in people
                             if (score := respondent_favourable(person, items_by_dim[dimension])) is not None]
            if len(person_scores) < MIN_GROUP:
                continue
            text_points.append(len(theme_authors) / len(commenters_in_group))
            score_points.append(mean(person_scores))
    triangulation = pearson(text_points, score_points) if len(text_points) >= MIN_GROUP else float("nan")
    triangulation_reportable = len(text_points) >= MIN_GROUP and math.isfinite(triangulation)
    triangulation_text = (
        f"Across {len(text_points)} eligible department-and-theme combinations, the share of "
        f"distinct commenters raising a theme correlates descriptively at **r = {triangulation:.2f}** "
        "with the favourable score on the matching survey dimension. This is an exploratory "
        "cross-check, not evidence that both measures are valid or that text represents the workforce."
        if triangulation_reportable else
        "Too few reportable department-and-theme combinations or insufficient variation are available for a descriptive comparison."
    )

    # ---- distinctive language -------------------------------------------
    if PRIVATE_MODE:
        distinctive = {}
    else:
        docs = {dept: [c["comment_text"] for c in critical if c["department"] == dept]
                for dept in departments}
        distinctive = T.tfidf_by_group(docs, top_n=5)

    # ---- verbatims -------------------------------------------------------
    quotable = ("Verbatim text is withheld from local exports. Theme and sentiment aggregates are "
                "reported only when at least five distinct respondents contribute."
                if PRIVATE_MODE else pick_verbatims(critical, themes_ranked[:4]))

    # ---- narrative --------------------------------------------------------
    detractor_denominator = len({
        r["response_id"] for r in answered if r["enps"] is not None and r["enps"] <= 6})
    promoter_denominator = len({
        r["response_id"] for r in answered if r["enps"] is not None and r["enps"] >= 9})
    detractor_rate = len(detractor_authors) / detractor_denominator if detractor_denominator else 0.0
    promoter_rate = len(promoter_authors) / promoter_denominator if promoter_denominator else 0.0
    rate_groups_reportable = (
        detractor_denominator >= MIN_GROUP and promoter_denominator >= MIN_GROUP
        and len(detractor_authors) >= MIN_GROUP and len(promoter_authors) >= MIN_GROUP
    )
    comment_rate_text = (
        f"Detractors wrote reportable comments at **{detractor_rate:.2f} per detractor** "
        f"and promoters at **{promoter_rate:.2f} per promoter**"
        if detractor_denominator and promoter_denominator
        and (not PRIVATE_MODE or rate_groups_reportable) else
        "The detractor/promoter comment-rate comparison is withheld or unavailable."
    )
    rate_ratio = (f" ({detractor_rate / promoter_rate:.1f} times the promoter rate)"
                  if promoter_rate and (not PRIVATE_MODE or rate_groups_reportable) else "")

    if PRIVATE_MODE and truth:
        evaluation_note = (f"A hand-labelled reference set was supplied for {labelled_comment_count:,} "
                           "comments. Metrics below apply only to that labelled subset.")
        evaluation_limit = ("A labelled subset from this dataset is not external validation; review "
                            "sampling, class balance and annotator agreement before relying on it.")
    elif truth:
        evaluation_note = (f"This synthetic corpus has hand-labelled references for "
                           f"{labelled_comment_count:,} comments:")
        evaluation_limit = ("These demo comments are assembled from a template bank, which makes "
                            "a keyword lexicon's job easier than on real free text. The measured "
                            "scores are not an estimate of performance on employee comments.")
    else:
        evaluation_note = "No hand-labelled ground truth was supplied, so accuracy is not estimated for this corpus."
        evaluation_limit = ("No predictive quality claim can be made without a representative, "
                            "independently labelled sample and an annotation protocol.")
    tone_reference = ("On the supplied labelled subset it gets " if PRIVATE_MODE else
                      "On this synthetic labelled corpus it gets ")

    md = [
        "## 3. What people wrote",
        "",
        f"**{len(comments):,} comments** from **{len(commenters):,} of {len(answered):,}** "
        f"respondents ({pct(len(commenters) / len(answered))}). {comment_rate_text}{rate_ratio}. "
        "Comment participation differs between eNPS groups, so theme frequencies are "
        "descriptive and should not be read as workforce prevalence.",
        "",
        "### First: does the text pipeline actually work?",
        "",
        "Theme tagging uses a keyword lexicon that lives in "
        "[`src/textlib.py`](../src/textlib.py) and can be read, argued with and changed. "
        f"It tagged at least one theme on **{pct(coverage)}** of comments. "
        + evaluation_note,
        "",
        (md_table(["Theme", "Precision", "Recall", "F1", "False positives", "Misses"],
                  [[r["theme"], f"{r['precision']:.2f}", f"{r['recall']:.2f}",
                    f"**{r['f1']:.2f}**", r["fp"], r["fn"]] for r in evaluation],
                  align="lrrrrr") if evaluation else "Accuracy table unavailable for this dataset."),
        "",
        (f"Macro F1 is **{macro_f1:.2f}**. " + weakest_note(evaluation)
         if evaluation else ""),
        "",
        f"*{evaluation_limit}*",
        "",
        "Sentiment is a word list with negation handling, not a language model. "
        + (tone_reference
           + ", ".join(f"**{pct(hits / total)}** of {tone} comments right"
                       for tone, (hits, total) in sorted(tone_hits.items())) + ". "
           if tone_hits else "No labelled sentiment reference was supplied. ")
        + (f"Across {len(pairs)} respondents with comments and eNPS, mean comment sentiment "
           f"correlates descriptively at **r = {sentiment_validity:.2f}** with eNPS. This is "
           "not an external validation and is not used to infer individual attitudes."
           if sentiment_correlation_reportable else
           "Too few respondents have both comments and eNPS, or there is insufficient variation, to report a sentiment correlation."),
        "",
        "### Volume and tone by theme",
        "",
        "![Theme sentiment](figures/05_theme_sentiment.svg)",
        "",
        md_table(["Theme", "Distinct commenters", "Share of commenters", "Mean sentiment"],
                 [[theme, f"{theme_counts[theme]:,}",
                   pct(theme_counts[theme] / max(1, len(commenters))),
                   f"{theme_sentiment[theme]:+.2f}"]
                  for theme in sorted(theme_counts, key=lambda t: -theme_counts[t])],
                 align="lrrr"),
        "",
        "### Where the complaints concentrate",
        "",
        "![Theme by department](figures/06_theme_by_department.svg)",
        "",
        md_table(["Theme", "Share of detractor commenters", "Share of promoter commenters",
                  "Ratio"],
                 [[r["theme"], pct(r["detractors"]), pct(r["promoters"]),
                   f"**{r['lift']:.1f}x**" if r["lift"] != float("inf") else "-"]
                  for r in lift[:6]], align="lrrr"),
        "",
        (f"**{lift[0]['theme']}** appears in {pct(lift[0]['detractors'])} of detractor "
         f"commenters against {pct(lift[0]['promoters'])} of promoter commenters - "
         f"**{lift[0]['lift']:.1f} times** as often. This descriptive contrast is exploratory."
         if lift else "Theme contrasts by eNPS group are withheld because at least one side has fewer "
         f"than {MIN_GROUP} distinct contributors for each reportable theme."),
        "",
        "### Do the words agree with the numbers?",
        "",
        triangulation_text,
        "",
        "### The language each department uses",
        "",
        *([] if PRIVATE_MODE else [
            md_table(["Department", "Distinctive terms in their 'what should change' comments"],
                     [[dept, ", ".join(f"`{term}`" for term, _score in terms)]
                      for dept, terms in sorted(distinctive.items())], align="ll"),
            "",
            "These terms are weighted by how much more one group uses them than others.",
            "",
            "### In their own words",
            "",
            f"Verbatims are published only from groups with at least {MIN_GROUP} distinct respondents; "
            "automated redaction is imperfect and does not make source comments anonymous.",
            "",
            quotable,
            "",
        ]),
        *( [quotable, ""] if PRIVATE_MODE else []),
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
            out.append(f"> \"{comment['comment_text']}\"")
            out.append(">")
            out.append(f"> — {comment['department']}, {comment['tenure_band']} tenure")
            out.append(">")
            if len(seen_departments) >= per_theme:
                break
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print(run())
