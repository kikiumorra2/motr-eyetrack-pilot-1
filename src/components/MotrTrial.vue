<!--
  MotrTrial — one Mouse-Tracking-for-Reading trial.

  Markup and CSS replicate the original MoTR experiment screen exactly (class names
  included), so layout, font, blur and the cursor window are identical:

    <Screen class="main_screen">        position: relative; isolation: isolate; 18px / 40px
      <div>                             this component's root (plays the role of magpie's <Slide>)
        .oval-cursor                    the moving "window": a white oval with mix-blend-mode: difference
        counter                         "Sentence i of N"
        .readingText                    sharp WHITE text, absolutely positioned, one <span> per word
        .blurry-layer                   BLACK text, blurred, 30% opacity, painted on top of the white text
        spacer / buttons / question

  On a white page the white text is invisible and the participant only sees the blurred
  black copy. Under the oval, difference blending inverts the white text to black and
  cancels the blur, producing a sharp window that follows the mouse. The blurry layer has
  pointer-events: none, so the word <span>s receive the mouse events.

  Data (config.samplingMode):
    "interval"  legacy 20 Hz sampler: while the cursor is over the text, every
                `sampleIntervalMs` a row is recorded with the word under the cursor
                (Index/Word), its bounding box and the mouse position.
    "events"    (default) character-event recorder (src/charEvents/): every coalesced pointer
                sample is hit-tested against measured character boxes and only *changes* of
                the character under the cursor are kept, with millisecond timestamps; one
                compact row per trial (TrialType = "charEvents", see src/charEvents/FORMAT.md).
                postprocessing/1_fetch_and_flatten.py expands it into legacy sample rows.
    "both"      both, for validation.
  "Done Reading" records the end-of-reading marker (Index = -1 row and/or the `e` event) and
  shows the question (if any). "Next Trial" records a trial-summary row (TrialType = "trial"),
  optionally submits this trial's rows to the server, and emits `done`. magpie adds
  `responseTime` (ms since screen start).

    sample rows:  Experiment, Condition, ItemId, Index, Word, mousePositionX/Y,
                  wordPositionTop/Left/Bottom/Right
    charEvents:   Experiment, Condition, ItemId, TrialType, TrialText, mtFormat, mtLayout,
                  mtEvents, mtTrace, mtStats
    summary row:  Experiment, Condition, ItemId, TrialId, TrialType, Phase, TrialText,
                  userResponse, correctResponse, readingTime, ListId, zoomPercent,
                  devicePixelRatio, windowInnerWidth, windowInnerHeight
-->
<template>
  <div>
    <div 
		class="oval-cursor"
		:style="{ fontSize: sentenceFontSize+'px' }"
	></div>

    <div class="trial-counter">
      <template v-if="trial.phase === 'practice'">Practice sentence {{ number }}</template>
      <template v-else>Sentence {{ number }} of {{ total }}</template>
    </div>

    <div
      v-if="reading"
      class="readingText"
	  :style="{ fontSize: sentenceFontSize + 'px' }"
      @mousemove="onMouseMove"
      @mouseleave="onMouseLeave"
    >
      <template v-for="(word, i) of words">
        <span :key="i" :data-index="i">
          {{ word }}
        </span>
      </template>
    </div>

    <div
      class="blurry-layer"
      :style="{
		fontSize: sentenceFontSize + 'px',
		opacity: 0.3, 
		filter: 'blur(0.28em)', 
		transition: 'all 0.3s linear 0s'
	  }"
    >
      {{ trial.text }}
    </div>

    <div style="height: 75px"></div>

    <div>
      <button v-if="reading" :disabled="!hasMoved" @click="finishReading">
        Done Reading
      </button>
    </div>

    <div v-if="!reading && question" class="userInput">
      <p>{{ question.prompt }}</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.response"
        :options="question.options"
      />
    </div>

    <button
      v-if="!reading && question && $magpie.measurements.response"
      @click="finishTrial"
    >
      Next Trial
    </button>
  </div>
</template>

<script>
import config from "../config";
import { zoomPercent } from "../browser";
import { submitRows } from "../submit";
import { CharEventRecorder } from "../charEvents/recorder.js";
import { measureLayout } from "../charEvents/measure.js";
import { attachRecorder } from "../charEvents/dom.js";
import { decodeRow } from "../charEvents/decoder.js";

const samplingMode = () => config.samplingMode || "interval";

