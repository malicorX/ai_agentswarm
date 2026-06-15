from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(
    r"^([a-zA-Z0-9][a-zA-Z0-9._-]{2,})-v(\d+)(?:\.(\d+))?$"
)


@dataclass(frozen=True)
class ParsedVersion:
    raw: str
    family: str
    major: int
    minor: int


def parse_version_signature(version_signature: str) -> ParsedVersion:
    raw = version_signature.strip()
    match = _VERSION_RE.match(raw)
    if not match:
        raise ValueError(
            "version_signature must match <family>-v<major>[.<minor>] "
            "(e.g. codewriter-v1.0)"
        )
    family, major_s, minor_s = match.groups()
    return ParsedVersion(
        raw=raw,
        family=family.lower(),
        major=int(major_s),
        minor=int(minor_s or 0),
    )


def validate_version_signature(version_signature: str) -> None:
    if len(version_signature.strip()) < 8:
        raise ValueError("version_signature must be at least 8 characters")
    parse_version_signature(version_signature)


def classify_version_bump(previous: str, current: str) -> str | None:
    """Return None if unchanged, else minor or major."""
    if previous.strip() == current.strip():
        return None
    old = parse_version_signature(previous)
    new = parse_version_signature(current)
    if old.family != new.family:
        return "major"
    if new.major > old.major:
        return "major"
    if new.major == old.major and new.minor > old.minor:
        return "minor"
    return "major"
