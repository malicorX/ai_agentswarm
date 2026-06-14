import assert from "node:assert/strict";
import test from "node:test";

import { createHash } from "node:crypto";

import { ed } from "./noble.js";

import { canonicalJson } from "./crypto.js";

ed.etc.sha512Sync = (...messages: Uint8Array[]) => {
  const hash = createHash("sha512");
  for (const message of messages) {
    hash.update(message);
  }
  return new Uint8Array(hash.digest());
};

test("canonicalJson matches Python sort_keys compact format", () => {
  const payload = { task_id: "task_abc", result: { applied: true, z: 1, a: 2 } };
  const encoded = canonicalJson(payload);
  assert.equal(
    encoded,
    '{"result":{"a":2,"applied":true,"z":1},"task_id":"task_abc"}',
  );
});

test("sign round-trip with noble ed25519", async () => {
  const privateKey = ed.utils.randomPrivateKey();
  const publicKey = await ed.getPublicKey(privateKey);
  const message = new TextEncoder().encode(
    canonicalJson({ task_id: "t1", result: { ok: true } }),
  );
  const signature = await ed.sign(message, privateKey);
  const valid = await ed.verify(signature, message, publicKey);
  assert.equal(valid, true);
});
