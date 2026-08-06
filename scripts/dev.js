"use strict";

const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { build, outputRoot } = require("./build");

const port = Number.parseInt(process.env.PORT || "4173", 10);
const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

function resolveRequestPath(requestUrl) {
  const pathname = decodeURIComponent(new URL(requestUrl, "http://localhost").pathname);
  const relativePath = pathname.endsWith("/") ? `${pathname}index.html` : pathname;
  const resolvedPath = path.resolve(outputRoot, relativePath.replace(/^[/\\]+/, ""));
  const relativeToOutput = path.relative(outputRoot, resolvedPath);

  if (relativeToOutput.startsWith("..") || path.isAbsolute(relativeToOutput)) {
    return null;
  }

  return resolvedPath;
}

build();

const server = http.createServer((request, response) => {
  const requestedPath = resolveRequestPath(request.url || "/");
  if (!requestedPath || !fs.existsSync(requestedPath) || !fs.statSync(requestedPath).isFile()) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Страница не найдена");
    return;
  }

  response.writeHead(200, {
    "Content-Type": mimeTypes[path.extname(requestedPath)] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  fs.createReadStream(requestedPath).pipe(response);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Development server: http://localhost:${port}`);
});
