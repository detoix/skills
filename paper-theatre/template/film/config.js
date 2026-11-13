// This film's settings for the stage (stage.js). The tools read film.json; these are the picture's.

// Which words get which colour of card when a label has no style of its own (stage.js chipStyle):
// gold highlight · red name · violet legend/myth · white number · kraft everything else.
// Stems of this film's words, matched at the start of the word, case-insensitive.
export const WORDS = [
  [/^\d/i, 'number'],   // add number words or subject-specific stems for the narration language
];

// The timeline rail under the stage (shown when the story moves to another time, cues in film.js ERAS):
// Set the range for the film before adding cues. Either direction is supported.
export const RAIL_YEARS = { from: 0, to: 100, tick: 10, major: 20 };

// The maps' paper (geo.js): sea and lakes, the land and two shades of patches on it, rivers, the reference border.
export const MAP = { sea: '#4f7f9e', water: '#4f7f9e', land: '#e6d7b2', land2: '#b3b47c', land3: '#cdc394', border: 'rgba(42,32,25,0.55)' };
