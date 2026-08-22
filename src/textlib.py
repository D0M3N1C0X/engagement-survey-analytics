"""
Text analytics for survey verbatims - written from scratch, no NLP library.

The approach is deliberately transparent rather than clever. Everything an HR
team publishes from free text has to survive the question "how did you decide
that?", which rules out anything nobody can inspect. So themes come from a
keyword lexicon that lives in this file and can be argued with, sentiment
comes from a word list with negation handling, and every step reports its own
coverage and its own error rate instead of assuming it worked.

What this deliberately does not do: infer anything about an individual. The
unit of analysis is a theme across a group, never a person.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

TOKEN_RE = re.compile(r"[a-z][a-z'\-]+")

STOPWORDS = {
    "a", "about", "above", "after", "again", "all", "also", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "could", "did", "do", "does", "doing", "done", "down", "during", "each",
    "even", "every", "for", "from", "further", "get", "gets", "getting", "go", "goes", "going",
    "had", "has", "have", "having", "he", "her", "here", "hers", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "like", "make", "makes", "many", "may",
    "me", "might", "more", "most", "much", "must", "my", "of", "off", "on", "once", "one",
    "only", "or", "other", "our", "ours", "out", "over", "own", "put", "same", "she", "should",
    "so", "some", "still", "such", "than", "that", "the", "their", "theirs", "them", "then",
    "there", "these", "they", "thing", "things", "this", "those", "through", "to", "too",
    "under", "until", "up", "us", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "would", "you", "your", "yours",
}

# Lemmatisation-lite. It is a set of suffix rules, not a real lemmatiser, and
# it is wrong on irregular verbs - acceptable when the output is a ranked list
# of themes rather than a parse tree.
SUFFIXES = (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("s", ""))
KEEP_WHOLE = {"process", "business", "loss", "less", "boss", "access", "progress", "pass",
              "bands", "hours", "needs", "means", "always", "sales"}


def normalise(token: str) -> str:
    if token in KEEP_WHOLE or len(token) <= 3:
        return token
    for suffix, replacement in SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + replacement
    return token


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    tokens = [normalise(t) for t in TOKEN_RE.findall(text.lower())]
    return [t for t in tokens if not drop_stopwords or t not in STOPWORDS]


def bigrams(tokens: list[str]) -> list[str]:
    return [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------

# The lexicon is the analysis. Keeping it here, in plain sight, is what lets a
# works council or an HR director challenge a number and be answered.
# Phrases are matched against the raw lower-cased text; single terms against
# the normalised tokens.
THEME_LEXICON: dict[str, dict[str, list[str]]] = {
    "Workload & staffing": {
        "phrases": ["short-staffed", "short staffed", "keep up", "not sustainable",
                    "enough people", "extra hours", "no capacity", "cover"],
        "terms": ["workload", "overtime", "firefighting", "understaffed", "pressure",
                  "capacity", "replaced", "holiday", "burnout", "shift"],
    },
    "Manager relationship": {
        "phrases": ["one to one", "my manager", "team lead", "line manager"],
        "terms": ["manager", "supervisor", "feedback", "supportive", "cancels"],
    },
    "Career & progression": {
        "phrases": ["career path", "next role", "next one", "development plan",
                    "training budget", "hire externally", "internal move"],
        "terms": ["promotion", "progress", "career", "grade", "development", "training",
                  "learn", "growth", "opportunity"],
    },
    "Recognition": {
        "phrases": ["good work", "shout-out", "shout out", "thank you", "never mentioned"],
        "terms": ["recognition", "recognised", "recognise", "appreciated", "noticed",
                  "credit", "praise"],
    },
    "Pay & benefits": {
        "phrases": ["pay band", "cost of living", "paid fairly", "base salary"],
        "terms": ["salary", "pay", "paid", "inflation", "benefit", "pension", "bonus",
                  "compensation", "money"],
    },
    "Leadership & communication": {
        "phrases": ["town hall", "senior leader", "hear about decisions", "strategy change"],
        "terms": ["leadership", "strategy", "direction", "transparency", "communicate",
                  "communication", "decision", "reorganisation", "restructure"],
    },
    "Tools & process": {
        "phrases": ["approval process", "do not talk to each other", "getting access"],
        "terms": ["system", "tool", "process", "approval", "access", "software", "admin",
                  "bureaucracy", "rekey"],
    },
    "Flexibility & workplace": {
        "phrases": ["office rule", "work from home", "shift pattern", "school hours",
                    "video call"],
        "terms": ["hybrid", "remote", "commute", "flexibility", "office", "onsite"],
    },
    "Inclusion & voice": {
        "phrases": ["my opinion", "raise a concern", "same voices", "look out for each other",
                    "treated fairly"],
        "terms": ["inclusive", "welcoming", "belong", "voice", "respect", "excluded",
                  "language", "english"],
    },
    "Joining & onboarding": {
        "phrases": ["first week", "first month", "onboarding buddy", "induction"],
        "terms": ["onboarding", "induction", "buddy", "laptop", "starter"],
    },
}


def tag_themes(text: str) -> list[str]:
    """Every theme whose lexicon matches. Comments can carry more than one."""
    lower = text.lower()
    tokens = set(tokenize(text))
    found = []
    for theme, lexicon in THEME_LEXICON.items():
        if any(p in lower for p in lexicon["phrases"]) or \
           any(normalise(t) in tokens for t in lexicon["terms"]):
            found.append(theme)
    return found


# --------------------------------------------------------------------------
# Sentiment
# --------------------------------------------------------------------------

_POSITIVE_RAW = {
    "good", "great", "excellent", "support", "supportive", "help", "helpful", "useful",
    "clear", "fair", "fairly", "respect", "trust", "value", "valued", "proud", "genuine",
    "genuinely", "welcoming", "easier", "easy", "improve", "improved", "better", "best",
    "saved", "save", "flexible", "flexibility", "honest", "openly", "recognised",
    "recognise", "appreciate", "appreciated", "protect", "protects", "supported",
    "welcome", "smooth", "reliable", "positive", "pleasure",
}

_NEGATIVE_RAW = {
    "short-staffed", "understaffed", "overtime", "firefighting", "pressure", "refused",
    "postponed", "cancel", "cancels", "avoid", "avoids", "secret", "filtered", "excludes",
    "exclude", "problem", "problems", "issue", "issues", "nothing", "never", "unsustainable",
    "impossible", "difficult", "hard", "worse", "worst", "stop", "stopped", "late", "slow",
    "confusing", "unclear", "unfair", "ignored", "ignore", "burnout", "leave", "leaving",
    "elsewhere", "frustrating", "frustrated", "broken", "wrong", "bureaucracy",
    "delay", "delays", "chaos", "shortage", "excuse", "backlog", "waiting", "waste",
    "pointless", "stress", "stressed", "exhausted", "micromanage", "favouritism",
    "blocked", "stuck", "silo", "twice", "longer", "chaotic", "excluded", "refuse",
    "exhausting", "overwhelmed", "unsustainable", "understaffing",
}

# Both lexicons are stored in the same normalised form the tokeniser produces.
# Without this pass, entries like "short-staffed" or "frustrated" would sit in
# the set and never match anything, because the tokeniser hands over
# "short-staff" and "frustrat" - a silent failure that costs recall and shows
# up nowhere in the output.
POSITIVE = {normalise(w) for w in _POSITIVE_RAW}
NEGATIVE = {normalise(w) for w in _NEGATIVE_RAW}

NEGATORS = {normalise(w) for w in {"not", "no", "never", "nobody", "nothing", "without",
                                   "hardly", "rarely", "cannot", "dont", "doesnt"}}
NEGATION_WINDOW = 3

# Weight given to a negator that has no sentiment word to flip. In feedback
# text, bare negation almost always marks the absence of something wanted -
# "no visible route", "has not kept up", "systems do not talk to each other" -
# and without this rule 42% of complaints score exactly zero. It is a
# heuristic, and it is the first thing to check when a score looks wrong.
BARE_NEGATION_WEIGHT = 0.5


def sentiment(text: str) -> float:
    """
    Net sentiment in [-1, 1].

    A word list gets tone roughly right and irony completely wrong. That is
    fine for ranking themes by how positively people talk about them; it is
    not fine for judging a comment, and the report says so.
    """
    tokens = [normalise(t) for t in TOKEN_RE.findall(text.lower())]
    positive = negative = 0.0
    attached_negators = set()

    for i, token in enumerate(tokens):
        polarity = 1 if token in POSITIVE else -1 if token in NEGATIVE else 0
        if not polarity:
            continue
        window = range(max(0, i - NEGATION_WINDOW), i)
        negators = [j for j in window if tokens[j] in NEGATORS]
        if negators:
            polarity *= -1
            attached_negators.update(negators)
        if polarity > 0:
            positive += 1
        else:
            negative += 1

    for i, token in enumerate(tokens):
        if token in NEGATORS and i not in attached_negators and token not in NEGATIVE:
            negative += BARE_NEGATION_WEIGHT

    total = positive + negative
    return (positive - negative) / total if total else 0.0


def sentiment_label(score: float) -> str:
    return "positive" if score > 0.2 else "negative" if score < -0.2 else "mixed"


# --------------------------------------------------------------------------
# Distinctive language
# --------------------------------------------------------------------------

def tfidf_by_group(docs: dict[str, list[str]], top_n: int = 6,
                   min_count: int = 3) -> dict[str, list[tuple[str, float]]]:
    """
    Terms that distinguish what one group says from what everyone else says.

    Plain frequency just returns the same words for every group ("work",
    "team"); weighting by inverse document frequency across groups surfaces
    the language that is actually specific to each one.
    """
    counts = {g: Counter(t for d in texts for t in tokenize(d) + bigrams(tokenize(d)))
              for g, texts in docs.items()}
    n_groups = len(counts)
    appears = Counter()
    for counter in counts.values():
        appears.update(set(counter))

    out = {}
    for group, counter in counts.items():
        total = sum(counter.values()) or 1
        scored = []
        for term, count in counter.items():
            if count < min_count or " " in term and count < min_count + 1:
                continue
            idf = math.log(n_groups / appears[term]) + 1e-9
            scored.append((term, count / total * idf))
        out[group] = sorted(scored, key=lambda kv: -kv[1])[:top_n]
    return out


# --------------------------------------------------------------------------
# Publication controls
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
NAME_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+")


def redact(text: str) -> tuple[str, bool]:
    """
    Strip anything that identifies a person before a verbatim is published.

    The synthetic corpus contains no personal data, so this changes nothing
    here - it exists because a real corpus always does, and because the number
    of redactions is itself something to report.
    """
    original = text
    text = EMAIL_RE.sub("[removed]", text)
    text = PHONE_RE.sub("[removed]", text)
    text = NAME_RE.sub("[name removed]", text)
    return text, text != original


def theme_matrix(comments: list[dict]) -> dict[str, list[dict]]:
    """theme -> the comments carrying it."""
    out: dict[str, list[dict]] = defaultdict(list)
    for comment in comments:
        for theme in comment["themes"]:
            out[theme].append(comment)
    return dict(out)
