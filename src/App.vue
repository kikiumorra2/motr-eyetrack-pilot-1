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
                RESEARCH INFORMED CONSENT FORM
            </h1>

            <div class="study-information">
                <p>
                    <strong>STUDY TITLE:</strong>
                    Developing and Testing Language Models with Cognitively Plausible Memory (IRB-FY2026-11698)
                </p>

                <p>
                    <strong>INVESTIGATOR(S):</strong>
                    Tal Linzen
                </p>
            </div>

            <h2 class="section-heading">
                FUNDING SPONSOR:
            </h2>

            <p>
                National Institute of Biomedical Imaging and Bioengineering (NIH NIBIB)
            </p>
            
             <h2 class="section-heading">
                INVITATION TO BE A PART OF A RESEARCH STUDY
            </h2>

            <p>
                You are invited to participate in a research study. This form has information to help you decide 
                whether or not you wish to participate - please review it carefully. Your participation is voluntary.
                Please ask any questions you have about the study or about this form before deciding to 
                participate.
            </p>
            
            <h2 class="section-heading">
                PURPOSE OF THE STUDY
            </h2>

            <p>
                The purpose of this research study is to understand how the human mind is able to read sentences,
                what makes some sentences more difficult than others, and how human memory limitations
                influence the way we process sentences with particular grammatical structures.
            </p>
            
            <h2 class="section-heading">
                ELIGIBILITY TO PARTICIPATE
            </h2>

            <p>
                You are eligible to participate in this study if you are a native speaker of English, or, if otherwise
                specified, another language (e.g. French, German, Korean, Russian), and are over the age of 18.
                You should not participate if you are not a native speaker of the target language of the study, or are 
                under the age of 18.
            </p>
            <p>
                To determine if you are eligible, we will ask you to self-report your age and whether you are a native
                speaker of the target language before the experiment begins.
            </p>
            
            <h2 class="section-heading">
                DESCRIPTION OF PROCEDURES
            </h2>

            <p>
                If you agree to participate, you will be asked to:
            </p>
            
            <p>
                1. Read the study instructions. This should take approximately one minute.
            </p>
            
            <p>
                2. Complete approximately five practice sentences to familiarize yourself with the task. You will
                press keys on your keyboard that will reveal each word of a sentence, then you may be
                asked to answer a multiple-choice question about the sentence with your keyboard. This
                should take approximately five minutes.
            </p>
            
            <p>
                3. You will then complete the experiment. The task will be the same as that of the practice
                trials described above. This should take approximately twenty to thirty-five minutes. Finally,
                you will be presented with debriefing information, which should take less than one minute to
                read, and you will receive your compensation within one day of completion.
            </p>

            <h2 class="section-heading">
                RISKS OR DISCOMFORTS
            </h2>

            <p>
                This study involves the following risks or discomforts: The risks associated with participation in this
                study are no greater than those encountered in daily life. Because the study collects some
                information considered to be personally identifiable, there is always a risk of a breach of
                confidentiality.
            </p>
                
            <p>
                Please tell the researchers if you believe you are harmed from your participation in the study.
            </p>
            
            <h2 class="section-heading">
                BENEFITS
            </h2>

            <p>
                There are no direct benefits to you from participating in this study. This study may benefit society if
                the results lead to a better understanding of what makes certain aspects of language easier or
                harder to learn and understand.
            </p>
            
            <h2 class="section-heading">
                COMPENSATION
            </h2>

            <p>
                Immediately upon completion of the study or decision to withdraw from the study, you will be
                credited $15 to your specified Prolific account within one day of your completion or decision to
                withdraw.
            </p>

            <h2 class="section-heading">
                VOLUNTARY PARTICIPATION
            </h2>

            <p>
                Participating in this study is completely voluntary. You may choose not to take part in the study or
                to stop participating at any time, for any reason, without penalty or negative consequences.
                If you withdraw from the study early there are no penalties, and you will not lose any benefits to
                which you would otherwise be entitled.
            </p>

            <p>
                If you withdraw or are withdrawn from the study early, then we will keep information about you that
                is already collected, but we will destroy the collected information upon your request.
            </p>

            <h2 class="section-heading">
                PRIVACY & DATA CONFIDENTIALITY
            </h2>

            <p>
                In this study, you may be asked to provide information that could be used to identify you personally.
                This information will be kept confidential. Only researchers and others that will keep the information
                confidential (e.g., regulatory agencies or oversight groups) may access information that could
                personally identify you.
            </p>

            <p>
                This research is covered by a Certificate of Confidentiality from the National Institutes of Health.
                Researchers with this Certificate will not disclose or use information that may identify you in any
                federal, state, or local civil, criminal, administrative, legislative, or other action, suit, or proceeding, 
                even if there is a court subpoena.
            </p>
            
            <p>
                Exceptions include:
            </p>
            
            <p>
                - A federal, state, or local law requires disclosure.
            </p>
            
            <p>
                - Your explicit approval for the researchers to release your name or any other personally 
                identifiable information.
            </p>
            
            <p>
                <em>
                    Future Use of Data
                </em>
            </p>
            
            <p>
                Information about you collected for this study may be shared with other researchers, used for other 
                research studies, or placed in a data repository. These studies may be similar to this study or 
                completely different. All information that could identify you will be removed before sharing the data 
                or using it for other research studies. We will not ask you for additional permission before sharing 
                the information.
            </p>

            <h2 class="section-heading">
                ACCESS TO YOUR STUDY INFORMATION
            </h2>

            <p>
                We will give you access to the information that is collected about you in this study. Participants may 
                request collected information directly from the research team by emailing Tal Linzen at 
                tl876@nyu.edu.
            </p>

            <h2 class="section-heading">
                CONTACT INFORMATION
            </h2>

            <p>
                You are encouraged to ask questions at any time during this study. For information about the study, 
                contact Tal Linzen at tl876@nyu.edu.
            </p>

            <p>
                If you have questions about your rights as a research participant or if you believe you have been 
                harmed from the research, please contact the NYU Human Research Protection Program at 
                (212)998-4808 or ask.humansubjects@nyu.edu.
            </p>
            
            <h2 class="section-heading">
                AGREEMENT TO PARTICIPATE
            </h2>

            <p>
                <b>Participant:</b> By checking the box below and pressing “continue", you are agreeing to participate in 
                this study. Make sure you understand what the study involves before you check the box and press 
                continue. If you have any questions about the study after you agree to participate, you can contact 
                the research team using the information provided above. You may keep a copy of this form.
            </p>

            <p class="continue-instruction">
              If you agree to participate, please check the box below,
              enter your Prolific ID, and press "Continue."
              Otherwise, you may exit this page.
            </p>
            
            <p>
              <label>
                <input
                  type="checkbox"
                  v-model="consentAgreed"
                />
                I have read and understand the information above,
                and I agree to participate in this study.
              </label>
            </p>
            
            <p class="participant-id">
              Prolific ID:
              <input
                type="text"
                v-model="$magpie.measurements.SubjectID"
              />
            </p>
            
            <div class="consent-button">
              <button
                :disabled="!consentAgreed || !$magpie.measurements.SubjectID || $magpie.measurements.SubjectID.trim().length < 2"
                @click="consent"
              >
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
    return { config, listId, practiceTrials, mainTrials, sentenceFontSize, longestSentence, submitting: false, consentAgreed: false };
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
