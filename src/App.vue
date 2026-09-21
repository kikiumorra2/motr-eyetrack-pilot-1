<!--
  Screen flow of the experiment:
    1. Consent + participant ID          (edit the study information text below)
    2. Browser check: zoom = 100%         (config.browserCheck)
    3. Instructions                       (edit)
    4. Practice trials                    (materials/practice.csv, config.nPractice)
       "Practice complete" screen
    5. Main trials                        (materials/lists/list_NN.csv + fillers.csv)
    6. Survey: device, hand, feedback     (config.survey.enabled)
    7. Completion code

  The MoTR interface itself is in components/MotrTrial.vue; experiment settings are in
  config.js; server settings in magpie.config.js; materials in ../materials/.
-->
<template>
  <Experiment title="Reading Experiment" translate="no" wide>
    <!-- 1. Consent ---------------------------------------------------------------- -->
<Screen
  title="Welcome"
  class="instructions"
  :validations="{ SubjectID: { minLength: $magpie.v.minLength(2) } }"
>
  <div id="consent">

    <div
      id="consent-form"
      class="consent-scrollbox"
    >
      <h1 class="consent-title">
        Informed Consent Form IRB-FY2020-4512
      </h1>

      <div class="study-information">
        <p>
          <strong>Title:</strong>
          Sources of Difficulty in Language Processing and Learning
        </p>

        <p>
          <strong>Principal Investigator:</strong>
          Tal Linzen, Department of Linguistics and the Center for
          Data Science, New York University
        </p>
      </div>

      <h2 class="section-heading">
        PURPOSE OF RESEARCH STUDY:
      </h2>

      <p>
        The goal of the project is to measure what makes particular
        aspects of language easier or harder to learn and understand.
      </p>

      <h2 class="section-heading">
        PROCEDURES:
      </h2>

      <p>
        You will be asked to read or listen to language, and answer
        questions about what you've read or heard. The sentences may
        be in English or in a made-up language that you will learn
        during the experiment. The experiment involves a single
        session that will take up to an hour; there will be up to five
        sessions, but most participants will only participate in a
        single session.
      </p>

      <h2 class="section-heading">
        RISKS/DISCOMFORTS:
      </h2>

      <p>
        The risks associated with participation in this study are no
        greater than those encountered in daily life.
      </p>

      <h2 class="section-heading">
        BENEFITS:
      </h2>

      <p>
        There are no direct benefits to you from participating in this
        study. This study may benefit society if the results lead to a
        better understanding of what makes certain aspects of language
        easier or harder to learn and understand.
      </p>

      <h2 class="section-heading">
        VOLUNTARY PARTICIPATION AND RIGHT TO WITHDRAW:
      </h2>

      <p>
        Your participation in this study is entirely voluntary: You
        choose whether to participate. If you decide not to
        participate, there are no penalties, and you will not lose any
        benefits to which you would otherwise be entitled.
      </p>

      <p>
        If you choose to participate in the study, you can stop your
        participation at any time, without any penalty or loss of
        benefits.
      </p>

      <h2 class="section-heading">
        CONFIDENTIALITY:
      </h2>

      <p>
        Any study records that identify you will be kept confidential
        to the extent possible by law. The records from your
        participation may be reviewed by people responsible for making
        sure that research is done properly. Otherwise, records that
        identify you will be available only to people working on the
        study, unless you give permission for other people to see the
        records.
      </p>

      <p>
        Any study records that include your name will be kept in a
        password-protected database. On all records of test results,
        we will use a code number rather than your name.
      </p>

      <h2 class="section-heading">
        COMPENSATION:
      </h2>

      <p>
        You will receive compensation in proportion to the length of
        the session.
      </p>

      <h2 class="section-heading">
        IF YOU HAVE QUESTIONS OR CONCERNS:
      </h2>

      <p>
        You can ask questions about this research study now or at any
        time during the study, by talking to the researcher(s) working
        with you or by emailing Dr. Tal Linzen at
        <a href="mailto:linzen@nyu.edu">linzen@nyu.edu</a>.
      </p>

      <p>
        If you have questions about your rights as a research
        participant or feel that you have not been treated fairly,
        please contact the NYU Institutional Review Board at
        <a href="mailto:ask.humansubjects@nyu.edu">
          ask.humansubjects@nyu.edu
        </a>
        or <strong>212.998.4808</strong>.
      </p>

      <p class="final-consent-statement">
        Pressing "Continue" below means that you understand the
        information in this consent form, and that you agree to
        participate in this study. You have not waived any legal rights
        you otherwise would have as a participant in a research study.
      </p>
    </div>

    <p class="continue-instruction">
      If you agree to participate, please enter your Prolific ID and
      press "Continue." Otherwise, you may exit this page.
    </p>

    <p class="participant-id">
      Prolific ID:
      <input
        type="text"
        v-model="$magpie.measurements.SubjectID"
      />
    </p>

    <div
      class="consent-button"
      v-if="$magpie.measurements.SubjectID &&
            !$magpie.validateMeasurements.SubjectID.$invalid"
    >
      <button @click="consent">
        Continue
      </button>
    </div>

  </div>
