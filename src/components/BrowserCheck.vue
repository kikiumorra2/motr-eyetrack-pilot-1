<!--
  BrowserCheck — asks the participant to set the browser zoom to 100% before the study.
  The MoTR window and the word boxes are defined in CSS pixels, so a zoomed page changes
  their physical size on screen. The check re-runs whenever the window is resized (zoom
  changes fire a resize event). Settings: config.browserCheck.
-->
<template>
  <div class="browser-check">

    <!-- STEP 1 -->
    <template v-if="!showPreview">
      <p>
        <b>Please reset your browser zoom to 100% before continuing.</b>
      </p>

      <p>
        Press <kbd>Ctrl</kbd> + <kbd>0</kbd> on Windows/Linux,
        or <kbd>&#8984;</kbd> + <kbd>0</kbd> on Mac.
      </p>

      <p>
        Please use a desktop or laptop computer with a mouse or trackpad,
        <b>make this window full-screen</b> and not bigger than your screen. Keep it open and do not change the zoom until the study is complete.
      </p>

      <button @click="showPreview = true">
        I have reset the zoom to 100% and maximized my window
      </button>
    </template>

    <!-- STEP 2 -->
    <template v-else>
      <p>
        <b>Please check text box below.</b>
      </p>

      <p>
        Being able to see the entire text is crucial for this study, so if you cannot fully see "START" and "END" in the box,
        <b>we kindly ask you to quit this study.</b> Thank you.
      </p>

      <div class="sentence-preview-window">
        <div
          class="sentence-preview"
          :style="{ fontSize: sentenceFontSize + 'px' }"
        >{{previewSentence}}</div>
      </div>


      <button @click="$emit('done')">
        The text fits on my screen
      </button>
    </template>

  </div>
</template>


<script>

export default {
  name: "BrowserCheck",

  props: {
    longestSentence: {
      type: String,
      required: true,
    },

    sentenceFontSize: {
      type: Number,
      required: true,
    },
  },

  data() {
    return {
      showPreview: false,
    };
  },

  computed: {
    previewSentence() {
      //return "With schools still closed, cars still buried and streets still blocked by the widespread weekend snowstorm, officials are asking people to help out.";
        return "START--------------------------------------------------------------------------------------------------------------------------------------------END";
    },
  },
};
</script>

<style>
.browser-check kbd {
  border: 1px solid #999;
  border-radius: 3px;
  padding: 0 4px;
  font-family: inherit;
}

.sentence-preview-window {
  width: calc(100vw - 2px);
  max-width: calc(100vw - 2px);

  margin-top: 30px;
  margin-bottom: 30px;

  margin-left: 50%;
  transform: translateX(-50%);

  overflow: hidden;
  box-sizing: border-box;

  border: 1px solid #999;
  padding: 1px;
}

.sentence-preview {
  font-family: Consolas, monospace;
  font-weight: 450;

  white-space: nowrap !important;
  width: 100%;

  text-align: center;

  pointer-events: none;

  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
}
</style>
