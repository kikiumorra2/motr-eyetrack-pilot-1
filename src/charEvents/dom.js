// Wire a CharEventRecorder to the browser (pointer events, layout changes, visibility).
//
//   const detach = attachRecorder({ recorder, readingTextEl, words });
//   ...
//   detach();
//
// * pointermove on the document (capture, passive) — every coalesced hardware sample is fed
//   with its own timeStamp (getCoalescedEvents; falls back to the event itself).
// * pointerleave on the text block → recorder.leave().
// * visibilitychange → recorder.visibility().
// * resize / scroll / visualViewport / ResizeObserver / font loading → re-measure the
//   layout (debounced to one animation frame) → recorder.relayout().

import { measureLayout } from "./measure.js";

const MAX_TIMESTAMP_SKEW_MS = 10000;

export function attachRecorder({ recorder, readingTextEl, words }) {
  const now = () => performance.now();
  let detached = false;

  const onPointerMove = (e) => {
    const t1 = now();
    let evs = null;
    let coalesced = false;
    if (typeof e.getCoalescedEvents === "function") {
      const c = e.getCoalescedEvents();
      if (c && c.length) { evs = c; coalesced = true; }
    }
    if (!evs) evs = [e];
    for (let i = 0; i < evs.length; i++) {
      const ev = evs[i];
      let ts = ev.timeStamp;
      if (!(Math.abs(ts - t1) < MAX_TIMESTAMP_SKEW_MS)) { ts = t1; recorder.tsrc = "perf"; }
      recorder.feed(ev.clientX, ev.clientY, ts, ev.pointerType || "mouse");
    }
    recorder.noteBatch(evs.length, coalesced, (now() - t1) * 1000);
  };
  const onPointerLeave = () => recorder.leave(now());
  const onVisibility = () => recorder.visibility(now(), document.hidden);

  let raf = 0;
  const remeasure = () => {
    raf = 0;
    if (detached || !readingTextEl.isConnected) return;
    recorder.relayout(now(), measureLayout(readingTextEl, words));
  };
  const scheduleRemeasure = () => {
    if (!raf) raf = requestAnimationFrame(remeasure);
  };

  document.addEventListener("pointermove", onPointerMove, { capture: true, passive: true });
  readingTextEl.addEventListener("pointerleave", onPointerLeave, { passive: true });
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("resize", scheduleRemeasure);
  document.addEventListener("scroll", scheduleRemeasure, { capture: true, passive: true });
  const vv = window.visualViewport;
  if (vv) {
    vv.addEventListener("resize", scheduleRemeasure);
    vv.addEventListener("scroll", scheduleRemeasure);
  }
  let ro = null;
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(scheduleRemeasure);
    ro.observe(readingTextEl);
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleRemeasure, () => {});

  return function detach() {
    if (detached) return;
    detached = true;
    if (raf) cancelAnimationFrame(raf);
    document.removeEventListener("pointermove", onPointerMove, { capture: true });
    readingTextEl.removeEventListener("pointerleave", onPointerLeave);
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("resize", scheduleRemeasure);
    document.removeEventListener("scroll", scheduleRemeasure, { capture: true });
    if (vv) {
      vv.removeEventListener("resize", scheduleRemeasure);
      vv.removeEventListener("scroll", scheduleRemeasure);
    }
    if (ro) ro.disconnect();
  };
}
