/**
 * Loads the experimental materials and builds the trial sequence.
 *
 * Files (see materials/README.md for the column spec):
 *   materials/lists/list_NN.csv   critical items, one list per participant group
 *   materials/fillers.csv         filler sentences shown to everyone
 *   materials/practice.csv        practice sentences shown before the main trials
 *
 * All CSVs are bundled into the app at build time by csv-loader (see vue.config.js).
 */
import _ from "lodash";
import config from "./config";
import practiceRows from "../materials/practice.csv";

//helper for loading folders contaning list_a.csv, etc 
function loadLists(context){
  const lists = {};
  
  context.keys().forEach((key) => {
    const match = key.match(/list_([A-Za-z0-9]+)\.csv$/);
    
    if (match){
      const id = match[1];
      lists[id] = context(key);
    }
  });
  return lists;
}

//expererimental lists ---- block 2

const expBlock2Context = require.context(
  "../materials/lists_exp_block_2_shuffled",
  false,
  /^\.\/list_[A-Za-z0-9]+\.csv$/
);

const expBlock2Lists = loadLists(expBlock2Context);

//filler lists -- block 2
const fillerBlock2Context = require.context(
  "../materials/lists_filler_block_2",
  false,
  /^\.\/list_[A-Za-z0-9]+\.csv$/
);

const fillerBlock2Lists = loadLists(fillerBlock2Context);



//experimental lists --- block 3
const expBlock3Context = require.context(
  "../materials/lists_exp_block_3_shuffled",
  false,
  /^\.\/list_[A-Za-z0-9]+\.csv$/
);

const expBlock3Lists = loadLists(expBlock3Context);


//filler lists --- block 3
const fillerBlock3Context = require.context(
  "../materials/lists_filler_block_3",
  false,
  /^\.\/list_[A-Za-z0-9]+\.csv$/
);

const fillerBlock3Lists = loadLists(fillerBlock3Context);


//only list IDs that exist in all four folders
export const listIds = Object.keys(expBlock2Lists)
  .filter(
    (id) =>
      fillerBlock2Lists[id] &&
      expBlock3Lists[id] &&
      fillerBlock3Lists[id]
  )
  .sort();


/**
 * Pick the list for this participant: ?LIST_ID=N in the URL wins; otherwise
 * config.defaultList ("random" or a list number).
 */
export function chooseListId() {
  if (listIds.length === 0) {
    throw new Error("No matching list IDs found across all four list folders.");
  }
  
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("LIST_ID");
  
  if (requested !== null) {
    if(listIds.includes(requested)){
      return requested;
    }
    console.warn(`[MoTR] LIST_ID=${requested} does not exist in all four fodlers; falling back to default`);
    
  }
  
  if (config.defaultList === "random") return _.sample(listIds);
  const defautlId = String(config.defaultList);
  
  return listIds.includes(defaultId) ? defaultId : listIds[0];
}


//trial conversion
function isBlank(value) {
  return value === undefined || value === null || String(value).trim() === "";
}

/** Convert a CSV row into the trial object consumed by <MotrTrial>. */
function toTrial(row, phase) {
  return {
    item_id: String(row.item_id),
    condition_id: String(row.condition_id),
    text: String(row.text).trim(),
    question: isBlank(row.question) ? null : String(row.question),
    // options are pipe-separated in the CSV, e.g. "Yes|No"
    options: isBlank(row.options)
      ? null
      : String(row.options)
          .split("|")
          .map((s) => s.trim()),
    correct: isBlank(row.correct) ? null : String(row.correct),
    phase, // "practice" | "main"
    row, // the full original CSV row, in case you need extra columns
  };
}

/** Practice trials, in file order. */
export function buildPracticeTrials() {
  return practiceRows.slice(0, config.nPractice).map((r) => toTrial(r, "practice"));
}

/**
 * trials randomized every time -- so when refresh a page/new participant enters same list, they appear in different order 
 * CONSTRAINT: no same condition will appear twice in a row.
 */

function shuffleWithConditionConstraint(items){
  if (items.length === 0){
    return [];
  }

  //group trials by condition_id
  const groups = {};

  items.forEach((item) => {
    const condition = item.condition_id;

    if (!groups[condition]){
      groups[condition] = [];
    }
    groups[condition].push(item);
  });

  //randomize order of items WITHIN each condition group
  Object.keys(groups).forEach((condition) => {
    groups[condition] = _.shuffle(groups[condition]);
  });

  //check whether valid arrangement is possible -- so if one condition is over half of all items, you cannot arrange them so that the same condition doesnt repeat in a row
  const largestGroup = Math.max(
    ...Object.values(groups).map((rows) => rows.length)
  );

  if (largestGroup > Math.ceil(items.length / 2)) {
    throw new Error(
      "Impossible to arrange experimental trials without repeating a condition."
    );
  }

  const result = [];
  let previousCondition = null;

  while (result.length < items.length){
    //conditions we are allowed to use next -- anything but previousCondition
    const candidates = Object.keys(groups).filter(
      (condition) => 
        groups[condition].length >0 &&
        condition !== previousCondition
    );

    if (candidates.length === 0){
      throw new Error(
        "Could not arrange without repeating a condition."
      );
    }

    //prefer condition with most remaining trials
    const largestRemaining = Math.max(
      ...candidates.map((condition) => groups[condition].length)
    );

    const largestCandidates = candidates.filter(
      (condition) =>
        groups[condition].length === largestRemaining
    );

    //if multiple conditions have the same length, choose randomly
    const chosenCondition = _.sample(largestCandidates);

    //take 1 randomized trial from chosenCondition
    const trial = groups[chosenCondition].pop();

    result.push(trial);

    previousCondition = chosenCondition; //now you can start while loop again, this being reset for current condition
  }

  //safety check
  for (let i=1; i<items.length; i++){
    if (result[i].condition_id === result[i-1].condition_id){
      throw new Error("Two identical conditions ended up next to each other.");
    }
  }

  return result;
}
















//interleave filters into items

function interleaveFillers(items, fillers){
  const shuffledFillers = _.shuffle(fillers);
  
  //exp items stay in their order
  const result = [...items];
  
  shuffledFillers.forEach((filler) => {
    const randomIndex = Math.floor(Math.random() * (result.length+1)
    );
    result.splice(randomIndex, 0, filler);
  });
  return result;
}

//main exp

export function buildMainTrials(listId) {
  //block 2
  const block2Items = shuffleWithConditionConstraint(
    expBlock2Lists[listId].map(
      (r) => toTrial(r,"main")
    )
  );
    
  const block2Fillers = 
    fillerBlock2Lists[listId].map(
      (r) => toTrial(r,"main")
    );
    
  const block2 = interleaveFillers(
    block2Items,
    block2Fillers
  );
    
  //block 3
  const block3Items = shuffleWithConditionConstraint(
    expBlock3Lists[listId].map(
      (r) => toTrial(r,"main")
    )
  );
  
  const block3Fillers = 
    fillerBlock3Lists[listId].map(
      (r) => toTrial(r,"main")
    );
  const block3 = interleaveFillers(
    block3Items,
    block3Fillers
  );
  
  //block2 finishes before block3 begins
  return block2.concat(block3);
}
