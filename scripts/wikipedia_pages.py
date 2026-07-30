"""Hebrew Wikipedia articles used as mental-health interest signals."""

PAGES = [
    {
        "article": "התקף חרדה",
        "language": "he",
        "indicator": "crisis",
        "label_en": "Anxiety attack",
    },
    {
        # "דיכאון" redirects here. The suggested "דיכאון (טיפול)" page
        # does not exist on Hebrew Wikipedia.
        "article": "דיכאון קליני",
        "language": "he",
        "indicator": "crisis",
        "label_en": "Clinical depression",
    },
    {
        "article": "הפרעת דחק פוסט-טראומטית",
        "language": "he",
        "indicator": "crisis",
        "label_en": "Post-traumatic stress disorder",
    },
]
