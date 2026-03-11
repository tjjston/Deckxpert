from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MatchResult:
    match_id: int
    seed: int
    winner: int
    turns: int
    outcome: dict[str, Any]
    log_path: str


def _derive_seed(global_seed: int, match_id: int) -> int:
    digest = hashlib.sha256(f"{global_seed}:{match_id}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _simulate_locally(seed: int, match_id: int, deck_a: str, deck_b: str) -> MatchResult:
    rng = random.Random(seed)
    turns = rng.randint(4, 14)
    winner = 1 if rng.random() > 0.5 else 2
    events = []
    for t in range(1, turns + 1):
        actor = 1 if t % 2 else 2
        events.append(
            {
                "timestamp": f"t{t}",
                "turn": t,
                "action": "simulate_turn",
                "result": "ok",
                "player": actor,
            }
        )

    logs_dir = Path("sim_harness") / "artifacts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"match_{match_id}.jsonl"
    with log_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")

    outcome = {
        "deck_a": deck_a,
        "deck_b": deck_b,
        "winner": winner,
        "turns": turns,
        "mode": "python_fallback",
    }
    return MatchResult(match_id, seed, winner, turns, outcome, str(log_path))


def resolve_php_bin() -> str | None:
    candidates: list[str] = []
    php_bin_env = (os.environ.get("PHP_BIN") or "").strip()
    if php_bin_env:
        candidates.append(php_bin_env)
    candidates.extend(["php", "php8.4", "php8.3", "php8.2", "php8.1", "php8.0", "php7.4"])
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def run_match(
    deck_a: str,
    deck_b: str,
    seed: int,
    match_id: int = 0,
    php_script: str | None = None,
    policy: str = "random_legal",
    mcts_iterations: int | None = None,
    mcts_max_depth: int | None = None,
) -> MatchResult:
    """Run one headless match.

    If php_script is provided and executable, this calls:
    php <php_script> --seed <seed> --deck-a-b64 <deck_a_b64> --deck-b-b64 <deck_b_b64> --match-id <id>
    and expects JSON on stdout. Otherwise it uses a deterministic local simulation fallback.
    """
    if php_script:
        php_bin = resolve_php_bin()
        if not php_bin:
            raise RuntimeError(
                "PHP executable not found. Install php-cli or set PHP_BIN to your php binary path."
            )
        if not Path(php_script).exists():
            raise RuntimeError(f"PHP match runner script not found: {php_script}")
        deck_a_b64 = base64.b64encode(deck_a.encode("utf-8")).decode("ascii")
        deck_b_b64 = base64.b64encode(deck_b.encode("utf-8")).decode("ascii")
        cmd = [
            php_bin,
            php_script,
            "--seed",
            str(seed),
            "--deck-a-b64",
            deck_a_b64,
            "--deck-b-b64",
            deck_b_b64,
            "--match-id",
            str(match_id),
            "--policy",
            str(policy or "random_legal"),
        ]
        if mcts_iterations is not None and int(mcts_iterations) > 0:
            cmd.extend(["--mcts-iterations", str(int(mcts_iterations))])
        if mcts_max_depth is not None and int(mcts_max_depth) > 0:
            cmd.extend(["--mcts-max-depth", str(int(mcts_max_depth))])
        env = dict(os.environ)
        env["XDEBUG_MODE"] = "off"
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            concise = _extract_runner_error(stdout, stderr)
            raise RuntimeError(
                "PHP match runner failed "
                f"(exit={proc.returncode}). {concise}"
            )
        payload = _decode_php_json(stdout, stderr)
        return MatchResult(
            match_id=payload.get("match_id", match_id),
            seed=payload["seed"],
            winner=payload["winner"],
            turns=payload["turns"],
            outcome=payload,
            log_path=payload.get("log_path", ""),
        )

    return _simulate_locally(seed, match_id, deck_a, deck_b)


def _decode_php_json(stdout: str, stderr: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise ValueError(
            "PHP match runner returned empty stdout. "
            f"stderr={stderr[:500] or '<empty>'}"
        )
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise ValueError(
        "PHP match runner did not return valid JSON. "
        f"stdout={text[:500]} stderr={stderr[:500] or '<empty>'}"
    )


def _extract_runner_error(stdout: str, stderr: str) -> str:
    for text in (stdout, stderr):
        if not text:
            continue
        try:
            payload = _decode_php_json(text, "")
            if isinstance(payload, dict):
                err = str(payload.get("error", "")).strip()
                msg = str(payload.get("message", "")).strip()
                if err and msg:
                    return f"{err}: {msg}"
                if msg:
                    return msg
                if err:
                    return err
        except Exception:
            pass
    return (
        f"stderr={stderr[:500] or '<empty>'} "
        f"stdout={stdout[:500] or '<empty>'}"
    )


def _run_match_job(job: tuple[int, str, str, int, str | None, str, int | None, int | None]) -> MatchResult:
    match_id, deck_a, deck_b, seed, php_script, policy, mcts_iterations, mcts_max_depth = job
    return run_match(
        deck_a,
        deck_b,
        seed,
        match_id=match_id,
        php_script=php_script,
        policy=policy,
        mcts_iterations=mcts_iterations,
        mcts_max_depth=mcts_max_depth,
    )


def _emit_progress_line(label: str, current: int, total: int) -> None:
    safe_label = str(label or "benchmark").strip().replace(" ", "_")
    if safe_label == "":
        safe_label = "benchmark"
    capped_total = max(int(total), 0)
    capped_current = max(int(current), 0)
    if capped_total > 0:
        capped_current = min(capped_current, capped_total)
        percent = (capped_current / capped_total) * 100.0
    else:
        percent = 0.0
    print(
        f"[progress] label={safe_label} current={capped_current} total={capped_total} percent={percent:.2f}",
        flush=True,
    )


def run_benchmark(
    deck_pairs: list[tuple[str, str]],
    n_games: int,
    seed_policy: dict[str, Any],
    workers: int = 4,
    output_jsonl: str | None = "sim_harness/artifacts/benchmark.jsonl",
    output_parquet: str | None = None,
    progress_label: str | None = None,
) -> list[MatchResult]:
    global_seed = int(seed_policy.get("global_seed", 0))
    php_script = seed_policy.get("php_script")
    policy = str(seed_policy.get("policy", "random_legal") or "random_legal")
    mcts_iterations = seed_policy.get("mcts_iterations")
    mcts_max_depth = seed_policy.get("mcts_max_depth")

    jobs: list[tuple[int, str, str, int, str | None, str, int | None, int | None]] = []
    match_id = 0
    for deck_a, deck_b in deck_pairs:
        for _ in range(n_games):
            jobs.append((
                match_id,
                deck_a,
                deck_b,
                _derive_seed(global_seed, match_id),
                php_script,
                policy,
                int(mcts_iterations) if mcts_iterations is not None else None,
                int(mcts_max_depth) if mcts_max_depth is not None else None,
            ))
            match_id += 1

    progress_name = str(progress_label or "").strip()
    emit_progress = progress_name != ""
    total_jobs = len(jobs)
    completed = 0
    results: list[MatchResult] = []

    if total_jobs > 0:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_match_job, job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
                completed += 1
                if emit_progress:
                    _emit_progress_line(progress_name, completed, total_jobs)

    results.sort(key=lambda row: int(row.match_id))

    if output_jsonl:
        out_path = Path(output_jsonl)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(result.outcome) + "\n")

    if output_parquet:
        try:
            import pandas as pd

            rows = [r.outcome for r in results]
            pd.DataFrame(rows).to_parquet(output_parquet, index=False)
        except Exception:
            pass

    return results


def optimize_deck(
    candidate_pool: list[str],
    population_size: int,
    generations: int,
    constraints: dict[str, Any] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Initial GA scaffold with deck constraints.

    Current fitness is placeholder random scoring and should be replaced with benchmark-driven fitness.
    """
    constraints = constraints or {}
    min_cards = int(constraints.get("min_cards", 50))
    max_copies = int(constraints.get("max_copies", 3))
    rng = random.Random(seed)

    def make_deck() -> list[str]:
        deck: list[str] = []
        while len(deck) < min_cards:
            card = rng.choice(candidate_pool)
            if deck.count(card) < max_copies:
                deck.append(card)
        return deck

    population = [make_deck() for _ in range(population_size)]
    best = population[0]
    best_score = -1.0

    for _ in range(generations):
        scored = []
        for deck in population:
            score = rng.random()
            scored.append((score, deck))
            if score > best_score:
                best_score = score
                best = list(deck)
        scored.sort(key=lambda x: x[0], reverse=True)
        survivors = [d for _, d in scored[: max(2, population_size // 4)]]

        next_population = survivors[:]
        while len(next_population) < population_size:
            mom = rng.choice(survivors)
            dad = rng.choice(survivors)
            cut = rng.randint(1, min_cards - 1)
            child = mom[:cut] + dad[cut:]
            if rng.random() < 0.2:
                idx = rng.randint(0, min_cards - 1)
                child[idx] = rng.choice(candidate_pool)
            next_population.append(child)
        population = next_population

    return {"best_deck": best, "fitness": best_score, "constraints": constraints}
