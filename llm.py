"""Layers 3-5: grounding prompts, citation parsing and the Claude client."""
import os
import re

import anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"
CITATION_RE = re.compile(r"\[S(\d+)\]")

GROUNDING_RULES = (
    "Use ONLY the numbered source excerpts provided. Do not use outside "
    "knowledge. After every claim, cite the excerpt(s) it came from, like "
    "[S1] or [S2][S4]. If the excerpts do not answer the question, say so "
    "plainly instead of guessing.")

CHAT_SYSTEM = "You are a careful research assistant. " + GROUNDING_RULES

STUDIO_SYSTEM = (
    "You turn source material into study and research documents. "
    + GROUNDING_RULES)

STUDIO_KINDS = {
    "study_guide": {
        "title": "Study guide",
        "instructions": (
            "Write a study guide: the key concepts with short "
            "explanations, important terms with definitions, and five "
            "practice questions with answers."),
    },
    "faq": {
        "title": "FAQ",
        "instructions": (
            "Write 6-10 questions a reader would likely ask about these "
            "sources, each with a concise answer."),
    },
    "briefing": {
        "title": "Briefing doc",
        "instructions": (
            "Write a briefing document: a one-paragraph executive "
            "summary, then the main themes, key facts and open questions."),
    },
}


def format_context(chunks):
    """Number each chunk so Claude can cite it as [S<n>]."""
    blocks = []
    for n, chunk in enumerate(chunks, start=1):
        header = f"[S{n}] (from {chunk['source_name']})"
        blocks.append(f"{header}\n{chunk['text']}")
    return "\n\n".join(blocks)


def build_chat_prompt(question, chunks):
    """Return (system, user) prompts for a grounded chat answer."""
    user = (
        f"<excerpts>\n{format_context(chunks)}\n</excerpts>\n\n"
        f"Question: {question}")
    return CHAT_SYSTEM, user


def build_studio_prompt(kind, chunks):
    """Return (system, user) prompts for a Studio output."""
    instructions = STUDIO_KINDS[kind]["instructions"]
    user = (
        f"<excerpts>\n{format_context(chunks)}\n</excerpts>\n\n"
        f"Task: {instructions} Format the result in Markdown with "
        "headings and lists.")
    return STUDIO_SYSTEM, user


def extract_citations(text, count):
    """Sorted, unique excerpt numbers cited in text that actually exist."""
    numbers = {int(n) for n in CITATION_RE.findall(text)}
    return sorted(n for n in numbers if 1 <= n <= count)


class ClaudeClient:
    """Thin wrapper around the Anthropic Messages API."""

    def __init__(self, model=None):
        self.model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
        self._client = None

    def complete(self, system, user, max_tokens=2000):
        """Send one prompt and return the text of Claude's reply."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        if self._client is None:
            self._client = anthropic.Anthropic()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(
            block.text for block in response.content
            if block.type == "text")
