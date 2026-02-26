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
