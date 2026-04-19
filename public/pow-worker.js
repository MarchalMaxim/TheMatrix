/**
 * pow-worker.js — Proof-of-Work solver running in a Web Worker thread.
 *
 * Input message:  { challenge: string, difficulty: number }
 * Output message: { nonce: string }
 *
 * Finds the smallest integer nonce such that
 *   SHA-256(`${challenge}:${nonce}`)
 * starts with at least `difficulty` zero bits.
 */

const enc = new TextEncoder();

/**
 * Count leading zero bits in a Uint8Array (big-endian SHA-256 output).
 */
function countLeadingZeroBits(bytes) {
  for (let i = 0; i < bytes.length; i++) {
    const byte = bytes[i];
    if (byte === 0) continue; // 8 more zero bits
    // First non-zero byte — find the position of the leading 1-bit
    for (let shift = 7; shift >= 0; shift--) {
      if ((byte >> shift) & 1) return i * 8 + (7 - shift);
    }
  }
  return bytes.length * 8;
}

self.onmessage = async function (e) {
  const { challenge, difficulty } = e.data;
  let nonce = 0;
  while (true) {
    const buf = await crypto.subtle.digest(
      "SHA-256",
      enc.encode(`${challenge}:${nonce}`),
    );
    if (countLeadingZeroBits(new Uint8Array(buf)) >= difficulty) {
      self.postMessage({ nonce: String(nonce) });
      return;
    }
    nonce++;
  }
};
