# DOGFOOD — pioneer-ledger-tui

_Session: 2026-04-23T12:44:43, driver: pty, duration: 3.0 min_

**PASS** — ran for 0.5m, captured 6 snap(s), 1 milestone(s), 0 blocker(s), 1 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found **1 major(s)**, 1 UX note(s). Game state never changed during the session. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 2 coverage note(s) — see Coverage section.

## Findings

### Blockers

_None._

### Majors
- **[M1] state appears frozen during golden-path play**
  - Collected 10 state samples; only 1 unique. Game may not be receiving keys.
  - Repro: start game → press right/up/left/down repeatedly

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)
- **[U1] state() feedback is coarse**
  - Only 1 unique states over 14 samples (ratio 0.07). The driver interface works but reveals little per tick.

## Coverage

- Driver backend: `pty`
- Keys pressed: 160 (unique: 12)
- State samples: 14 (unique: 1)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=6.2, B=5.8, C=18.1
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/pioneer-ledger-tui-20260423-124411`

Unique keys exercised: ?, R, down, enter, escape, left, n, p, r, right, space, up

### Coverage notes

- **[CN1] Phase A exited early due to saturation**
  - State hash unchanged for 10 consecutive samples after 9 golden-path loop(s); no further learning expected.
- **[CN2] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `pioneer-ledger-tui-20260423-124411/milestones/first_input.txt` | key=right |
