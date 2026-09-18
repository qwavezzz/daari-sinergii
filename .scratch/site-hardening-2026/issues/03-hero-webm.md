# Hero WebM

Status: resolved

Create a smaller VP9 WebM version of the hero video, prefer it in the `<video>` source list and preserve the H.264 MP4 fallback and WebP poster.

## Answer

Added a 960×540, 18 fps VP9 WebM (1.43 MB) before the existing 2.41 MB MP4 fallback. Browser QA selected WebM, reported readyState 4, and retained the WebP reduced-motion poster.
