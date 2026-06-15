from __future__ import annotations

import os
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


def reject_version_downgrades() -> bool:
    raw = os.environ.get("AGENTSWARM_VERSION_REJECT_DOWNGRADES", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_version_downgrade(previous: str, current: str) -> bool:
    """True when current is a strict downgrade within the same version family."""
    if previous.strip() == current.strip():
        return False
    old = parse_version_signature(previous)
    new = parse_version_signature(current)
    if old.family != new.family:
        return False
    if new.major < old.major:
        return True
    return new.major == old.major and new.minor < old.minor


def assert_version_reconnect_allowed(previous: str, current: str) -> None:
    if reject_version_downgrades() and is_version_downgrade(previous, current):
        raise ValueError(
            "version_signature downgrade is not allowed; "
            "bump forward or register a new agent identity"
        )


def versioning_public_parameters() -> dict[str, float | int | bool]:
    return {
        "reject_downgrades": reject_version_downgrades(),
    }


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