</Screen>

    <!-- 2. Browser check (zoom) -------------------------------------------------- -->
    <Screen 
      v-if="config.browserCheck.enabled" 
      title="Before we start"
      class="instructions"
    >
      <div class ="browser-check-text">
        <BrowserCheck
          :longest-sentence="longestSentence"
          :sentence-font-size="sentenceFontSize"
          @done="browserCheckDone"
        />
      </div>
    </Screen>

    <!-- 3. Instructions ---------------------------------------------------------- -->
    <InstructionScreen title="Instructions">
      <p>
        In this study, you will read sentences. Unlike in normal reading, however, the text
        will be blurred. To bring the text into focus, move your mouse over it. When you are
        done reading, click the <b>Done Reading</b> button.
      </p>
      <p>
        After each sentence you will be asked a question about it. Indicate your answer by
        clicking the appropriate option, then click <b>Next</b>.
      </p>
      <p v-if="practiceTrials.length">We will start with a few practice sentences.</p>
    </InstructionScreen>

    <!-- 4. Practice trials ------------------------------------------------------- -->
    <template v-for="(trial, i) in practiceTrials">
      <Screen :key="'practice-' + i" class="main_screen" :progress="0">
        <MotrTrial
          :trial="trial"
          :index="i"
          :number="i + 1"
          :total="mainTrials.length"
          :list-id="listId"
          :sentence-font-size="sentenceFontSize"
          @done="$magpie.nextScreen()"
        />
      </Screen>
    </template>

    <!-- 4b. Practice complete ----------------------------------------------------- -->
    <InstructionScreen v-if="practiceTrials.length" title="Practice complete">
      <p>That was the practice. Press the button to start the main study.</p>
    </InstructionScreen>

    <!-- 5. Main trials ----------------------------------------------------------- -->
    <template v-for="(trial, i) in mainTrials">
      <Screen :key="'trial-' + i" class="main_screen" :progress="i / mainTrials.length">
        <MotrTrial
          :trial="trial"
          :index="practiceTrials.length + i"
          :number="i + 1"
          :total="mainTrials.length"
          :list-id="listId"
          :sentence-font-size="sentenceFontSize"
          @done="$magpie.nextScreen()"
        />
      </Screen>
    </template>

    <!-- 6. Survey ---------------------------------------------------------------- -->
    <Screen v-if="config.survey.enabled" title="Almost done">
      <p>1. Which input device are you using for this experiment?</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.device"
        orientation="horizontal"
        :options="['Computer Mouse', 'Computer Trackpad', 'Other']"
      />
      <p>2. Which hand are you using during this experiment?</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.hand"
        orientation="horizontal"
        :options="['Left', 'Right', 'Both']"
      />
      <p>
        3. What did you think about the experiment? Please describe how hard or easy the task
        felt, anything you noticed about the sentences, or any other thoughts you have. If
        anything was confusing or frustrating, please let us know!
      </p>
      <TextareaInput :response.sync="$magpie.measurements.feedback" />
      <button :disabled="submitting" @click="finish">
        {{ submitting ? "Submitting…" : "Submit" }}
      </button>
    </Screen>
    <Screen v-else title="Almost done">
      <p>The next screen will submit your results and display your completion code.</p>
      <button :disabled="submitting" @click="finish">
        {{ submitting ? "Submitting…" : "Continue" }}
      </button>
    </Screen>

    <!-- 7. Completion ------------------------------------------------------------ -->
    <Screen title="Study complete">
      <p class="selectable-text large">Completion code:</p>
      <p class="selectable-text large">{{ config.completionCode }}</p>
      <p v-if="$magpie.mode === 'prolific'">
        <a :href="$magpie.completionUrl">Click here to return to Prolific.</a>
      </p>
    </Screen>
  </Experiment>
