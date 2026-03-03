# SWUOnline (Petranaki) in Deckxpert

This codebase was originally built as a virtual **Star Wars: Unlimited** web app (Arena UI + online turns).

In this repository, it is also used as a **rules engine** for headless simulation:
- the same PHP game logic that drives Arena is executed without the browser UI,
- simulations are run via the headless engine and surfaced in the `sim_harness` dashboard.

## What This Repo Is Used For Now

1. **Original Arena app**
- Web gameplay flow and online turn system.
- Useful for manual parity checks against rules behavior.

2. **Headless rules execution**
- Engine interface exposed via `Engine/HeadlessEngine.php` and `EngineCLI.php`.
- Supports initialize game, legal actions, action apply, and state/observation retrieval.

3. **Simulation harness**
- Deterministic single-match and multi-match runs.
- Deck upload/management from SWUDB JSON.
- Match timeline, legality checks, keyword/mechanic audits, and validation matrix.

## Current Simulation Functionality

The simulation UI (`sim_harness.web`) currently supports:
- Deck pools: `candidate`, `meta`, `starter`.
- Deck minimum selection: `30` or `50` cards (for sim setup).
- Single match run with policy and seed.
- Turn-by-turn timeline with:
  - action legality,
  - card metadata (`id`, `cost`, `type`),
  - initiative status,
  - resources (ready/exhausted/total),
  - board state (hands, units, upgrades, captives, force status).
- Round pagination and decision-prompt grouping/substeps.
- Timeline by round/phase summary.
- Keyword Trigger Audit.
- Validation Matrix (mechanic trigger tracking, trigger instances, illegal move tracking).
- Card art hover + modal preview in match timeline.
- Simulation batch runs and result analysis tiles.

## Architecture Overview

- Core rules logic: top-level PHP engine files (`CoreLogic.php`, `GameLogic.php`, `CardLogic.php`, `AllyAbilities.php`, etc.).
- Headless wrapper: `Engine/HeadlessEngine.php`.
- Headless CLI bridge: `EngineCLI.php`.
- Match runner for sim events: `sim_harness/php_match_runner.php`.
- Python dashboard/API for deck + sim operations: `sim_harness/web.py`.

## Quick Start (Docker)

### 1. Start services
```bash
bash petranaki.sh start
```

### 2. Open UIs
- Arena app: `http://localhost:8080/Arena/MainMenu.php`
- Sim dashboard: `http://localhost:8765`

### 3. Stop services
```bash
bash petranaki.sh stop
```

## Quick Start (Sim Harness Only)

If you are running locally without Docker:

1. Ensure Python dependencies are available for `sim_harness`.
2. Ensure PHP CLI is installed and reachable (`php` in `PATH`) or set `PHP_BIN`.
3. Start the dashboard:
```bash
python -m sim_harness.web --host 127.0.0.1 --port 8765
```
4. Open: `http://127.0.0.1:8765`

## Typical Sim Workflow

1. Upload one or more SWUDB deck JSON files.
2. Run **Single Match** to inspect timeline/rules behavior.
3. Review:
- legality,
- resources and board transitions,
- keyword audit,
- validation matrix trigger instances.
4. Run **Simulation** (N games/opponent set) for aggregate performance.
5. Inspect simulation analysis and matchup breakdown.

## Important Notes

- Set-style card IDs (for example `TWI_###`) are mapped to engine UUID IDs by the match runner.
- Unknown set IDs are rejected with explicit errors.
- Single-match mode runs to completion (winner/base-zero condition) with an internal safety cap.
- If PHP is missing, match execution cannot run.

## Key Paths

- [Engine/HeadlessEngine.php](Engine/HeadlessEngine.php)
- [EngineCLI.php](EngineCLI.php)
- [sim_harness/php_match_runner.php](sim_harness/php_match_runner.php)
- [sim_harness/web.py](sim_harness/web.py)
- [sim_harness/README.md](sim_harness/README.md)
- [README-Server-Setup.md](README-Server-Setup.md)

## Contact

Discord: https://discord.gg/AN5GEXSu
