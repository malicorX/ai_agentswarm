from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agentswarm_mcp import bridge
from agentswarm_platform.crypto import generate_keypair, public_key_b64


def test_poll_tasks_builds_query() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [{"task_id": "task_1"}]
    mock_response.raise_for_status = MagicMock()
    with patch.object(httpx, "get", return_value=mock_response) as get:
        tasks = bridge.poll_tasks(agent_id="agent_a", capability="codewriter", base_url="http://x")
    get.assert_called_once()
    assert get.call_args.kwargs["params"] == {
        "agent_id": "agent_a",
        "capability": "codewriter",
    }
    assert tasks[0]["task_id"] == "task_1"


def test_submit_task_signs_payload() -> None:
    pub, priv = generate_keypair()
    priv_b64 = __import__("base64").urlsafe_b64encode(priv).decode("ascii")
    mock_response = MagicMock()
    mock_response.json.return_value = {"submission_id": "sub_1"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx, "post", return_value=mock_response) as post:
        body = bridge.submit_task(
            claim_token="claim_1",
            task_id="task_1",
            result={"ok": True},
            private_key_b64=priv_b64,
            base_url="http://x",
        )

    assert body["submission_id"] == "sub_1"
    sent = post.call_args.kwargs["json"]
    assert sent["claim_token"] == "claim_1"
    assert verify_submit_signature(public_key_b64(pub), sent, "task_1", {"ok": True})


def verify_submit_signature(
    public_key_b64_value: str, sent: dict, task_id: str, result: dict
) -> bool:
    from agentswarm_platform.crypto import verify_payload

    return verify_payload(
        public_key_b64_value,
        {"task_id": task_id, "result": result},
        sent["signature"],
    )


def test_verify_submission_posts_signed_body() -> None:
    pub, priv = generate_keypair()
    priv_b64 = __import__("base64").urlsafe_b64encode(priv).decode("ascii")
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ack"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx, "post", return_value=mock_response) as post:
        bridge.verify_submission(
            claim_token="claim_v",
            verdict="approve",
            task_id="task_1",
            submission_id="sub_1",
            notes="looks good",
            private_key_b64=priv_b64,
            base_url="http://x",
        )

    sent = post.call_args.kwargs["json"]
    assert sent["verdict"] == "approve"
    from agentswarm_platform.crypto import verify_payload

    assert verify_payload(
        public_key_b64(pub),
        {
            "task_id": "task_1",
            "submission_id": "sub_1",
            "verdict": "approve",
            "notes": "looks good",
        },
        sent["signature"],
    )


def test_checkpoint_parses_json_string() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = MagicMock()
    with patch.object(httpx, "post", return_value=mock_response) as post:
        bridge.checkpoint_task(
            claim_token="claim_1",
            partial_state=json.dumps({"step": 2}),
            base_url="http://x",
        )
    sent = post.call_args.kwargs["json"]
    assert sent["partial_state"] == {"step": 2}


def test_decode_private_key_requires_value() -> None:
    with pytest.raises(ValueError, match="private_key_b64"):
        bridge.decode_private_key(None)
