from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair() -> tuple[bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return (
        public_key.public_bytes_raw(),
        private_key.private_bytes_raw(),
    )


def public_key_b64(public_key_raw: bytes) -> str:
    return base64.urlsafe_b64encode(public_key_raw).decode("ascii")


def public_key_from_b64(value: str) -> Ed25519PublicKey:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    return Ed25519PublicKey.from_public_bytes(raw)


def sign_payload(private_key_raw: bytes, payload: dict[str, Any]) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_raw)
    message = canonical_json(payload)
    signature = private_key.sign(message)
    return base64.urlsafe_b64encode(signature).decode("ascii")


def verify_payload(public_key_b64_value: str, payload: dict[str, Any], signature_b64: str) -> bool:
    try:
        public_key = public_key_from_b64(public_key_b64_value)
        signature = base64.urlsafe_b64decode(signature_b64.encode("ascii"))
        public_key.verify(signature, canonical_json(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
