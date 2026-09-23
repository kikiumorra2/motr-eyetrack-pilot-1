// magpie server / deployment settings.
// See https://magpie-experiments.org/ for the full list of options.
export default {
  // Numeric experiment ID created on the magpie server. Every submission is stored under it.
  experimentId: "388",

  // magpie backend that receives the data.
  serverUrl: "https://magpie-serverless.vercel.app",

  // Used in 'prolific' mode: participants are redirected here after the final screen.
  // The code must match `completionCode` in src/config.js.
  completionUrl: "https://app.prolific.com/submissions/complete?cc=CCH6PRPT", 

  contactEmail: "wpt2011@nyu.edu",

  // 'debug'      – nothing is sent to the server; data is logged to the browser console.
  // 'directLink' – submits to the server; participant ID is typed in on the consent screen.
  // 'prolific'   – like directLink, but also records Prolific URL parameters and redirects
  //                to completionUrl at the end.
  mode: "prolific",

  language: "en",
};
