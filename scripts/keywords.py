"""
Keyword catalog for the Israel Mental Health Trends Index.

Each entry maps one search term to an SDT indicator and a language.

`ANCHORS` were originally meant to be included in every Google Trends
request so batches could be rescaled onto a common axis later (Trends only
normalizes values 0-100 within a single request). In practice "weather" is
FAR too large a topic for this: pairing a niche mental-health phrase with
it just rounds the keyword down to 0 every time, regardless of its real
volume, because Trends normalizes to the larger term's peak. So batches()
currently queries each keyword ALONE (self-normalized) - that's enough to
tell whether a term has any real search pattern in Israel at all. Proper
cross-keyword rescaling (needed before terms can be compared/combined into
an index) needs a right-sized anchor chosen after we know the rough
magnitude of the real keywords, not a placeholder chosen up front - that's
a follow-up problem, not solved yet.

See README.md for the rationale behind each indicator and term.
"""

INDICATORS = ["autonomy", "competence", "relatedness", "crisis"]

KEYWORDS = [
    # --- Autonomy (אוטונומיה) ---
    {"term": "feeling trapped", "language": "en", "indicator": "autonomy"},
    {"term": "lost control of my life", "language": "en", "indicator": "autonomy"},
    {"term": "decision fatigue", "language": "en", "indicator": "autonomy"},
    {"term": "quit my job", "language": "en", "indicator": "autonomy"},
    {"term": "burnout no choice", "language": "en", "indicator": "autonomy"},
    {"term": "תחושת מלכוד", "language": "he", "indicator": "autonomy"},
    {"term": "איבדתי שליטה על החיים", "language": "he", "indicator": "autonomy"},
    {"term": "עייפות החלטות", "language": "he", "indicator": "autonomy"},
    {"term": "להתפטר מהעבודה", "language": "he", "indicator": "autonomy"},
    {"term": "אין לי ברירה", "language": "he", "indicator": "autonomy"},

    # --- Competence / Ability (מסוגלות) ---
    {"term": "burnout symptoms", "language": "en", "indicator": "competence"},
    {"term": "can't cope", "language": "en", "indicator": "competence"},
    {"term": "how to stop procrastinating", "language": "en", "indicator": "competence"},
    {"term": "feeling overwhelmed", "language": "en", "indicator": "competence"},
    {"term": "imposter syndrome", "language": "en", "indicator": "competence"},
    {"term": "תסמיני שחיקה", "language": "he", "indicator": "competence"},
    {"term": "לא מסתדרת", "language": "he", "indicator": "competence"},
    {"term": "איך להפסיק לדחיין", "language": "he", "indicator": "competence"},
    {"term": "תחושת עומס", "language": "he", "indicator": "competence"},
    {"term": "תסמונת המתחזה", "language": "he", "indicator": "competence"},

    # --- Relatedness / Belonging (שייכות) ---
    {"term": "feeling lonely", "language": "en", "indicator": "relatedness"},
    {"term": "loneliness help", "language": "en", "indicator": "relatedness"},
    {"term": "no friends", "language": "en", "indicator": "relatedness"},
    {"term": "support group near me", "language": "en", "indicator": "relatedness"},
    {"term": "social isolation", "language": "en", "indicator": "relatedness"},
    {"term": "מרגישה בודדה", "language": "he", "indicator": "relatedness"},
    {"term": "עזרה לבדידות", "language": "he", "indicator": "relatedness"},
    {"term": "אין לי חברים", "language": "he", "indicator": "relatedness"},
    {"term": "קבוצת תמיכה", "language": "he", "indicator": "relatedness"},
    {"term": "בידוד חברתי", "language": "he", "indicator": "relatedness"},

    # --- Crisis / distress (cross-cutting severity signal) ---
    {"term": "anxiety attack", "language": "en", "indicator": "crisis"},
    {"term": "depression symptoms", "language": "en", "indicator": "crisis"},
    {"term": "suicide hotline", "language": "en", "indicator": "crisis"},
    {"term": "panic attack help", "language": "en", "indicator": "crisis"},
    {"term": "therapist near me", "language": "en", "indicator": "crisis"},
    {"term": "mental health help", "language": "en", "indicator": "crisis"},
    {"term": "התקף חרדה", "language": "he", "indicator": "crisis"},
    {"term": "תסמיני דיכאון", "language": "he", "indicator": "crisis"},
    {"term": "קו חם למניעת התאבדות", "language": "he", "indicator": "crisis"},
    {"term": "עזרה בהתקף פאניקה", "language": "he", "indicator": "crisis"},
    {"term": "ער\"ן", "language": "he", "indicator": "crisis"},
    {"term": "עזרה נפשית", "language": "he", "indicator": "crisis"},
]

# NOTE: not currently used by batches() - see module docstring. Kept here
# as candidates for a future, properly-scaled rescaling step.
ANCHORS = [
    {"term": "weather", "language": "en", "indicator": "anchor"},
    {"term": "מזג אוויר", "language": "he", "indicator": "anchor"},
]


def all_keywords():
    """Every keyword row (indicator terms + anchors) as a flat list."""
    return KEYWORDS + ANCHORS


def batches():
    """
    Yield one Google Trends request per keyword, queried alone (no anchor
    term) so it's self-normalized - the only thing we're checking right
    now is whether a term has any real search pattern in Israel at all.
    """
    for kw in KEYWORDS:
        yield {
            "language": kw["language"],
            "anchor": None,
            "keywords": [kw],
        }
