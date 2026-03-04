from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..runner import MatchResult
from .action_space import ActionVocab, canonical_action_key
from .encoding import encode_event_state


def _winner_value_target(winner: int, player_id: int) -> float:
    if winner not in (1, 2):
        return 0.5
    return 1.0 if winner == player_id else 0.0


def build_training_rows_from_outcome(
    outcome: dict[str, Any],
    source_policy: str,
    hash_dim: int = 256,
) -> list[dict[str, Any]]:
    if not isinstance(outcome, dict):
        return []

    winner = int(outcome.get("winner", 0) or 0)
    match_id = int(outcome.get("match_id", 0) or 0)
    seed = int(outcome.get("seed", 0) or 0)
    events = outcome.get("events", [])
    if not isinstance(events, list):
        return []

    rows: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if not bool(event.get("apply_ok", True)):
            continue
        action = event.get("action")
        if not isinstance(action, dict):
            continue
        player_id = int(event.get("player", 0) or 0)
        if player_id not in (1, 2):
            continue
        try:
            features = encode_event_state(event, hash_dim=hash_dim)
        except Exception:
            continue

        action_key = canonical_action_key(action)
        row = {
            "match_id": match_id,
            "seed": seed,
            "step": int(event.get("step", 0) or 0),
            "round": int(event.get("round", 0) or 0),
            "phase": str(event.get("phase", "") or ""),
            "player": player_id,
            "winner": winner,
            "value_target": _winner_value_target(winner, player_id),
            "action_key": action_key,
            "action_type": str(action.get("type", "unknown") or "unknown"),
            "legal_action_count": int(event.get("legal_action_count", 0) or 0),
            "legal_actions_by_type": event.get("legal_actions_by_type", {}) if isinstance(event.get("legal_actions_by_type"), dict) else {},
            "source_policy": source_policy,
            "features": features.tolist(),
        }
        rows.append(row)
    return rows


def build_training_rows_from_results(
    results: list[MatchResult],
    source_policy: str,
    hash_dim: int = 256,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        outcome = result.outcome if isinstance(result.outcome, dict) else {}
        rows.extend(build_training_rows_from_outcome(outcome, source_policy=source_policy, hash_dim=hash_dim))
    return rows


def attach_action_indices(rows: list[dict[str, Any]], vocab: ActionVocab) -> None:
    for row in rows:
        key = str(row.get("action_key", ""))
        row["action_index"] = vocab.encode(key)


def write_jsonl_rows(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def load_dataset_rows(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset file not found: {p}")
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text == "":
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def vectorize_rows(
    rows: list[dict[str, Any]],
    vocab: ActionVocab,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_rows: list[np.ndarray] = []
    y_policy: list[int] = []
    y_value: list[float] = []

    feature_dim: int | None = None
    for row in rows:
        key = str(row.get("action_key", ""))
        if key not in vocab.key_to_idx:
            continue
        features_raw = row.get("features", [])
        if not isinstance(features_raw, list):
            continue
        features = np.asarray(features_raw, dtype=np.float32)
        if features.ndim != 1:
            continue
        if feature_dim is None:
            feature_dim = int(features.shape[0])
        if int(features.shape[0]) != feature_dim:
            continue
        x_rows.append(features)
        y_policy.append(vocab.encode(key))
        y_value.append(float(row.get("value_target", 0.5)))

    if not x_rows:
        raise ValueError("No valid rows after vectorization.")

    x = np.stack(x_rows).astype(np.float32)
    y_pi = np.asarray(y_policy, dtype=np.int64)
    y_v = np.asarray(y_value, dtype=np.float32)
    return x, y_pi, y_v
