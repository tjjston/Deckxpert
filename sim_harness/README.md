# sim_harness

`sim_harness` is the Python + PHP simulation layer on top of the SWU engine.

It uses the same core rules logic as Arena, but runs matches headlessly for:
- deterministic single-match inspection,
- batch simulation analysis,
- rules/mechanic validation from real match logs.

## What It Does

1. **Deck management**
- Upload SWUDB JSON decks.
- Remove decks from the local deck list.
- Store decks in local pools: `candidate`, `meta`, `starter`.

2. **Single match execution**
- Run one match with a selected policy and seed.
- Capture per-step events with legal/illegal result and board snapshots.
- Show timeline paged by round with optional decision prompts.

3. **Batch simulation**
- Run candidate deck vs selected opponent pool.
- Track aggregate win rates and matchup summaries.
- Persist a full illegal-move audit per simulation (every illegal step with context).

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

### Docker + Multi-GPU Runtime

To run the same dashboard in Docker with CUDA access (for RL training jobs):

```bash
# Uses base compose + GPU override image/service config
SIM_HARNESS_GPU_DEVICES=0,1 docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build sim-harness-web
```

Then open:
- `http://127.0.0.1:8765`

Notes:
- Requires NVIDIA Container Toolkit on the host.
- `SIM_HARNESS_GPU_DEVICES=0,1` pins jobs to your two GPUs (e.g., RTX A4500 + RTX 5000).
- GPU-enabled image definition: `docker/sim-harness-gpu.Dockerfile`.

#### Docker Setup Tips

- Verify host GPU container support:
```bash
docker run --rm --gpus all nvidia/cuda:12.3.2-runtime-ubuntu22.04 nvidia-smi
```
- Verify running `sim-harness-web` container sees GPUs:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec sim-harness-web nvidia-smi
```
- Verify PyTorch CUDA visibility inside container:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec sim-harness-web python -c "import torch; print('cuda:', torch.cuda.is_available(), 'count:', torch.cuda.device_count())"
```
- GPU selection examples:
  - use both cards: `SIM_HARNESS_GPU_DEVICES=0,1`
  - use one card: `SIM_HARNESS_GPU_DEVICES=0`
  - disable GPU for testing: set ML job device to `cpu` in the UI.

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
- `heuristic`: rule-based scorer (tempo + board pressure + non-pass bias).
- `mcts`: Monte Carlo Tree Search starter (root-level UCT + rollout simulation).

`mcts` tuning flags (PHP runner / CLI pass-through):
- `--mcts-iterations` (default `16`)
- `--mcts-max-depth` (default `14`)

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
- Simulation Illegal Move Audit tile (all illegal rows + top illegal action types).
- ML Lab tab:
  - launch async jobs for `sim create`, `sim shootout`, `rl collect`, `rl train`,
  - set per-job `CUDA_VISIBLE_DEVICES`,
  - monitor queue status + live logs,
  - stop running jobs from the dashboard.

## ML Changes (New)

- New API routes in `sim_harness.web`:
  - `GET /api/ml/info`
  - `GET /api/ml/jobs`
  - `GET /api/ml/jobs/<job_id>`
  - `POST /api/ml/jobs`
  - `POST /api/ml/jobs/<job_id>/stop`
- New background job manager:
  - queues and runs ML/sim commands asynchronously,
  - stores rolling logs and exit codes,
  - supports cancellation for queued/running jobs.
- New web controls in ML Lab:
  - start sim/collect/train jobs without blocking the UI,
  - review command + logs per job,
  - reuse discovered RL dataset/vocab artifacts from the runtime.

## Daily Backups (30 Days, Space-Efficient)

- Automatic backup is run by `sim_harness` commands and write paths.
- Snapshot retention is fixed to the last `30` daily snapshots.
- Snapshot location: `sim_harness/data/backups/YYYY-MM-DD/`
  - includes `decks.json`, `simulations.json`, and a `manifest.json`.
- RL/training data is stored as deduplicated compressed blobs:
  - blob location: `sim_harness/data/backups/rl_blobs/*.tar.gz`
  - snapshots reference blobs via `rl_blob` in each `manifest.json`
  - unchanged RL data does not create duplicate archives.
- Old snapshots and orphaned RL blobs are pruned automatically.

