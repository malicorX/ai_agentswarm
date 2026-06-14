from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from agentswarm_platform.crypto import canonical_json

REPLICATION_ELIGIBLE_TASK_TYPES = frozenset({"classifier.label"})
DEFAULT_REPLICATION_SLOTS = 3
DEFAULT_REPLICATION_QUORUM = 2


@dataclass(frozen=True)
class ReplicationConfig:
    slots: int
    quorum: int


@dataclass(frozen=True)
class QuorumEvaluation:
    status: str
    winning_fingerprint: str | None
    winning_result: dict[str, Any] | None
    counts: dict[str, int]


def parse_replication_config(
    task_type: str, payload: dict[str, Any]
) -> ReplicationConfig | None:
    if task_type not in REPLICATION_ELIGIBLE_TASK_TYPES:
        return None
    if payload.get("replication") is False:
        return None
    repl = payload.get("replication") or {}
    slots = int(repl.get("slots", DEFAULT_REPLICATION_SLOTS))
    quorum = int(repl.get("quorum", DEFAULT_REPLICATION_QUORUM))
    validate_replication_config(slots, quorum)
    return ReplicationConfig(slots=slots, quorum=quorum)


def validate_replication_config(slots: int, quorum: int) -> None:
    if slots < 2:
        raise ValueError("replication slots must be at least 2")
    if quorum < 2:
        raise ValueError("replication quorum must be at least 2")
    if quorum > slots:
        raise ValueError("replication quorum cannot exceed slots")


def validate_classifier_result(payload: dict[str, Any], result: dict[str, Any]) -> None:
    label = result.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("classifier result requires non-empty string label")
    allowed = payload.get("labels")
    if allowed is not None and label not in allowed:
        raise ValueError(f"label must be one of: {', '.join(allowed)}")


def result_fingerprint(task_type: str, result: dict[str, Any]) -> str:
    if task_type == "classifier.label":
        normalized = {"label": str(result.get("label", "")).strip().lower()}
    else:
        normalized = result
    digest = hashlib.sha256(canonical_json(normalized)).hexdigest()
    return digest


def evaluate_quorum(
    *,
    task_type: str,
    submissions: list[dict[str, Any]],
    quorum: int,
    slots: int,
) -> QuorumEvaluation:
    fingerprints: list[str] = []
    fingerprint_to_result: dict[str, dict[str, Any]] = {}
    for item in submissions:
        fp = result_fingerprint(task_type, item["result"])
        fingerprints.append(fp)
        fingerprint_to_result[fp] = item["result"]
    counts = Counter(fingerprints)
    count_map = dict(counts)
    if not submissions:
        return QuorumEvaluation("pending", None, None, count_map)
    best_fp, best_count = counts.most_common(1)[0]
    if best_count >= quorum:
        return QuorumEvaluation(
            "quorum_met",
            best_fp,
            fingerprint_to_result[best_fp],
            count_map,
        )
    if len(submissions) >= slots:
        return QuorumEvaluation("disputed", None, None, count_map)
    return QuorumEvaluation("pending", None, None, count_map)


def shared_replication_payload(payload: dict[str, Any]) -> dict[str, Any]:
    shared = dict(payload)
    shared.pop("replication", None)
    return shared
