/**
 * The single place where data leaves the browser.
 *
 * By default `rows` (an array of flat objects, one per mouse sample / trial summary) is sent
 * to the magpie server from src/magpie.config.js:
 *     POST {serverUrl}/api/submit_experiment/{experimentId}   body: JSON array of rows
 * To use a different backend, change serverUrl (any magpie server works as is) or replace
 * the body of this function with your own request.
 *
 * Every submission gets the experiment-level data (SubjectId, ListId, Experiment,
 * experiment_start_time, ...) on its first row (withExpData below): magpie's getAllData() merges
 * it into the first row of ALL recorded data only, so a per-trial submission after the first —
 * and the survey row — would otherwise carry none of it and the postprocessing could not tell
 * which participant it belongs to (1_fetch_and_flatten.py drops such rows, with a warning).
 *
 * In debug mode nothing is sent; the rows are printed to the browser console and collected
 * in window.__motrRows, so a whole session can be saved from the console with
 *     copy(JSON.stringify(window.__motrRows))
 * (paste into rows.json for postprocessing/plot_char_events.py or motr_char_events.py --check).
 */

const missing = (v) => v === undefined || v === null || v === "" || v === "NA";

/** Copy of `rows` whose first row carries every field of `expData` it does not already have. */
export function withExpData(rows, expData) {
  if (!rows.length) return rows;
  const first = { ...rows[0] };
  for (const [key, value] of Object.entries(expData || {})) {
    if (missing(first[key]) && !missing(value)) first[key] = value;
  }
  return [first, ...rows.slice(1)];
}

export async function submitRows(magpie, rows, label) {
  if (!rows.length) return;
  const exp = magpie.expData || {};
  const now = Date.now();
  rows = withExpData(rows, {
    ...exp,
    // the two fields magpie itself computes in getAllData()
    ...(exp.experiment_start_time > 0 && {
      experiment_end_time: now,
      experiment_duration: now - exp.experiment_start_time,
    }),
  });
  if (magpie.debug) {
    const store = (window.__motrRows = window.__motrRows || []);
    store.push(...rows);
    console.log(
      `[MoTR] debug mode: not submitting ${rows.length} rows (${label}); ${store.length} rows collected in window.__motrRows`,
      rows
    );
    return;
  }
  try {
    await magpie.submitResults(magpie.submissionUrl, rows);
  } catch (err) {
    console.error(`[MoTR] submission failed (${label})`, err);
    throw err;
  }
}