Restore examples:
```bash
# restore deck list from a snapshot day
cp sim_harness/data/backups/2026-03-03/decks.json sim_harness/data/decks.json

# inspect RL blob used by that day
cat sim_harness/data/backups/2026-03-03/manifest.json

# extract a referenced RL blob to /tmp/rl-restore
mkdir -p /tmp/rl-restore
tar -xzf sim_harness/data/backups/rl_blobs/<blob-name>.tar.gz -C /tmp/rl-restore
```

## Simulation CLI (Batch)

Examples:

```bash
python -m sim_harness.cli deck upload --file path/to/deck.json --pool candidate --deck-id my-candidate
python -m sim_harness.cli deck upload --file path/to/meta.json --pool meta
python -m sim_harness.cli deck upload --file path/to/starter.json --pool starter
python -m sim_harness.cli deck random --count 20 --pool candidate --main-size 50 --seed 123 --deck-id-prefix random

python -m sim_harness.cli deck list --pool all
python -m sim_harness.cli deck show my-candidate --format swudb

python -m sim_harness.cli sim create --candidate my-candidate --opponents all --games 25 --seed 123
python -m sim_harness.cli sim create --candidate my-candidate --opponents all --games 25 --seed 123 --policy heuristic
python -m sim_harness.cli sim create --candidate my-candidate --opponents all --games 10 --seed 123 --policy mcts --mcts-iterations 24 --mcts-max-depth 18
python -m sim_harness.cli sim shootout --candidate my-candidate --opponents all --games 30 --seed 123 --policies random_legal,heuristic,mcts --mcts-iterations 24 --mcts-max-depth 18
python -m sim_harness.cli sim results sim-20260101-120000
python -m sim_harness.cli sim analysis sim-20260101-120000
```

## RL Scaffold (Dataset + Training)

Use this to bootstrap policy/value learning from your simulated games:

```bash
# 1) Collect supervised dataset from strong policies (same matchup + seed policy)
python -m sim_harness.cli rl collect --candidate my-candidate --opponents all --games 25 --seed 123 --policies heuristic,mcts --mcts-iterations 24 --mcts-max-depth 18

# 2) Train a policy/value network
python -m sim_harness.cli rl train --dataset sim_harness/data/rl/my-candidate-YYYYMMDD-HHMMSS.jsonl --vocab sim_harness/data/rl/my-candidate-YYYYMMDD-HHMMSS.vocab.json --model-out sim_harness/data/rl/my-candidate-policy.pt --epochs 12 --batch-size 256
```

Outputs from `rl collect`:
- `<prefix>.jsonl`: per-decision rows (features, action key, value target, metadata).
- `<prefix>.vocab.json`: action vocabulary used for policy targets.
- `<prefix>.meta.json`: collection settings and summary counts.

Requirements for `rl train`:
- `numpy`
- `torch` (PyTorch)

## Iterative Training Loop

Use `rl loop` to run the full infrastructure cycle per iteration:
- candidate deck pool resolution,
- self-play simulation + raw match logs,
- `(state, action, outcome)` dataset build,
- policy/value training,
- candidate evaluation ranking.

```bash
python -m sim_harness.cli rl loop \
  --candidate my-candidate \
  --include-candidate-store-pool \
  --opponents all \
  --iterations 5 \
  --games 25 \
  --policies heuristic,mcts \
  --mcts-iterations 24 \
  --mcts-max-depth 18 \
  --epochs 12 \
  --batch-size 512 \
  --eval-policy mcts \
  --eval-games 30 \
  --advance-candidate-on-eval
```

Optional hooks:
- `--deck-generator-cmd "..."` runs at the start of each iteration.
- `--post-train-hook "..."` runs after training each iteration.

Hook environment variables:
- `DECKXPERT_LOOP_ITERATION`
- `DECKXPERT_LOOP_RUN_DIR`
- `DECKXPERT_LOOP_STAGE`
- `DECKXPERT_LOOP_MODEL_PATH` (post-train)
- `DECKXPERT_LOOP_DATASET_PATH` (post-train)
- `DECKXPERT_LOOP_VOCAB_PATH` (post-train)
- `DECKXPERT_LOOP_BEST_CANDIDATE` (post-train)

Loop outputs are stored in:
- `sim_harness/data/rl/loops/<run-id>/run.meta.json`
- `sim_harness/data/rl/loops/<run-id>/iteration_###/collect/*`
- `sim_harness/data/rl/loops/<run-id>/iteration_###/train/policy_value.pt`
- `sim_harness/data/rl/loops/<run-id>/iteration_###/eval/candidate_ranking.json`
- `sim_harness/data/rl/loops/<run-id>/run_summary.json`

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
