# SirenGrid Data Directory

This directory contains data used by the SirenGrid prototype.

## Data Classes

Every important dataset should be clearly identifiable as one of:

1. **Real public/geospatial data** — e.g. road geometry, public POIs, hospital locations.
2. **Real external live data** — only when a real provider is actually connected.
3. **Simulated operational data** — e.g. ambulance positions, hospital load/capacity, traffic-light state.
4. **Synthetic evaluation data** — scenarios created for testing and benchmarking.

## Rules

- Do not present simulated or synthetic data as official/live data.
- Record the source and date/freshness of imported public datasets when possible.
- Do not commit secrets, credentials, API tokens, or private personal data.
- Prefer reproducible source files/scripts over undocumented manual data edits.
- Large generated/cache files should not be committed unless the team explicitly decides they are necessary.

The MVP geographic scope is **Nasr City, Cairo**, with the initial working/demo corridor:
**Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road**.