</template>

<script>
import config from "./config";
import MotrTrial from "./components/MotrTrial.vue";
import BrowserCheck from "./components/BrowserCheck.vue";
import { chooseListId, buildPracticeTrials, buildMainTrials } from "./materials";
import { browserInfo } from "./browser";
import { submitRows } from "./submit";
  
  
//make the font be a function of the size of the screen so that you never have to scroll to see full sentence -->

//SENTENCE_FONT_MODE = 
//  "reponsive" --> makes the font size s.t. the longest sentence takes up 90% of the window width
//  "fixed" --> sets font size to whatever FIXED_SENTENCE_FONT_SIZE is
  
const SENTENCE_FONT_MODE = "fixed";

const FIXED_SENTENCE_FONT_SIZE = 16;
  
const MAX_SENTENCE_FONT_SIZE = 16;
const SENTENCE_WIDTH_FRACTION = 0.90;

function calculateSentenceFontSize(trials){
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  //this must match font size in MotrTrial.vue
  ctx.font = `450 ${MAX_SENTENCE_FONT_SIZE}px Consolas, monospace`;

  let widestSentence = 0;

  for (const trial of trials){
    const width = ctx.measureText(trial.text).width;

    if (width > widestSentence){
      widestSentence = width;
    }
  }

  const availableWidth = window.innerWidth * SENTENCE_WIDTH_FRACTION;

  //how much do we need to shrink the 16px so the longest sentence fits?
  const scale = availableWidth/widestSentence;

  return Math.min(MAX_SENTENCE_FONT_SIZE, MAX_SENTENCE_FONT_SIZE*scale);
}

function findWidestSentence(trials) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  ctx.font = `450 ${MAX_SENTENCE_FONT_SIZE}px Consolas, monospace`;

  let widestSentence = "";
  let widestWidth = 0;

  for (const trial of trials) {
    const width = ctx.measureText(trial.text).width;

    if (width > widestWidth) {
      widestWidth = width;
      widestSentence = trial.text;
    }
  }

  return widestSentence;
}

