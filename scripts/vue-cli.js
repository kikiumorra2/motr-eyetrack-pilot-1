#!/usr/bin/env node
// Thin wrapper around vue-cli-service.
// The magpie stack is Vue CLI 4 / webpack 4, which needs OpenSSL's legacy provider on
// Node >= 17. This adds the flag automatically so `npm run serve` / `npm run build`
// work on any Node version without extra setup.
const { spawnSync } = require("child_process");

const major = Number(process.versions.node.split(".")[0]);
const env = { ...process.env };
if (major >= 17 && !(env.NODE_OPTIONS || "").includes("--openssl-legacy-provider")) {
  env.NODE_OPTIONS = ((env.NODE_OPTIONS || "") + " --openssl-legacy-provider").trim();
}

const result = spawnSync("vue-cli-service", process.argv.slice(2), {
  stdio: "inherit",
  env,
  shell: true,
});
process.exit(result.status === null ? 1 : result.status);
