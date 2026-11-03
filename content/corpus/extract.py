"""Practice text from public-domain linguistics books on Project Gutenberg (see sources.md).

    python3 extract.py pg12629.txt pg53038.txt > prose.txt

Keeps whole sentences and clauses cut at punctuation, made of plain words only
(letters, spaces, commas), 14 to 70 characters long, each ending in a full stop.
"""
import re
import sys

BAD = {"chapter", "footnote", "gutenberg", "ibid", "etc", "illustration", "page", "vol"}


def body(path):
    text = open(path, encoding="utf-8").read().replace("\r", "")
    return text[text.index("\n", text.index("*** START OF")):text.index("*** END OF")]


def cut_short(words):
    """Split at an abbreviation: 'He rejects Fr.', 'Kroeber and R.' (a short capitalised
    last word, or an initial anywhere)."""
    last = words[-1]
    return (last[0].isupper() and len(last) <= 4 and last != "I") or any(len(w) == 1 and w not in ("I", "a", "A") for w in words)


def plain(words):
    return not cut_short(words) and (all(re.fullmatch(r"[A-Za-z]+", w) for w in words)
            and not any(w.isupper() and len(w) > 1 for w in words)
            and not BAD & {w.lower() for w in words})


found = {}
for path in sys.argv[1:]:
    for paragraph in body(path).split("\n\n"):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if len(paragraph) < 200 or "[" in paragraph:  # headings, notes, tables
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph):
            words = sentence.rstrip(".").replace(",", "").split()
            if 28 <= len(sentence) <= 70 and re.fullmatch(r"[A-Z][A-Za-z ,]+[a-z]\.", sentence) and len(words) >= 6 and plain(words):
                found[sentence] = None
            for clause in re.split(r"\s*[,;:.!?()\"—–-]+\s*", sentence):
                words = clause.split()
                if 13 <= len(clause) <= 62 and len(words) >= 3 and plain(words):
                    found[clause[0].upper() + clause[1:] + "."] = None
print("\n".join(found))
