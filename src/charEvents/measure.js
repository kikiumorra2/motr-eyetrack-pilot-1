// Measure the character layout of the reading screen (DOM side of the char-event recorder).
//
// The screen renders one <span data-index="i"> word </span> per word; nothing in the DOM
// is changed here — every character is measured with a Range over the span's text node,
// so the rendered text stays pixel-identical. See layout.js for the table shape and
// FORMAT.md for the character model (k = 0 leading space, 1..len code points, len+1
// trailing space).

const MIN_WIDTH = 0.05;

function firstTextNode(el) {
  for (const n of el.childNodes) if (n.nodeType === 3) return n;
  return null;
}

/** Map code-point positions of the span's text to local character indices k. */
function localIndexMap(text, wordLen) {
  const cps = Array.from(text);
  if (cps.length === wordLen + 2) return cps.map((_, i) => i);   // " word " exactly (Vue condenses whitespace)
  // Unexpected whitespace: map leading whitespace to 0, trailing to len+1, the rest 1..len.
  let lead = 0;
  while (lead < cps.length && /\s/.test(cps[lead])) lead++;
  return cps.map((_, i) => Math.max(0, Math.min(wordLen + 1, i - lead + 1)));
}

/**
 * Measure `readingTextEl` (the .readingText block) into a layout table.
 * `words` are the trial's words (same order as the spans) — used to validate the
 * span → word mapping; the measurement itself is DOM-driven.
 */
export function measureLayout(readingTextEl, words) {
  const B = readingTextEl.getBoundingClientRect();
  const table = { block: [B.left, B.top, B.right, B.bottom], words: [] };
  const spans = Array.from(readingTextEl.querySelectorAll("span[data-index]"))
    .sort((a, b) => Number(a.getAttribute("data-index")) - Number(b.getAttribute("data-index")));
  const range = document.createRange();
  spans.forEach((span, i) => {
    const rect = span.getBoundingClientRect();
    const word = { rect: [rect.left, rect.top, rect.right, rect.bottom], frags: [] };
    table.words.push(word);
    const textNode = firstTextNode(span);
    if (!textNode) return;
    const text = textNode.data;
    const wordLen = Array.from(words && words[i] !== undefined ? words[i] : text.trim()).length;
    const kOf = localIndexMap(text, wordLen);
    const lineRects = Array.from(span.getClientRects());
    const cps = Array.from(text);
    let u16 = 0;
    let cur = null;
    for (let c = 0; c < cps.length; c++) {
      const len = cps[c].length;
      range.setStart(textNode, u16);
      range.setEnd(textNode, u16 + len);
      u16 += len;
      let r = null;
      for (const rr of range.getClientRects()) if (!r || rr.width > r.width) r = rr;
      if (!r || r.width < MIN_WIDTH) { cur = null; continue; }
      // Vertical extent: the span's line fragment this glyph sits on (so "on a character"
      // ⇔ "elementFromPoint hits the span"); fall back to the glyph rect.
      const cy = r.top + r.height / 2;
      const band = lineRects.find((lr) => cy >= lr.top && cy < lr.bottom) || r;
      const k = kOf[c];
      if (cur && cur.top === band.top && cur.bottom === band.bottom && k === cur.k0 + cur.xs.length - 1 &&
          Math.abs(cur.xs[cur.xs.length - 1] - r.left) < 0.5) {
        cur.xs.push(r.right);
      } else {
        cur = { k0: k, top: band.top, bottom: band.bottom, xs: [r.left, r.right] };
        word.frags.push(cur);
      }
    }
    // Snap fragment edges to the span's line box so the padding spaces cover the whole
    // inline box (legacy hit-testing counts the entire span).
    for (const f of word.frags) {
      const lr = lineRects.find((x) => f.top === x.top && f.bottom === x.bottom);
      if (!lr) continue;
      if (Math.abs(f.xs[0] - lr.left) < 1) f.xs[0] = lr.left;
      if (Math.abs(f.xs[f.xs.length - 1] - lr.right) < 1) f.xs[f.xs.length - 1] = lr.right;
    }
  });
  if (typeof range.detach === "function") range.detach();
  return table;
}
