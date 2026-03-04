from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

PHASE_VOCAB = (
    "M",
    "A",
    "B",
    "P",
    "ARS",
    "OPT",
    "YESNO",
    "CHOOSEMULTIZONE",
    "MAYCHOOSEMULTIZONE",
    "CHOOSECARD",
    "MAYCHOOSECARD",
    "CHOOSEOPTION",
    "MAYCHOOSEOPTION",
    "BUTTONINPUT",
    "BUTTONINPUTNOPASS",
)
PHASE_TO_IDX = {phase: i for i, phase in enumerate(PHASE_VOCAB)}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _hash_index(token: str, dim: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dim


def _accumulate_zone_tokens(
    hashed: np.ndarray,
    prefix: str,
    zone_name: str,
    raw_cards: list[Any],
) -> None:
    for raw in raw_cards:
        card_id = str(raw or "").strip()
        if card_id == "":
            continue
        token = f"{prefix}:{zone_name}:{card_id}"
        idx = _hash_index(token, hashed.shape[0])
        hashed[idx] += 1.0


def _player_numeric_features(player_snapshot: dict[str, Any]) -> list[float]:
    base = player_snapshot.get("base", {}) if isinstance(player_snapshot.get("base"), dict) else {}
    resources = player_snapshot.get("resources", {}) if isinstance(player_snapshot.get("resources"), dict) else {}
    counts = player_snapshot.get("counts", {}) if isinstance(player_snapshot.get("counts"), dict) else {}
    force = player_snapshot.get("force", {}) if isinstance(player_snapshot.get("force"), dict) else {}
    return [
        _safe_float(base.get("health", 0)),
        _safe_float(base.get("damage_taken", 0)),
        _safe_float(resources.get("available", 0)),
        _safe_float(resources.get("spent", 0)),
        _safe_float(resources.get("total_cards", 0)),
        _safe_float(resources.get("ready_cards", 0)),
        _safe_float(resources.get("exhausted_cards", 0)),
        _safe_float(counts.get("hand", 0)),
        _safe_float(counts.get("deck", 0)),
        _safe_float(counts.get("discard", 0)),
        _safe_float(counts.get("land_arena", 0)),
        _safe_float(counts.get("space_arena", 0)),
        _safe_float(counts.get("active_units", 0)),
        1.0 if bool(force.get("available", False)) else 0.0,
        _safe_float(force.get("times_used_this_phase", 0)),
    ]


def encode_state_snapshot(snapshot: dict[str, Any], player_id: int, hash_dim: int = 256) -> np.ndarray:
    if hash_dim < 16:
        raise ValueError("hash_dim must be >= 16")
    if player_id not in (1, 2):
        raise ValueError("player_id must be 1 or 2")

    self_key = f"player_{player_id}"
    opp_id = 2 if player_id == 1 else 1
    opp_key = f"player_{opp_id}"

    meta = snapshot.get("meta", {}) if isinstance(snapshot.get("meta"), dict) else {}
    phase = str(meta.get("turn_phase", "") or "")
    phase_one_hot = np.zeros(len(PHASE_VOCAB) + 1, dtype=np.float32)
    phase_idx = PHASE_TO_IDX.get(phase, len(PHASE_VOCAB))
    phase_one_hot[phase_idx] = 1.0

    turn_player = _safe_int(meta.get("turn_player", 0))
    meta_features = np.array(
        [
            1.0 if turn_player == player_id else 0.0,
            1.0 if turn_player == opp_id else 0.0,
            1.0 if str(meta.get("dq_phase", "") or "") != "" else 0.0,
            1.0 if str(meta.get("dq_context", "") or "") not in {"", "-", "<-"} else 0.0,
        ],
        dtype=np.float32,
    )

    self_snapshot = snapshot.get(self_key, {}) if isinstance(snapshot.get(self_key), dict) else {}
    opp_snapshot = snapshot.get(opp_key, {}) if isinstance(snapshot.get(opp_key), dict) else {}
    self_numeric = np.array(_player_numeric_features(self_snapshot), dtype=np.float32)
    opp_numeric = np.array(_player_numeric_features(opp_snapshot), dtype=np.float32)

    hashed = np.zeros(hash_dim, dtype=np.float32)
    self_zones = self_snapshot.get("zones", {}) if isinstance(self_snapshot.get("zones"), dict) else {}
    opp_zones = opp_snapshot.get("zones", {}) if isinstance(opp_snapshot.get("zones"), dict) else {}
    for zone_name in ("hand", "discard", "resources", "land_arena", "space_arena"):
        _accumulate_zone_tokens(hashed, "self", zone_name, list(self_zones.get(zone_name, []) or []))
        _accumulate_zone_tokens(hashed, "opp", zone_name, list(opp_zones.get(zone_name, []) or []))

    return np.concatenate([meta_features, phase_one_hot, self_numeric, opp_numeric, hashed]).astype(np.float32)


def encode_event_state(event: dict[str, Any], hash_dim: int = 256) -> np.ndarray:
    player_id = _safe_int(event.get("player", 0))
    snapshot = event.get("phase_state_begin", {})
    if not isinstance(snapshot, dict):
        raise ValueError("event.phase_state_begin missing or invalid")
    return encode_state_snapshot(snapshot, player_id, hash_dim=hash_dim)
