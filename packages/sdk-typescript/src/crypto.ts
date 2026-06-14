export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
    .join(",")}}`;
}

export function publicKeyB64(publicKey: Uint8Array): string {
  return Buffer.from(publicKey).toString("base64url");
}

export function privateKeyB64(privateKey: Uint8Array): string {
  return Buffer.from(privateKey).toString("base64url");
}

export function decodeB64Url(value: string): Uint8Array {
  return new Uint8Array(Buffer.from(value, "base64url"));
}
