// Hand-made layout table shared by several tests (not a test file itself).
//
// Three lines, 10 px characters, 40 px line pitch, 21 px glyph band (like the real screen:
// font-size 18px / line-height 40px). Word 3 ("wrapped") is split across lines 1 and 2.
// Leading spaces are zero-width (omitted, k0 = 1); trailing spaces are 10 px wide except at
// line ends where they are omitted too.
export const WORDS = ["The", "cat", "sat", "wrapped", "on", "the", "mat."];
export const TABLE = {
  block: [100, 150, 500, 300],
  words: [
    { rect: [120, 180, 160, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [120, 130, 140, 150, 160] }] },
    { rect: [160, 180, 200, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [160, 170, 180, 190, 200] }] },
    { rect: [200, 180, 230, 201], frags: [{ k0: 1, top: 180, bottom: 201, xs: [200, 210, 220, 230] }] }, // no trailing space (line end)
    { rect: [120, 220, 240, 281], frags: [
      { k0: 1, top: 220, bottom: 241, xs: [120, 130, 140, 150] },             // "wra"
      { k0: 4, top: 260, bottom: 281, xs: [120, 130, 140, 150, 160, 170] },   // "pped" + trailing space
    ] },
    { rect: [170, 260, 200, 281], frags: [{ k0: 1, top: 260, bottom: 281, xs: [170, 180, 190, 200] }] },
    { rect: [200, 260, 240, 281], frags: [{ k0: 1, top: 260, bottom: 281, xs: [200, 210, 220, 230, 240] }] },
    { rect: [240, 260, 280, 281], frags: [{ k0: 1, top: 260, bottom: 281, xs: [240, 250, 260, 270, 280] }] }, // "mat." no trailing space
  ],
};

/** Same layout shifted down by `dy` px (e.g. after a scroll) — for relayout tests. */
export function shiftedTable(table, dx, dy) {
  const mv = (r) => [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy];
  return {
    block: mv(table.block),
    words: table.words.map((w) => ({
      rect: mv(w.rect),
      frags: w.frags.map((f) => ({ k0: f.k0, top: f.top + dy, bottom: f.bottom + dy, xs: f.xs.map((x) => x + dx) })),
    })),
  };
}

/**
 * Synthetic monospace layout for arbitrary words: `charW` px per code point, words
 * separated by one `charW`-wide trailing space, wrapped after `lineChars` characters,
 * `lineH` px line pitch with a `glyphH` px glyph band. Leading spaces are zero-width
 * (omitted); trailing spaces are omitted at line ends (like a real browser).
 */
export function fakeTable(words, { charW = 10, lineChars = 60, lineH = 40, glyphH = 21, left = 120, top = 180, blockPad = 20 } = {}) {
  const table = { block: null, words: [] };
  let line = 0, col = 0, maxCol = 0;
  const bandTop = (ln) => top + ln * lineH;
  for (const w of words) {
    const len = Array.from(w).length;
    if (col > 0 && col + len > lineChars) { line++; col = 0; }
    const x0 = left + col * charW, t = bandTop(line);
    const xs = [];
    for (let j = 0; j <= len; j++) xs.push(x0 + j * charW);
    col += len;
    const atLineEnd = col >= lineChars;
    if (!atLineEnd) { xs.push(x0 + (len + 1) * charW); col += 1; }
    maxCol = Math.max(maxCol, col);
    table.words.push({ rect: [x0, t, xs[xs.length - 1], t + glyphH], frags: [{ k0: 1, top: t, bottom: t + glyphH, xs }] });
  }
  const right = left + maxCol * charW;
  table.block = [left - blockPad, top - blockPad, right + blockPad, bandTop(line) + glyphH + blockPad];
  return table;
}
