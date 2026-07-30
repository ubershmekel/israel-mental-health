"""
Keyword catalog for the Israel Mental Health Trends Index.

Each entry maps one search term to an SDT indicator and a language.
`ANCHORS` are stable, mental-health-unrelated terms included in every
Google Trends request so batches can be rescaled onto a common axis later
(Trends only normalizes values 0-100 within a single request of <=5 terms).

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
    {"term": "התקף חרדה", "language": "he", "indicator": "crisis"},
    {"term": "תסמיני דיכאון", "language": "he", "indicator": "crisis"},
    {"term": "קו חם למניעת התאבדות", "language": "he", "indicator": "crisis"},
    {"term": "עזרה בהתקף פאניקה", "language": "he", "indicator": "crisis"},
    {"term": "ער\"ן", "language": "he", "indicator": "crisis"},
]

# One anchor per language: stable, high-volume, mental-health-unrelated terms
# used in every batch of that language to allow cross-batch rescaling.
ANCHORS = [
    {"term": "weather", "language": "en", "indicator": "anchor"},
    {"term": "מזג אוויר", "language": "he", "indicator": "anchor"},
]


def all_keywords():
    """Every keyword row (indicator terms + anchors) as a flat list."""
    return KEYWORDS + ANCHORS


def batches(batch_size: int = 1):
    """
    Group keywords into Google Trends request batches.

    Each batch contains up to `batch_size` non-anchor keywords from the
    same language, plus that language's anchor term (Trends caps requests
    at 5 terms total, so batch_size should stay <= 4). Defaults to 1 -
    one keyword + the anchor per request - so every network call is a
    single, minimal, easy-to-pace query rather than a multi-keyword
    compare request.
    """
    by_language = {}
    for kw in KEYWORDS:
        by_language.setdefault(kw["language"], []).append(kw)

    anchor_by_language = {a["language"]: a for a in ANCHORS}

    for language, kws in by_language.items():
        anchor = anchor_by_language[language]
        for i in range(0, len(kws), batch_size):
            chunk = kws[i:i + batch_size]
            yield {
                "language": language,
                "anchor": anchor,
                "keywords": chunk,
            }
