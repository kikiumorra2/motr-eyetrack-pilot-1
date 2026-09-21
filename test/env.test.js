// Sanity check for the JS test environment. The Vue CLI 4 build can stay on Node 16
// (.nvmrc), but the unit tests use node:test + ESM and need a recent Node.
import { test } from "node:test";
import assert from "node:assert/strict";

test("node >= 22 for the test runner", () => {
  const major = Number(process.versions.node.split(".")[0]);
  assert.ok(
    major >= 22,
    `npm test needs Node >= 22 (found ${process.version}); run e.g. \`nvm use 22\``
  );
});