export default {
  name: "MotrTrial",
  props: {
    /** Trial object from src/materials.js */
    trial: { type: Object, required: true },
    /** 0-based position of this trial in the whole sequence (recorded as TrialId) */
    index: { type: Number, required: true },
    /** 1-based number shown in the counter ("Sentence 3 of 10"), within practice or main */
    number: { type: Number, required: true },
    /** Number of main trials (for the "Sentence i of N" counter) */
    total: { type: Number, required: true },
    listId: { type: [Number, String], default: null },
	sentenceFontSize:{type: Number, default: 16},
  },
  data() {
    return {
      reading: true,
      hasMoved: false,
      // Word index under the cursor: >= 0 on a word, -1 inside the text area but not on a
      // word, null when the cursor is outside the text area (no samples are recorded).
      currentIndex: null,
      mouse: { x: 0, y: 0 },
      readingStart: null,
      readingTime: null,
      timer: null,
    };
  },
  computed: {
    words() {
      return this.trial.text.split(/\s+/);
    },
    /** Per-item question if present in the materials, else the default from config. */
    question() {
      if (this.trial.question) {
        return { prompt: this.trial.question, options: this.trial.options || [] };
      }
      if (config.question.enabled) {
        return { prompt: config.question.prompt, options: config.question.options };
      }
      return null;
    },
  },
  mounted() {
    const mode = samplingMode();
    if (mode !== "events") this.timer = setInterval(this.recordSample, config.sampleIntervalMs);
    if (mode !== "interval") this.$nextTick(() => this.startRecorder());
  },
  beforeDestroy() {
    clearInterval(this.timer);
    this.stopRecorder();
  },
  methods: {
    isCorrectResponse(response){
       const correct = String(this.trial.correct || "").trim().toUpperCase();
      
       if (correct === "BOTH" || correct === "NA"){
          return true;
       }
       return response === correct;
    },


    cursorEl() {
      return this.$el.querySelector(".oval-cursor");
    },

    baseRow() {
      return {
        Experiment: config.experimentName,
        Condition: this.trial.condition_id,
        ItemId: this.trial.item_id,
      };
    },

    /** Called every sampleIntervalMs; records the word under the cursor. */
    recordSample() {
      if (this.currentIndex === null) return;
      const row = {
        ...this.baseRow(),
        Index: this.currentIndex,
        mousePositionX: this.mouse.x,
        mousePositionY: this.mouse.y,
      };
      const el =
        this.currentIndex >= 0
          ? this.$el.querySelector(`span[data-index="${this.currentIndex}"]`)
          : null;
      if (el) {
        const rect = el.getBoundingClientRect();
        // The span text is " word " (padded, as in the original); store it trimmed.
        row.Word = el.textContent.trim();
        row.wordPositionTop = rect.top;
        row.wordPositionLeft = rect.left;
        row.wordPositionBottom = rect.bottom;
        row.wordPositionRight = rect.right;
      }
      this.$magpie.addTrialData(row);
    },

    wordAt(x, y) {
      const el = document.elementFromPoint(x, y);
      return el ? el.closest("span[data-index]") : null;
    },

    onMouseMove(e) {
      const cursor = this.cursorEl();
      if (!this.hasMoved) {
        this.hasMoved = true;
        this.readingStart = Date.now();
      }
      cursor.classList.add("grow");

      const x = e.clientX;
      const y = e.clientY;
      let el = this.wordAt(x, y);
      if (el) {
        cursor.classList.remove("blank");
      } else {
        // Not on a word: shrink the window and look slightly above the cursor so the
        // word on the line above still counts.
        cursor.classList.add("blank");
        el = this.wordAt(x, y - 3);
      }
      this.currentIndex = el ? Number(el.getAttribute("data-index")) : -1;

      cursor.style.left = `${x + 12}px`;
      cursor.style.top = `${y - 6}px`;
      this.mouse.x = x;
      this.mouse.y = y;
    },

    onMouseLeave() {
      this.cursorEl().classList.remove("grow", "blank");
      this.currentIndex = null;
    },

    // --- character-event recorder (samplingMode "events" / "both") ---------------------
    // The recorder is deliberately NOT part of data(): it is written to on every pointer
    // sample and must not be made reactive.
    startRecorder() {
      const el = this.$el.querySelector(".readingText");
      if (!el || this._recorder) return;
      const recorder = new CharEventRecorder(config.charEvents || {});
      const t0 = performance.now();
      const screenStart = this.$magpie.responseTimeStart || Date.now();
      recorder.start(t0, this.words, measureLayout(el, this.words), {
        t0Response: Date.now() - screenStart,
        tsrc: "event",
      });
      this._recorder = recorder;
      this._detachRecorder = attachRecorder({ recorder, readingTextEl: el, words: this.words });
    },

    stopRecorder() {
      if (this._detachRecorder) this._detachRecorder();
      this._detachRecorder = null;
    },

    /** Ends the recording and stores the trial's charEvents row. */
    pushCharEventsRow() {
      const recorder = this._recorder;
      if (!recorder) return;
      recorder.end(performance.now());
      const fields = recorder.fields();
      this.$magpie.addTrialData({
        ...this.baseRow(),
        TrialType: "charEvents",
        TrialText: this.trial.text,
        ...fields,
      });
      if (config.charEvents && config.charEvents.selfCheck) {
        const decoded = decodeRow(fields);
        const size = Object.values(fields).reduce((n, v) => n + v.length, 0);
        console.assert(decoded.events.length === recorder.events.length, "charEvents self-check: event count");
        console.log(
          `charEvents ${this.trial.item_id}: ${decoded.events.length} events, ${decoded.trace.length} trace samples, ` +
            `${decoded.snapshots.length} layout(s), ${size} bytes, stats ${fields.mtStats}`
        );
      }
    },

    finishReading() {
      const mode = samplingMode();
      if (mode !== "events") {
        // End-of-reading marker: lets postprocessing close the fixation on the last word.
        this.$magpie.addTrialData({
          ...this.baseRow(),
          Index: -1,
          mousePositionX: this.mouse.x,
          mousePositionY: this.mouse.y,
        });
      }
      if (mode !== "interval") this.pushCharEventsRow();
      this.stopRecorder();
      this.currentIndex = null;
      this.cursorEl().classList.remove("grow", "blank");
      this.readingTime = Date.now() - this.readingStart;
      this.reading = false;
      if (!this.question) this.finishTrial();
    },

    finishTrial() {
      const response = this.$magpie.measurements.response || null;

      const isCorrect = response
	  ? this.isCorrectResponse(response)
          : null;

      this.$magpie.addTrialData({
        ...this.baseRow(),
        TrialId: this.index,
        TrialType: "trial",
        Phase: this.trial.phase,
        TrialText: this.trial.text,
        
        userResponse: response,
        correctResponse: this.trial.correct,
        isCorrect: isCorrect,
        
        readingTime: this.readingTime,
        ListId: this.listId,
        zoomPercent: zoomPercent(),
        devicePixelRatio: window.devicePixelRatio,
        windowInnerWidth: window.innerWidth,
        windowInnerHeight: window.innerHeight,
      });
      if (config.submitEachTrial) this.submitTrial();
      this.$emit("done");
    },

    /** Send this trial's rows (samples + summary) to the magpie server. */
    submitTrial() {
      const rows = this.$magpie
        .getAllData()
        .filter(
          (r) =>
            String(r.ItemId) === this.trial.item_id &&
            String(r.Condition) === this.trial.condition_id
        );
      submitRows(this.$magpie, rows, `trial ${this.trial.item_id}`).catch(() => {});
    },
  },
};
</script>

