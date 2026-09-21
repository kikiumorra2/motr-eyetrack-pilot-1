// Variable-length integer coding used for the raw pointer trace (mtTrace).
//
// Each signed integer is zigzag-mapped to a non-negative integer and written as a
// sequence of 5-bit chunks, least-significant chunk first; bit 0x20 of a symbol marks
// "more chunks follow". Symbols use a 64-character alphabet that is safe in JSON,
// CSV and the magpie/Postgres exports (no quotes, backslashes, braces or `|`).
//
// The Python module postprocessing/motr_char_events.py implements the same coding;
// the cross-language fixture tests keep them byte-for-byte identical.

export const ALPHABET =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

const CODE = new Map();
for (let i = 0; i < ALPHABET.length; i++) CODE.set(ALPHABET[i], i);

/** Map a signed integer to a non-negative one: 0,-1,1,-2,2 → 0,1,2,3,4. */
export function zigzag(v) {
  return v >= 0 ? v * 2 : -v * 2 - 1;
}

export function unzigzag(z) {
  return z % 2 === 0 ? z / 2 : -(z + 1) / 2;
}

/** Encode an array of safe integers as a VLQ string. */
export function encodeInts(ints) {
  let out = "";
  for (let i = 0; i < ints.length; i++) {
    const v = ints[i];
    if (!Number.isSafeInteger(v)) throw new RangeError(`not a safe integer: ${v}`);
    let z = zigzag(v);
    if (!Number.isSafeInteger(z)) throw new RangeError(`magnitude too large for VLQ: ${v}`);
    for (;;) {
      let chunk = z % 32;
      z = (z - chunk) / 32;
      if (z > 0) chunk += 32;
      out += ALPHABET[chunk];
      if (z === 0) break;
    }
  }
  return out;
}

/** Decode a VLQ string back to an array of integers. Throws on malformed input. */
export function decodeInts(s) {
  const out = [];
  let value = 0;
  let mult = 1;
  let open = false;
  for (let i = 0; i < s.length; i++) {
    const chunk = CODE.get(s[i]);
    if (chunk === undefined) throw new SyntaxError(`invalid VLQ character ${JSON.stringify(s[i])} at ${i}`);
    value += (chunk & 31) * mult;
    if (chunk & 32) {
      mult *= 32;
      open = true;
    } else {
      out.push(unzigzag(value));
      value = 0;
      mult = 1;
      open = false;
    }
  }
  if (open) throw new SyntaxError("truncated VLQ string (dangling continuation)");
  return out;
}
