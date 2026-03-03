# sim_harness

`sim_harness` is the Python + PHP simulation layer on top of the SWU engine.

It uses the same core rules logic as Arena, but runs matches headlessly for:
- deterministic single-match inspection,
- batch simulation analysis,
- rules/mechanic validation from real match logs.

## What It Does

1. **Deck management**
- Upload SWUDB JSON decks.
- Store decks in local pools: `candidate`, `meta`, `starter`.

2. **Single match execution**
- Run one match with a selected policy and seed.
- Capture per-step events with legal/illegal result and board snapshots.
- Show timeline paged by round with optional decision prompts.

3. **Batch simulation**
- Run candidate deck vs selected opponent pool.
- Track aggregate win rates and matchup summaries.

4. **Validation tooling**
- Keyword Trigger Audit.
- Validation Matrix with trigger instances and illegal move tracking.

## Core Files

- Runner: [php_match_runner.php](php_match_runner.php)
- Web dashboard/API: [web.py](web.py)
- CLI deck/sim management: [cli.py](cli.py)
- Persistent deck store: `sim_harness/data/decks.json`
- Persistent sim history: `sim_harness/data/simulations.json`

## Run the Dashboard

```bash
python -m sim_harness.web --host 127.0.0.1 --port 8765
```

Open:
- `http://127.0.0.1:8765`

Requirements:
- Python 3
- PHP CLI available in `PATH` (or set `PHP_BIN`)

If PHP is missing, match execution will fail with a PHP binary error.

## Single Match Behavior

Single-match run path:
1. Decks are normalized and ID-mapped.
2. Headless game initializes from the engine.
3. Legal actions are requested from `Engine/LegalActions.php`.
4. Action is selected by policy.
5. Action is applied through headless engine.
6. Event row is recorded with board state before/after.
7. Loop continues until winner/base-zero (or internal safety cap).

### Policies

- `random_legal` (default): random among legal actions.
- `random_non_pass`: bias away from pass where possible.
- `first_non_pass`: deterministic legacy style.

## UI Features (Current)

- Round-based timeline pagination.
- Decision prompt grouping into substeps (`4a`, `4b`, etc.) with raw step mapping.
- Match JSON (collapsible by default).
- Card image hover + full-size modal in timeline rows.
- Action detail summaries including:
  - damage,
  - deployments,
  - defeated units,
  - upgrade changes,
  - stat deltas,
  - capture changes,
  - experience/token unit creation,
  - leader/epic triggers.
- Board state lines showing:
  - HP, force, hand/deck/discard,
  - ready/exhausted/total resources,
  - active units with upgrades/captives,
  - captured-unit summary.
- Validation Matrix with expandable instance lists.
- Keyword Trigger Audit table.

## Simulation CLI (Batch)

Examples:

```bash
python -m sim_harness.cli deck upload --file path/to/deck.json --pool candidate --deck-id my-candidate
python -m sim_harness.cli deck upload --file path/to/meta.json --pool meta
python -m sim_harness.cli deck upload --file path/to/starter.json --pool starter

python -m sim_harness.cli deck list --pool all
python -m sim_harness.cli deck show my-candidate --format swudb

python -m sim_harness.cli sim create --candidate my-candidate --opponents all --games 25 --seed 123
python -m sim_harness.cli sim results sim-20260101-120000
python -m sim_harness.cli sim analysis sim-20260101-120000
```

## Rule/Engine Notes

- Set IDs (like `TWI_###`) are mapped to engine UUID IDs in the runner.
- Unknown set IDs are rejected with explicit error output.
- Event logs include legality at apply-time (not just pre-selection).
- Illegal probes can be retried in-step when alternatives exist.

## Validation Matrix Scope

The matrix is log-derived and only marks mechanics when evidence exists in action/event data.
It is intended for simulation QA, not full formal proof of every card text branch.

For deep checks:
1. open trigger instances,
2. inspect the linked timeline steps,
3. confirm board-state transitions and prompts.

## Troubleshooting

### `php: command not found`
Install PHP CLI or set `PHP_BIN` environment variable.

### “Unknown set card IDs (no UUID mapping)”
Deck contains IDs not present in current engine dictionary build.

### UI step numbers look inconsistent
Timeline displays grouped step labels; matrix instances can include raw step IDs.
Use the shown raw step when cross-referencing engine event order.
