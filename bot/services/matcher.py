"""Fuzzy name matcher for /guess attempts.

Uses rapidfuzz to compare the user's guess against:
  - character's full name
  - each alias (semicolon-separated)

A match is accepted if the best similarity score is >= threshold (default 85).
"""
from __future__ import annotations

from rapidfuzz import fuzz

MATCH_THRESHOLD = 85  # 0-100, higher = stricter


def matches(guess: str, name: str, aliases: str) -> tuple[bool, int]:
    """Return (matched, score) for the user's guess vs the character."""
    guess = guess.strip().lower()
    if not guess:
        return False, 0

    candidates = [name.lower()]
    if aliases:
        candidates += [a.strip().lower() for a in aliases.split(";") if a.strip()]

    best = 0
    for c in candidates:
        # token_sort_ratio handles word-order differences ("hatsune miku" vs "miku hatsune")
        s = max(
            fuzz.ratio(guess, c),
            fuzz.token_sort_ratio(guess, c),
            fuzz.partial_ratio(guess, c) if len(guess) >= 3 else 0,
        )
        if s > best:
            best = s

    return best >= MATCH_THRESHOLD, best
