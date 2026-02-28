# sim_harness

Python harness for deterministic, parallel match execution.

## API

- `run_match(...)`
- `run_benchmark(deck_pairs, n_games, seed_policy)`
- `optimize_deck(...)`

## Reproducibility

`run_benchmark` uses `seed_policy["global_seed"]` and derives deterministic per-match seeds with SHA-256.

## Optional PHP runner

Set `seed_policy["php_script"] = "sim_harness/php_match_runner.php"` to route each match to a PHP subprocess.

## Outputs

- JSONL benchmark output at `sim_harness/artifacts/benchmark.jsonl`.
- Optional parquet output when pandas + parquet backend are installed.

## Simulation Manager CLI

Use the CLI to upload SWUDB decks, maintain `meta`/`starter` pools, and run candidate simulations.

```bash
python -m sim_harness.cli deck upload --file path/to/deck.json --pool candidate --deck-id my-candidate
python -m sim_harness.cli deck upload --file path/to/meta.json --pool meta
python -m sim_harness.cli deck upload --file path/to/starter.json --pool starter

python -m sim_harness.cli deck list --pool all
python -m sim_harness.cli deck show my-candidate --format swudb

python -m sim_harness.cli sim create --candidate my-candidate --opponents all --games 25 --seed 123
python -m sim_harness.cli sim results sim-20260101-120000
python -m sim_harness.cli sim decks sim-20260101-120000
python -m sim_harness.cli sim analysis sim-20260101-120000
```

## Web Frontend

For a visual dashboard covering decks, simulations, match analysis, and run settings:

```bash
python -m sim_harness.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` in your browser.

The UI supports:
- uploading SWUDB deck JSON into `candidate` / `meta` / `starter` pools,
- viewing deck list + full deck JSON,
- creating simulations with seed/workers/opponent-set settings,
- reviewing simulation history and analysis (overall, by-tier, best/worst matchup, per-opponent stats).
- running a single match and following turn-by-turn events (action legality, card/cost/type, and per-step effects).
- selecting single-match action policy: `random_legal` (default), `random_non_pass`, or `first_non_pass`.
- viewing single-match timelines paginated by round, with optional decision-prompt filtering.
- single-match runs default to full-game simulation (until game over, with an internal safety cap).
- SWUDB-style set IDs are converted to engine UUID card IDs before simulation; unknown set IDs are rejected with an explicit error.

### Storage

- Deck library: `sim_harness/data/decks.json`
- Simulation history: `sim_harness/data/simulations.json`

Deck `show --format swudb` prints the exact SWUDB JSON payload.


## Headless Rules Engine CLI (PHP)

Rules execution is now separated from UI/UI-HTTP bindings via `EngineCLI.php` + `Engine/HeadlessEngine.php`.

Example request:

```bash
printf '{"type":"init_game","deckA":{"material":["LAW_014","SEC_025"],"main":["JTL_203"]},"deckB":{"material":["LAW_114","SEC_125"],"main":["JTL_103"]},"seed":12345}' | php EngineCLI.php
```

Supported request types:
- `init_game`
- `get_observation`
- `get_legal_actions`
- `apply_action`

Core interfaces exposed by the headless engine:
- `getObservation($player_id)`
- `getLegalActions($player_id)`
- `applyAction($player_id, $action)`

`init_game` returns structured events including initialization, state snapshot, player observation, and legal actions.


### Rich match event output

`sim_harness/php_match_runner.php` now emits per-action events with:
- player, round, phase, chosen action, legality result
- card metadata (`id`, `cost`, `type`)
- phase snapshots at begin/end including resources, base health, hand/deck/discard, land arena, and space arena
- derived per-player effect deltas between phase begin/end (including base health and spent/available resources)
