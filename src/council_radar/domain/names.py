"""Match council names from government lists (e.g. EFS tables) to ONS codes.

Government pages use short names ("Windsor & Maidenhead"), ONS uses formal names
("Windsor and Maidenhead"). Matching normalises both sides and reports anything
ambiguous or unmatched instead of guessing.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

_STOP = {
    "council",
    "borough",
    "city",
    "of",
    "metropolitan",
    "district",
    "county",
    "london",
    "royal",
    "the",
    "unitary",
}
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalise_name(name: str) -> str:
    s = name.casefold().replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    tokens = [t for t in s.split() if t not in _STOP]
    return " ".join(tokens)


@dataclass
class MatchResult:
    matched: dict[str, str] = field(default_factory=dict)  # raw name -> ons_code
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)


def match_names(raw_names: Iterable[str], councils: Mapping[str, str]) -> MatchResult:
    """``councils`` maps ons_code -> official name."""
    index: dict[str, list[str]] = defaultdict(list)
    for code, official in councils.items():
        index[normalise_name(official)].append(code)
    res = MatchResult()
    for raw in dict.fromkeys(raw_names):  # dedupe, keep order
        hits = index.get(normalise_name(raw), [])
        if len(hits) == 1:
            res.matched[raw] = hits[0]
        elif len(hits) > 1:
            res.ambiguous[raw] = sorted(hits)
        else:
            res.unmatched.append(raw)
    return res
