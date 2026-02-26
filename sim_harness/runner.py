from __future__ import annotations

import hashlib
import json
import random
import subprocess
from concurrent.futures import ProcessPoolExecutor
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


def run_match(
    deck_a: str,
    deck_b: str,
    seed: int,
    match_id: int = 0,
    php_script: str | None = None,
) -> MatchResult:
    """Run one headless match.

    If php_script is provided and executable, this calls:
    php <php_script> --seed <seed> --deck-a <deck_a> --deck-b <deck_b> --match-id <id>
    and expects JSON on stdout. Otherwise it uses a deterministic local simulation fallback.
    """
    if php_script:
        cmd = [
            "php",
            php_script,
            "--seed",
            str(seed),
            "--deck-a",
            deck_a,
            "--deck-b",
            deck_b,
            "--match-id",
            str(match_id),
        ]
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        payload = json.loads(proc.stdout)
        return MatchResult(
            match_id=payload.get("match_id", match_id),
            seed=payload["seed"],
            winner=payload["winner"],
            turns=payload["turns"],
            outcome=payload,
            log_path=payload.get("log_path", ""),
        )

    return _simulate_locally(seed, match_id, deck_a, deck_b)


def _run_match_job(job: tuple[int, str, str, int, str | None]) -> MatchResult:
    match_id, deck_a, deck_b, seed, php_script = job
    return run_match(deck_a, deck_b, seed, match_id=match_id, php_script=php_script)


def run_benchmark(
    deck_pairs: list[tuple[str, str]],
    n_games: int,
    seed_policy: dict[str, Any],
    workers: int = 4,
    output_jsonl: str | None = "sim_harness/artifacts/benchmark.jsonl",
    output_parquet: str | None = None,
) -> list[MatchResult]:
    global_seed = int(seed_policy.get("global_seed", 0))
    php_script = seed_policy.get("php_script")

    jobs: list[tuple[int, str, str, int, str | None]] = []
    match_id = 0
    for deck_a, deck_b in deck_pairs:
        for _ in range(n_games):
            jobs.append((match_id, deck_a, deck_b, _derive_seed(global_seed, match_id), php_script))
            match_id += 1

    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_match_job, jobs))

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
