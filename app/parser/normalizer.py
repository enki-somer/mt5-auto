from __future__ import annotations

import re

ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\ufeff")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for marker in ZERO_WIDTH:
        cleaned = cleaned.replace(marker, "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in cleaned.split("\n")]
    return "\n".join(line for line in lines if line)


def flatten_text(text: str) -> str:
    return " ".join(normalize_text(text).split())


def uppercase_flat(text: str) -> str:
    return flatten_text(text).upper()


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