export default {
  name: "App",
  components: { MotrTrial, BrowserCheck },
  data() {
    const listId = chooseListId();
    const practiceTrials = buildPracticeTrials();
    const mainTrials = buildMainTrials(listId);

    const allTrials = [...practiceTrials, ...mainTrials];

    const sentenceFontSize = SENTENCE_FONT_MODE === "responsive"
      ? calculateSentenceFontSize(allTrials)
      : FIXED_SENTENCE_FONT_SIZE;

    const longestSentence = findWidestSentence(allTrials);

    console.log("FONT MODE:", SENTENCE_FONT_MODE);
    console.log("FONT SIZE:", sentenceFontSize);
    
    console.log(`[MoTR] sentence font size: ${sentenceFontSize}px`);
    
    console.log(`[MoTR] list ${listId}: ${practiceTrials.length} practice + ${mainTrials.length} main trials`, mainTrials);
    return { config, listId, practiceTrials, mainTrials, sentenceFontSize, longestSentence, submitting: false };
  },
  created() {
    // magpie replaces the socket with a stub that raises a "no socket URL is set" warning
    // on *any* access -- including magpie's own nextScreen() -- and renders it as a red box
    // on every screen. This experiment does not use sockets, so drop that one warning.
    this.$watch(
      () => this.$magpie.warning,
      (warning) => {
        if (warning && String(warning).includes("no socket URL")) this.$magpie.warning = null;
      }
    );
  },
  mounted() {
    // Pre-fill the participant ID when the study is launched from Prolific.
    const pid = new URLSearchParams(window.location.search).get("PROLIFIC_PID");
    if (pid) this.$magpie.measurements.SubjectID = pid;
  },
  methods: {
    consent() {
      // Experiment-level data. magpie merges it into the first row of getAllData() only;
      // src/submit.js puts it on the first row of every submission.
      this.$magpie.addExpData({
        SubjectId: this.$magpie.measurements.SubjectID,
        ListId: this.listId,
        Experiment: config.experimentName,
      });
      this.$magpie.nextScreen();
    },

    browserCheckDone() {
      this.$magpie.nextScreen();
    },

    /** Record the survey answers, submit, and go to the completion screen. */
    async finish() {
      this.submitting = true;
      const m = this.$magpie.measurements;
      this.$magpie.addTrialData({
        Experiment: config.experimentName,
        TrialType: "survey",
        device: m.device || null,
        hand: m.hand || null,
        feedback: m.feedback || null,
        ...browserInfo(),
        userAgent: navigator.userAgent,
      });
      const all = this.$magpie.getAllData();
      // With per-trial submission only the survey row is still unsent.
      const payload = config.submitEachTrial ? [all[all.length - 1]] : all;
      try {
        await submitRows(this.$magpie, payload, "final");
      } catch (err) {
        // already logged; the completion code is shown regardless
      }
      this.submitting = false;
      this.$magpie.nextScreen();
    },
  },
};
</script>

<style>
.browser-check-text {
  width: 40em;
  max-width: 90%;
  margin: 0 auto;
  text-align: left;
  white-space: normal;
}

.browser-check-text * {
  white-space: normal;
}

.experiment {
  display: flex;
  align-items: center;
  justify-content: center;
}
#consent {
  width: 60em;
  max-width: 95%;
  margin: 0 auto;
  box-sizing: border-box;

  font-family: Arial, Helvetica, sans-serif;
  font-size: 16px;
  line-height: 1.5;
  color: #222222;

  text-align: left;
}


/*
  Only the consent document itself scrolls.
*/
.consent-scrollbox {
  width: 100%;
  height: 500px;

  overflow-y: auto;
  overflow-x: hidden;

  padding: 20px;

  border: 1px solid #04abe3;

  box-sizing: border-box;
  background-color: #ffffff;
}


.consent-title {
  margin: 0 0 10px 0;
  padding: 10px;

  text-align: center;

  font-size: 20px;

  background-color: #d9d9d9;
}


.study-information {
  margin: 0 0 20px 0;
  padding: 10px;

  background-color: #d9d9d9;
}


.study-information p {
  margin: 5px 0;
}


.section-heading {
  margin-top: 22px;
  margin-bottom: 8px;

  font-size: 16px;

  text-decoration: underline;
}


.consent-scrollbox p {
  margin-top: 0;
  margin-bottom: 14px;
}


.final-consent-statement {
  margin-top: 24px;

  font-weight: bold;
}


.continue-instruction {
  margin-top: 15px;

  text-align: center;
}


.participant-id {
  text-align: center;
}


.consent-button {
  text-align: center;
}


#consent a {
  color: #005ea8;
}



  
.large {
  font-size: 24px;
}




  

/* Prevent text selection so participants cannot drag-select the sentence. */
* {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}
.selectable-text {
  -webkit-user-select: text;
  -moz-user-select: text;
  -ms-user-select: text;
  user-select: text;
}
</style>
