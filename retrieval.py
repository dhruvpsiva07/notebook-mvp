"""Layer 2: pick which chunks go into Claude's context.

Small notebooks are sent whole (long-context stuffing). Larger ones
use BM25 keyword search, so no embedding API is needed for the MVP.
"""
import math
import re
from collections import Counter

CONTEXT_BUDGET = 60_000
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is "
    "it its me my of on or that the their this to was what when where "
    "which who why will with you your".split())


def tokenize(text):
    """Lowercase word tokens with common stopwords removed."""
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class BM25Index:
    """Okapi BM25 ranking over a list of chunk dicts with a 'text' key."""

    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.docs = [Counter(tokenize(c["text"])) for c in chunks]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        total_len = sum(self.lengths)
        self.avg_len = total_len / len(self.lengths) if total_len else 1
        doc_freq = Counter()
        for doc in self.docs:
            doc_freq.update(doc.keys())
        total = len(self.docs)
        self.idf = {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()}

    def search(self, query, k=8):
        """Return up to k chunks ranked by relevance to the query."""
        terms = tokenize(query)
        scored = []
        for i, doc in enumerate(self.docs):
            score = 0.0
            length_norm = 1 - self.b + self.b * self.lengths[i] / self.avg_len
            for term in terms:
                freq = doc.get(term, 0)
                if freq:
                    weight = freq * (self.k1 + 1)
                    score += self.idf[term] * weight / (
                        freq + self.k1 * length_norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [self.chunks[i] for _, i in scored[:k]]


def select_context(chunks, query, budget=CONTEXT_BUDGET, k=8):
    """Choose the chunks to send to Claude for this request.

    query=None (Studio outputs) means "summarize everything", so large
    notebooks get an even sample across all chunks instead of a search.
    """
    total = sum(len(c["text"]) for c in chunks)
    if total <= budget:
        return list(chunks)
    if query:
        hits = BM25Index(chunks).search(query, k)
        if hits:
            return hits
    return _spread(chunks, budget, total)


def _spread(chunks, budget, total):
    average = total / len(chunks)
    count = max(1, int(budget / average))
    step = len(chunks) / count
    return [chunks[int(i * step)] for i in range(count)]
