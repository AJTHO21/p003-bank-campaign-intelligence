# Source and provenance

Moro, S., Rita, P., & Cortez, P. (2014). *Bank Marketing* [Dataset]. UCI Machine Learning Repository. DOI 10.24432/C5K306. [Dataset citation](https://doi.org/10.24432/C5K306)

- Repository identifier is UCI 222. [Catalog](https://archive.ics.uci.edu/dataset/222/bank+marketing)
- License is Creative Commons Attribution 4.0 International. [License](https://creativecommons.org/licenses/by/4.0/)
- The script downloads UCI's public archive and extracts `bank-additional-full.csv` and `bank-additional-names.txt` from `bank-additional.zip`. [Official download](https://archive.ics.uci.edu/static/public/222/bank%2Bmarketing.zip)
- Version is the full bank-additional variant. UCI's catalog provides no numbered revision for this specific file. The CSV SHA-256 gives the acquired revision a content identity.
- Acquired on 2026-11-21 at 16:41:36 UTC. The selected CSV SHA-256 is `74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8`. Both archives, the selected CSV, and the bundled notes passed snapshot verification.

## Local snapshot verification

Run `python3 scripts/acquire.py` from the repository root. On first acquisition, the script checks the selected CSV and writes a local `data/raw/uci-222/manifest.json` recording source details, archive member names, byte sizes, and SHA-256 fingerprints for the four files. On rerun it verifies the existing files against that manifest. The PostgreSQL loader also checks the selected CSV against the project's pinned fingerprint. The snapshot and manifest are ignored by Git and are generated locally. [Acquisition script](../scripts/acquire.py) · [PostgreSQL ingestion](postgresql-ingestion.md)
