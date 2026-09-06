# Phase 00 Evaluation Inputs

`cases.json` is synthetic/team-created Egyptian Arabic text used only for the
feasibility spike. It is not a live emergency feed and contains no authoritative
coordinates.

Place 3–5 short team-created audio recordings under `audio/` and one synthetic or
team-created image under `images/` when available. The runner discovers supported
files without creating media or treating missing media as a successful check.

Audio ground truth may be supplied as a same-stem `.txt` file for local quality
review. Raw text cases and media paths are preserved as replay inputs; provider
responses are written only to ignored `artifacts/phase00/` output.
