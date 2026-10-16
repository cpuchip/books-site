"""neutral.py: the one place the site turns the export's working credits into reader-facing words.

The export's errata name the people and machines that did the work (found_by, and clauses inside evidence).
That is honest data and stays in pd-books (CC0). The site does not print who; it prints how: the credit line
comes from the erratum's kind and status, and the clauses below are rewritten in evidence. tools/outward.py
fails the build on any seat name left anywhere on the site, so a new clause shows up as a red, not a leak.
"""
import re

# (pattern, replacement), applied in order. Longest first where one contains another.
EVIDENCE = [
    (r"Flagged by the claudiverse shelf:", "Flagged by our checking pipeline:"),
    (r"the claudiverse shelf", "our checking pipeline"),
    (r"claudiverse judge(\.py)?", r"our answer checker"),
    (r"claudiverse [A-Za-z_]+\.py", "our checking script"),
    (r"claudiverse adjudication", "our checking pipeline's adjudication"),
    (r"tutor's acceptance run", "the lesson checker's acceptance run"),
    (r"by the books seat \(#[0-9]+\) and again by qwenniverse-fermion", "by two readers independently"),
    (r"by the books seat(?: \(#[0-9]+\)|, #[0-9]+)?", "by a second reader"),  # after the line above, which it would cut in two
    (r"awaiting abacus", "awaiting review"),
    (r"\babacus\b", "a reviewer"),
]

CREDIT = {
    "transcriber_marked": "Marked by Project Gutenberg's proofreaders in the transcription.",
    "confirmed": "Confirmed: found by computation and read against the printed page.",
    "probable": "Probable: found by computation; not yet read against a scan.",
    "candidate": "Candidate: reported, not yet confirmed.",
    "dismissed": "Dismissed after checking; kept so the question is not asked again.",
    "note": "A note on the text, not an erratum.",
}


def evidence(text):
    for pat, rep in EVIDENCE:
        text = re.sub(pat, rep, text)
    return text


def credit(status, kind):
    if status == "confirmed" and kind == "transcription":
        return "Confirmed against a scan of the printed book: the transcription differs, the book is right."
    return CREDIT.get(status, f"Status: {status}.")
