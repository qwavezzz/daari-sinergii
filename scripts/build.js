"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { routes } = require("../src/site-content");
const { renderPage } = require("../src/render");

const projectRoot = path.resolve(__dirname, "..");
const outputRoot = path.join(projectRoot, "dist");

function build() {
  fs.rmSync(outputRoot, { recursive: true, force: true });
  fs.mkdirSync(outputRoot, { recursive: true });

  for (const route of routes) {
    const outputPath = path.join(outputRoot, route.output);
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    fs.writeFileSync(outputPath, renderPage(route), "utf8");
  }

  const assetsDirectory = path.join(outputRoot, "assets");
  fs.mkdirSync(assetsDirectory, { recursive: true });
  fs.copyFileSync(path.join(projectRoot, "src", "styles.css"), path.join(assetsDirectory, "styles.css"));
  fs.copyFileSync(
    path.join(projectRoot, "src", "presentation-runtime.js"),
    path.join(assetsDirectory, "presentation-runtime.js"),
  );
  fs.copyFileSync(
    path.join(projectRoot, "src", "shared-interactions.js"),
    path.join(assetsDirectory, "shared-interactions.js"),
  );
  fs.cpSync(
    path.join(projectRoot, "src", "variants"),
    path.join(assetsDirectory, "variants"),
    { recursive: true },
  );

  console.log(`Generated ${routes.length} routes in ${path.relative(projectRoot, outputRoot)}.`);
}

if (require.main === module) {
  build();
}

module.exports = { build, outputRoot };
