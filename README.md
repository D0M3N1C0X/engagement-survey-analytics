# Engagement survey analytics: from 2,753 answers to what to do on Monday

An employee engagement survey, analysed end to end — participation and non-response bias,
scores with confidence intervals, a key-driver analysis that survives a bootstrap, and free
text scored with a pipeline that reports its own error rate. Output is an **interactive
dashboard in a single HTML file** and a written read-out.

[![pipeline](https://github.com/D0M3N1C0X/engagement-survey-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/D0M3N1C0X/engagement-survey-analytics/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-1baf7a)
![dashboard](https://img.shields.io/badge/dashboard-one%20HTML%20file-2a78d6)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

> **Synthetic data.** The survey, the answers and the comments are generated with a fixed
> seed by [`src/generate_survey.py`](src/generate_survey.py). No real employee wrote any of
> this. What is meant to be judged is the method.

### ▶ [Open the live dashboard](https://d0m3n1c0x.github.io/engagement-survey-analytics/)

Filter 2,753 survey responses by department, country, level, tenure or work model and watch
every score, interval, theme and verbatim recompute — no install, no login.

**Read the full read-out: [`reports/survey_report.md`](reports/survey_report.md)**

---

## The interactive part

`dashboard.html` is the deliverable an HR team would actually use: filter by department,
country, level, tenure or work model, and every number — scores, confidence intervals,
eNPS, themes, verbatims — recomputes in the browser. No server, no libraries, no build step.

```bash
python3 src/run_all.py && open dashboard.html
```

It also enforces the rule the report is built on: **filter below five respondents and it
refuses to show scores**, masking the tiles as well as the charts. Confidentiality is what
makes people answer honestly, and a dashboard that quietly reports on a team of three is how
a company loses its next survey.

---

## What the analysis found

**Participation is the first finding, not a footnote.** 72.4% responded — but 61% in
Operations against 83% in Finance & Legal, and 57% among shift workers against 79% at a desk.
The people under most pressure are the least likely to answer, so the company scores below
are more likely to be flattering than harsh. That direction of error is stated up front and
carried through the report.

**The headline is an engagement index of 54% favourable and an eNPS of −12.** Career Growth
scores lowest at 32% favourable, Inclusion & Belonging highest at 79%.

![Dimension scores](reports/figures/01_dimension_scores.svg)

**But what scores badly and what matters are different questions.** A relative weight
analysis (Johnson's method — the drivers are far too correlated for raw regression
coefficients) splits the 38% of explained variance across the eight dimensions:

![Impact against performance](reports/figures/04_impact_vs_performance.svg)

- **Manager Support carries 40% of the explained variance** — nearly three times the
  bottom four dimensions combined (14%) — and came first in *every one* of 120 bootstrap
  resamples.
- **Career Growth (19% impact, 32% favourable) and Recognition (14%, 40%)** sit in the
  fix-first quadrant: high impact, low score.
- **Pay & Benefits scores 41% favourable and carries 4% impact.** Pay is the loudest theme
  in the free text and near the bottom of the scores, and it still is not what separates an
  engaged employee from a disengaged one here. That is an uncomfortable finding to present,
  which is exactly why it ships with a bootstrap behind it.

**The company average hides the teams.** Across the 86 teams with at least 15 respondents —
small teams swing too much to compare — the engagement index runs from 18% to 94%, and the
bottom decile sits at 29% against 78% at the top. **34 teams sit significantly below** the
company score
— their whole confidence interval is below it — and teams in the top quartile on Manager
Support score 72% against 36% for the bottom quartile, a 37-point gap inside one company.

**The free text agrees with the numbers.** Across every department-and-theme combination,
the share of comments raising a theme correlates **r = −0.67** with the favourable score on
the matching dimension — two instruments, same story, which is the answer to a leadership
team that wants to dismiss verbatims as the vocal minority.

![Theme sentiment](reports/figures/05_theme_sentiment.svg)

---

## The part most survey projects skip: scoring the text pipeline

Themes come from a keyword lexicon and sentiment from a word list with negation handling —
both in [`src/textlib.py`](src/textlib.py), both readable and arguable, because anything an
HR team publishes from free text has to survive the question *"how did you decide that?"*.

Neither is trusted without a measurement. The generator writes out which themes each comment
was built from, and the analysis scores itself against those labels before quoting anything:

| Measure | Result |
|---|---|
| Comments tagged with at least one theme | 97% of 1,234 verbatims |
| Macro F1 across ten themes | **0.93** |
| Weakest theme (Manager relationship) | comments that mention a manager in passing get pulled in |
| Sentiment vs the labelled tone | 67% of negative, 71% of positive comments correct |
| Respondent's average comment sentiment vs their own eNPS | **r = 0.28** |

That last number is the honest ceiling: good enough to rank themes by tone, nowhere near
good enough to judge an individual comment — so nothing downstream does.

And the F1 has a ceiling of its own worth stating: the verbatims are assembled from a
template bank, so a keyword lexicon has an easier job here than it would on real free text.
The evaluation proves the pipeline is *measured* and that its weak spot is known — not that
0.93 would survive contact with a real corpus.

---

## Method notes

- **Wilson confidence intervals** on every rate, because survey cuts are small and
  favourable rates sit near the ends of the scale where the textbook interval breaks.
- **Two-proportion z-tests** for group comparisons — a department is only reported as below
  average when the difference survives a test.
- **Johnson's relative weights** for driver impact, plus **120 bootstrap resamples** to show
  which parts of the ranking are real. The report says explicitly which dimensions swap
  places and should not be argued about.
- **A confidentiality threshold of five respondents**, enforced in the report, the team
  lists and the dashboard.
- **Association, not causation.** Cross-sectional survey data cannot prove that improving a
  driver raises engagement; the report says so wherever a number could be read as a promise.

Everything is implemented from scratch in [`src/statlib.py`](src/statlib.py) — including a
Jacobi eigenvalue solver, since relative weight analysis needs to decompose the predictor
correlation matrix.

---

## What's inside

```
├── dashboard.html                one self-contained interactive file
├── src/
│   ├── generate_survey.py        synthetic survey: instrument, answers, verbatims
│   ├── surveylib.py              favourable scoring, eNPS, segments, the confidentiality gate
│   ├── statlib.py                Wilson intervals, z-tests, OLS, Jacobi eigen, relative weights
│   ├── textlib.py                tokeniser, theme lexicon, sentiment, TF-IDF, redaction
│   ├── viz.py                    dot plot with CIs, heatmap, quadrant, diverging bars
│   ├── analysis_scores.py        module 1 - participation and scores
│   ├── analysis_drivers.py       module 2 - key driver analysis
│   ├── analysis_text.py          module 3 - free text, scored before it is believed
│   ├── build_dashboard.py        payload + HTML + JS for the dashboard
│   └── run_all.py                the whole pipeline, one command
├── data/                         generated CSVs + data dictionary
└── reports/
    ├── survey_report.md          the written read-out
    └── figures/                  6 SVG charts
```

Four tables: the invite list with every answer, the free-text verbatims, the team roster and
the questionnaire itself. Column-by-column definitions — and an honest list of the effects
deliberately planted in the generator — are in [`data/README.md`](data/README.md).

## Run it

```bash
python3 src/run_all.py
```

Regenerates the data, runs the three analyses, writes six charts, assembles the read-out and
builds the dashboard. Around twelve seconds, and **no packages to install** — Python 3.10 or
newer and nothing else.

To publish the dashboard as a live page, enable GitHub Pages with "GitHub Actions" as the
source; [`.github/workflows/pages.yml`](.github/workflows/pages.yml) deploys it on every
push to `main`.

## About

Built by **Domenico Perroni** — HR Operations & Advisory, People Analytics. Kraków, Poland.
[LinkedIn](https://www.linkedin.com/in/domenico-perroni-8780981b8)

**Companion project:** [hr-people-analytics](https://github.com/D0M3N1C0X/hr-people-analytics)
— attrition drivers, pay equity under the EU Pay Transparency Directive, and HR service-desk
performance on the same zero-dependency footing.

MIT licensed. Reuse anything here.
