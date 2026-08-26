/** Generate a RFC 9562 UUIDv7 using the platform CSPRNG. */
export function newUuidV7(): string {
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.getRandomValues) {
    throw new Error("A cryptographically secure random source is required");
  }

  const random = cryptoApi.getRandomValues(new Uint8Array(10));
  const bytes = new Uint8Array(16);
  const timestamp = Date.now();

  // UUIDv7 carries a 48-bit Unix epoch millisecond timestamp in big-endian
  // order, followed by a version nibble, variant bits, and random data.
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = (timestamp / 2 ** (8 * (5 - index))) & 0xff;
  }
  bytes[6] = 0x70 | (random[0] & 0x0f);
  bytes[7] = random[1];
  bytes[8] = 0x80 | (random[2] & 0x3f);
  bytes.set(random.subarray(3), 9);

  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
