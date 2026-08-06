"use strict";

// Replace only these local paths after the owned, approved media set is supplied.
// Empty paths are intentional: the renderer will not emit empty source or poster
// attributes, so browsers never request the current page as missing media.
const heroMedia = Object.freeze({
  poster: "",
  sources: Object.freeze([
    Object.freeze({ format: "webm", type: "video/webm", src: "" }),
    Object.freeze({ format: "mp4", type: "video/mp4", src: "" }),
  ]),
});

const motionBudgets = Object.freeze({
  full: Object.freeze({
    framesPerSecond: 30,
    pixelRatio: 1.75,
    ambientParticles: 72,
    mediaParticles: 34,
  }),
  compact: Object.freeze({
    framesPerSecond: 20,
    pixelRatio: 1.25,
    ambientParticles: 24,
    mediaParticles: 12,
  }),
  reduced: Object.freeze({
    framesPerSecond: 0,
    pixelRatio: 1,
    ambientParticles: 18,
    mediaParticles: 8,
  }),
});

module.exports = { heroMedia, motionBudgets };
