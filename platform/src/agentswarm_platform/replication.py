from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from agentswarm_platform.crypto import canonical_json
from agentswarm_platform.credibility import GOOD_ATTEMPT_MINT

REPLICATION_ELIGIBLE_TASK_TYPES = frozenset({"classifier.label"})
TOURNAMENT_ELIGIBLE_TASK_TYPES = frozenset(
    {"creative.text", "summarizer.summarize", "classifier.label"}
)
DEFAULT_REPLICATION_SLOTS = 3
DEFAULT_REPLICATION_QUORUM = 2
DEFAULT_TOURNAMENT_SLOTS = 3
DEFAULT_TOURNAMENT_QUORUM = 2


@dataclass(frozen=True)
class ReplicationConfig:
    slots: int
    quorum: int
    good_attempt_mint: float = 0.0
    kind: str = "replication"


@dataclass(frozen=True)
class QuorumEvaluation:
    status: str
    winning_fingerprint: str | None
    winning_result: dict[str, Any] | None
    counts: dict[str, int]


def parse_replication_config(
    task_type: str, payload: dict[str, Any]
) -> ReplicationConfig | None:
    return parse_parallel_config(task_type, payload)


def parse_parallel_config(
    task_type: str, payload: dict[str, Any]
) -> ReplicationConfig | None:
    tournament = payload.get("tournament")
    if tournament is False or payload.get("replication") is False:
        return None

    if tournament is not None:
        if task_type not in TOURNAMENT_ELIGIBLE_TASK_TYPES:
            raise ValueError(f"tournament not supported for task type {task_type!r}")
        if tournament is True:
            tournament = {}
        if not isinstance(tournament, dict):
            raise ValueError("tournament must be an object when provided")
        slots = int(tournament.get("slots", DEFAULT_TOURNAMENT_SLOTS))
        quorum = int(tournament.get("quorum", DEFAULT_TOURNAMENT_QUORUM))
        good_attempt = float(
            tournament.get("good_attempt_mint", GOOD_ATTEMPT_MINT)
        )
        validate_replication_config(slots, quorum)
        return ReplicationConfig(
            slots=slots,
            quorum=quorum,
            good_attempt_mint=good_attempt,
            kind="tournament",
        )

    if task_type not in REPLICATION_ELIGIBLE_TASK_TYPES:
        return None
    repl = payload.get("replication") or {}
    slots = int(repl.get("slots", DEFAULT_REPLICATION_SLOTS))
    quorum = int(repl.get("quorum", DEFAULT_REPLICATION_QUORUM))
    validate_replication_config(slots, quorum)
    return ReplicationConfig(
        slots=slots,
        quorum=quorum,
        good_attempt_mint=0.0,
        kind="replication",
    )


def validate_replication_config(slots: int, quorum: int) -> None:
    if slots < 2:
        raise ValueError("parallel slots must be at least 2")
    if quorum < 1:
        raise ValueError("parallel quorum must be at least 1")
    if quorum > slots:
        raise ValueError("parallel quorum cannot exceed slots")


def validate_parallel_result(
    task_type: str, payload: dict[str, Any], result: dict[str, Any]
) -> None:
    if task_type == "classifier.label":
        validate_classifier_result(payload, result)
        return
    if task_type == "creative.text":
        text = result.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("creative.text result requires non-empty text")
        return
    if task_type == "summarizer.summarize":
        summary = result.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summarizer.summarize result requires non-empty summary")


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
    elif task_type == "creative.text":
        normalized = {"text": str(result.get("text", "")).strip().lower()}
    elif task_type == "summarizer.summarize":
        normalized = {"summary": str(result.get("summary", "")).strip().lower()}
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
    shared.pop("tournament", None)
    return shared
