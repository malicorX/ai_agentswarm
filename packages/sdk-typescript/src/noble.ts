import { createHash } from "node:crypto";

import * as ed from "@noble/ed25519";

ed.etc.sha512Sync = (...messages: Uint8Array[]) => {
  const hash = createHash("sha512");
  for (const message of messages) {
    hash.update(message);
  }
  return new Uint8Array(hash.digest());
};

export { ed };
