# 0001 MVP-0 architecture and Base / Runtime usage

Date: 2026-09-27 — Status: accepted (provisional with MViser#2)

## Context

MViser#2 defines MVP-0. The workspace also offers KiNoTch. Repository Base (v0.5.9),
KiNoTch. Runtime (v0.1.0, provisional Python reference) and the Default Canary as an adoption example.

## Decision

1. **Adopt Repository Base 0.5.9** with profile `cli` (surface `cli`). Project code lives in `project/**`;
   `knt doctor / setup / test / verify` are the entry points, following the Default Canary layout.
2. **CLI Surface Default = OVERRIDE**: the Base CLI kit is PowerShell; MViser's CLI is Python argparse in the same process as the core.
   **ci-test Default = DISABLED**: the Base-owned `.github/workflows/verify.yml` already runs doctor → setup → verify on Ubuntu and Windows.
3. **Runtime not used in MVP-0** (`runtime.modules: []`). Runtime Contracts are provisional, the package is not distributed,
   and Base rules forbid copying Runtime into individual repos. Rendering is, however, a natural future consumer of
   Progress / Cancellation / Artifact semantics; `project/contracts/actions.json` declares the actions so a later Pilot can bind them.
4. Internal time unit is the frame; rendering never sees BPM/measures (MViser#2 Timeline model).
5. Frames are piped as raw RGB to FFmpeg (no temporary PNGs); PNG sequence is a separate export for AviUtl / After Effects.

## Consequences

- Python ≥ 3.10, Pillow, PyYAML, imageio-ffmpeg are the only dependencies.
- Revisit Runtime adoption when a GUI/long-running render needs cancellation or when Runtime Progress becomes a stable candidate.
