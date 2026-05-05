"""Text statistics helpers."""

import re


def strip_markdown(text):
    """Remove common Markdown markers before counting readable text."""
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]+", "", text)
    return text


def count_text_units(text):
    """Count Chinese-friendly readable units.

    Chinese/Japanese/Korean characters count one by one. Latin words and
    numbers count by word/number sequence. Punctuation, Markdown syntax,
    whitespace, and emoji are ignored.
    """
    text = strip_markdown(text)
    cjk_chars = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", text)
    latin_words = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", text)
    numbers = re.findall(r"\d+(?:[.,]\d+)*", text)
    return len(cjk_chars) + len(latin_words) + len(numbers)
