import Vue from "vue";
import VueKonva from "vue-konva";
import VueMagpie from "magpie-base";
import App from "./App.vue";
import magpieConfig from "./magpie.config.js";

Vue.config.productionTip = false;

// Konva canvas components (a magpie peer dependency)
Vue.use(VueKonva, { prefix: "Canvas" });

// magpie components ($magpie, <Experiment>, <Screen>, inputs, ...)
Vue.use(VueMagpie, magpieConfig);

new Vue({
  render: (h) => h(App),
}).$mount("#app");
