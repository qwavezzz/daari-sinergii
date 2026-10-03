# Checkout and delivery

Status: in progress

Implement requested phone examples and email blur validation; diagnose actual delivery failure and add regression coverage for its cause.

## Result

Phone and email corrections are implemented and browser-verified. Public checkout failure reproduced; sandbox API returns `v2_sender_location_not_recognized` and an empty city directory, including Moscow and Tolyatti. Confirmed independently with the public sandbox account, both with and without insurance. Added precise error classification and CLI diagnosis. User explicitly chose to retain sandbox (no live credentials). External recovery remains unverified; do not label delivery fixed.