<style>
/* Copied verbatim from the original MoTR experiment. Keep .readingText and .blurry-layer
   identical (font, padding) so the two text layers line up exactly. */
.main_screen {
  isolation: isolate;
  position: relative;
  width: 100%;
  height: auto;
  font-family: Arial, sans-serif;
  font-size: 16px;
  line-height: 40px;
}
.debugResults {
  width: 100%;
}
.readingText {
  /* z-index: 1; */
  position: absolute;
  color: white;
  text-align: center;
  font-weight: 450;
  font-family: Consolas, monospace;
  cursor: pointer;
  width: 100%;
  box-sizing: border-box;
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 3%;
  padding-right: 3%;
  white-space: nowrap;
}
.userInput {
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 20%;
  padding-right: 20%;
}
button {
  /* position: absolute; */
  /* bottom: 0; */
  left: 50%;
}
.oval-cursor {
  position: fixed;
  z-index: 2;
  width: 1px;
  height: 1px;
  transform: translate(-50%, -50%);
  background-color: white;
  mix-blend-mode: difference;
  border-radius: 50%;
  pointer-events: none;
  transition: width 0.5s, height 0.5s;
}
.oval-cursor.grow.blank {
  width: 4.444em; /*original was 80px for 18px font. 80/18 = 4.444em*/
  height: 0.722em; /*13/18 = 0.722em*/
}
.oval-cursor.grow {
  width: 5.667em; /*102/18 = 5.667em*/
  height: 2.111em; /*38/18 = 2.111*/
  border-radius: 50%;
  box-shadow: 30px 0 8px -4px rgba(255, 255, 255, 0.1),
    -30px 0 8px -4px rgba(255, 255, 255, 0.1);
  background-color: rgba(255, 255, 255, 0.3);
  background-blend-mode: screen;
  pointer-events: none;
  transition: width 0.5s, height 0.5s;
  filter: blur(3px);
}
.oval-cursor.grow::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 70%;
  height: 70%;
  background-color: white;
  mix-blend-mode: normal;
  border-radius: 50%;
}
.blurry-layer {
  position: absolute;
  pointer-events: none;
  color: black;
  text-align: center;
  font-weight: 450;
  font-family: Consolas, monospace;
  width: 100%;
  box-sizing: border-box;
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 3%;
  padding-right: 3%;
  white-space: nowrap;
}
</style>
