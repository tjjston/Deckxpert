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
        return 0.0
    return 1.0 if winner == player_id else -1.0


def _extract_legal_action_keys(event: dict[str, Any]) -> list[str]:
    out: list[str] = []
    legal_actions = event.get("legal_actions", [])
    if not isinstance(legal_actions, list):
        return out
    seen: set[str] = set()
    for legal_action in legal_actions:
        if not isinstance(legal_action, dict):
            continue
        try:
            key = canonical_action_key(legal_action)
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


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
            "legal_action_keys": _extract_legal_action_keys(event),
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x_rows: list[np.ndarray] = []
    y_policy: list[np.ndarray] = []
    y_value: list[float] = []
    legal_masks: list[np.ndarray] = []
    action_indices: list[int] = []

    feature_dim: int | None = None
    action_dim = len(vocab)
    if action_dim < 1:
        raise ValueError("Action vocabulary is empty.")

    for row in rows:
        key = str(row.get("action_key", ""))
        if key not in vocab.key_to_idx:
            continue
        action_idx = vocab.encode(key)
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

        legal_mask = np.ones(action_dim, dtype=np.float32)
        legal_keys_raw = row.get("legal_action_keys", [])
        legal_indices: list[int] = []
        if isinstance(legal_keys_raw, list):
            for legal_key_raw in legal_keys_raw:
                legal_key = str(legal_key_raw)
                if legal_key in vocab.key_to_idx:
                    legal_indices.append(vocab.encode(legal_key))
        if legal_indices:
            legal_mask.fill(0.0)
            legal_mask[np.asarray(legal_indices, dtype=np.int64)] = 1.0
            legal_mask[action_idx] = 1.0

        policy_target = np.zeros(action_dim, dtype=np.float32)
        policy_target[action_idx] = 1.0

        x_rows.append(features)
        y_policy.append(policy_target)
        y_value.append(float(row.get("value_target", 0.0)))
        legal_masks.append(legal_mask)
        action_indices.append(action_idx)

    if not x_rows:
        raise ValueError("No valid rows after vectorization.")

    x = np.stack(x_rows).astype(np.float32)
    y_pi = np.stack(y_policy).astype(np.float32)
    y_v = np.asarray(y_value, dtype=np.float32)
    y_mask = np.stack(legal_masks).astype(np.float32)
    y_action_idx = np.asarray(action_indices, dtype=np.int64)
    return x, y_pi, y_v, y_mask, y_action_idx
