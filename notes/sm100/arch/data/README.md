# B200 tcgen05 primary evidence

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** probes and Modal runners linked from the parent research notes
**Open items:** none
**Audit:** lossless archives of the primary records cited by the curated notes

## Conclusion

This directory preserves the primary records cited by the
[current model and evidence index](../tcgen05_microarch_speculation.md).
Raw JSON results and source/request snapshots are stored as deterministic
gzip files. No fields or samples have been removed from the accepted records.
Summaries, figures, and figure data remain directly readable.

## Evidence

[manifest.json](manifest.json) maps every archived file to its original path,
byte length, SHA-256 hash, and citing notes. It records hashes for both the
stored file and the original bytes. The archived results/request records carry
the original experiment sources and run metadata where supplied by the runner;
these snapshots take precedence over later edits to the working probes.

From the repository root:

```sh
python3 tools/tcgen05_evidence.py verify
python3 tools/tcgen05_evidence.py unpack
```

`verify` checks the stored and decompressed bytes without writing files.
`unpack` additionally restores original JSON filenames for the reproduction
commands in each note. It accepts an existing identical file and refuses to
overwrite different bytes. Restored payloads are ignored by Git.

Only complete, validated measurements support the conclusions. One explicitly
qualified partial AS gap run contributes its 232 completed configurations;
its full payload and the qualification are retained. Queue logs, failed loader
attempts, incomplete transport logs, and superseded interpretations are not
part of this curated evidence set. A successful record may retain incidental
diagnostic fields as part of its unchanged original bytes.

These hashes ensure archive integrity, not independent validation of hardware
claims. Read the construction, controls, and inference limits in the citing note.

## History / retracted hypotheses

Curated on 2026-11-21 from the November B200 experiment records.
