from __future__ import annotations

import argparse
import copy
import json
import os
import random
import re
import shlex
import statistics
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import backup as data_backup
from .runner import MatchResult, run_benchmark

DATA_DIR = Path("sim_harness") / "data"
DECKS_FILE = DATA_DIR / "decks.json"
SIMS_FILE = DATA_DIR / "simulations.json"
GENERATED_CARD_DICT_FILE = Path("GeneratedCode") / "GeneratedCardDictionaries.php"
SUPPORTED_MIN_DECK_SIZES = {30, 50}
DEFAULT_MIN_DECK_SIZE = 50
SUPPORTED_POLICIES = ("random_legal", "random_non_pass", "first_non_pass", "heuristic", "mcts")


@dataclass
class DeckRecord:
    deck_id: str
    pool: str
    swudb: dict[str, Any]
    added_at: str

    @property
    def name(self) -> str:
        return self.swudb.get("metadata", {}).get("name", self.deck_id)

    @property
    def author(self) -> str:
        return self.swudb.get("metadata", {}).get("author", "unknown")



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_daily_backup(*, refresh_today: bool = False) -> None:
    try:
        data_backup.ensure_daily_data_backup(
            data_dir=DATA_DIR,
            retention_days=30,
            refresh_today=refresh_today,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"warning: daily backup skipped: {exc}")



def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DECKS_FILE.exists():
        DECKS_FILE.write_text("[]\n", encoding="utf-8")
    if not SIMS_FILE.exists():
        SIMS_FILE.write_text("[]\n", encoding="utf-8")



def _read_json_list(path: Path) -> list[dict[str, Any]]:
    _ensure_data_files()
    payload = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list")
    return payload



def _write_json_list(path: Path, payload: list[dict[str, Any]]) -> None:
    _safe_daily_backup(refresh_today=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=1)
def _known_base_set_ids() -> set[str]:
    """Best-effort extraction of base set IDs from generated dictionaries."""
    if not GENERATED_CARD_DICT_FILE.exists():
        return set()

    text = GENERATED_CARD_DICT_FILE.read_text(encoding="utf-8", errors="ignore")

    uuid_start = text.find("function UUIDLookup(")
    uuid_end = text.find("function CardIDLookup(")
    type_start = text.find("function DefinedCardType(")
    type_end = text.find("function DefinedCardType2(")
    if min(uuid_start, uuid_end, type_start, type_end) < 0:
        return set()

    uuid_block = text[uuid_start:uuid_end]
    type_block = text[type_start:type_end]

    uuid_by_set = {
        m.group(1): m.group(2).lower()
        for m in re.finditer(r"'([A-Z0-9]+_[0-9]{3})'\s*=>\s*'([0-9a-fA-F]+)'", uuid_block)
    }
    base_uuids = {
        m.group(1).strip("'").lower()
        for m in re.finditer(r"([0-9]+|'[0-9a-fA-F]+')\s*=>\s*'Base'", type_block)
    }
    return {set_id for set_id, uuid_id in uuid_by_set.items() if uuid_id in base_uuids}


@lru_cache(maxsize=1)
def _known_set_id_to_card_type() -> dict[str, str]:
    """Best-effort mapping of set-id card codes (e.g. SOR_001) to card type."""
    if not GENERATED_CARD_DICT_FILE.exists():
        return {}

    text = GENERATED_CARD_DICT_FILE.read_text(encoding="utf-8", errors="ignore")

    uuid_start = text.find("function UUIDLookup(")
    uuid_end = text.find("function CardIDLookup(")
    type_start = text.find("function DefinedCardType(")
    type_end = text.find("function DefinedCardType2(")
    if min(uuid_start, uuid_end, type_start, type_end) < 0:
        return {}

    uuid_block = text[uuid_start:uuid_end]
    type_block = text[type_start:type_end]

    uuid_by_set = {
        m.group(1): m.group(2).lower()
        for m in re.finditer(r"'([A-Z0-9]+_[0-9]{3})'\s*=>\s*'([0-9a-fA-F]+)'", uuid_block)
    }
    type_by_uuid = {
        m.group(1).strip("'").lower(): m.group(2)
        for m in re.finditer(r"([0-9]+|'[0-9a-fA-F]+')\s*=>\s*'([^']+)'", type_block)
    }

    set_to_type: dict[str, str] = {}
    for set_id, uuid_id in uuid_by_set.items():
        card_type = type_by_uuid.get(uuid_id)
        if card_type:
            set_to_type[set_id] = card_type
    return set_to_type


def _random_hex(rng: random.Random, length: int = 8) -> str:
    alphabet = "0123456789abcdef"
    return "".join(rng.choice(alphabet) for _ in range(max(1, int(length))))


def _build_random_main_cards(
    card_ids: list[str],
    main_size: int,
    max_copies: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if main_size < 1:
        raise ValueError("main_size must be >= 1")
    if max_copies < 1:
        raise ValueError("max_copies must be >= 1")
    unique_card_ids = sorted(set(str(cid).strip() for cid in card_ids if str(cid).strip() != ""))
    if not unique_card_ids:
        raise ValueError("No non-leader/base card IDs are available for random deck generation.")
    if len(unique_card_ids) * max_copies < main_size:
        raise ValueError(
            f"Not enough card pool capacity for main_size={main_size} with max_copies={max_copies}."
        )

    remaining = int(main_size)
    available = list(unique_card_ids)
    counts: dict[str, int] = {}
    while remaining > 0:
        if not available:
            raise ValueError("Random deck generation exhausted available cards before filling main deck.")
        card_id = rng.choice(available)
        current = int(counts.get(card_id, 0))
        add_max = min(max_copies - current, remaining)
        add = rng.randint(1, add_max)
        counts[card_id] = current + add
        remaining -= add
        if counts[card_id] >= max_copies:
            available.remove(card_id)

    ordered_ids = list(counts.keys())
    rng.shuffle(ordered_ids)
    return [{"id": cid, "count": int(counts[cid])} for cid in ordered_ids]


def _create_random_decks(
    *,
    count: int,
    pool: str,
    main_size: int,
    seed: int | None,
    deck_id: str | None,
    deck_id_prefix: str,
    name_prefix: str,
    author: str,
    max_copies: int,
) -> list[DeckRecord]:
    if pool not in {"candidate", "meta", "starter"}:
        raise ValueError("pool must be candidate/meta/starter")
    main_size = _coerce_min_cards(main_size)
    count = int(count)
    if count < 1:
        raise ValueError("count must be >= 1")
    if count > 1000:
        raise ValueError("count must be <= 1000")
    if deck_id is not None and count != 1:
        raise ValueError("--deck-id can only be used with --count 1")
    if max_copies < 1:
        raise ValueError("max_copies must be >= 1")

    set_to_type = _known_set_id_to_card_type()
    leader_ids = sorted([set_id for set_id, typ in set_to_type.items() if typ == "Leader"])
    base_ids = sorted([set_id for set_id, typ in set_to_type.items() if typ == "Base"])
    main_card_ids = sorted(
        [set_id for set_id, typ in set_to_type.items() if typ in {"Unit", "Event", "Upgrade"}]
    )
    if not leader_ids:
        raise ValueError("No leader cards found in generated dictionaries.")
    if not base_ids:
        raise ValueError("No base cards found in generated dictionaries.")
    if not main_card_ids:
        raise ValueError("No Unit/Event/Upgrade cards found in generated dictionaries.")

    deck_id_prefix_clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(deck_id_prefix or "random")).strip("-")
    if deck_id_prefix_clean == "":
        deck_id_prefix_clean = "random"
    name_prefix_clean = str(name_prefix or "Random Deck").strip() or "Random Deck"
    author_clean = str(author or "sim_harness_random").strip() or "sim_harness_random"

    rng = random.Random(seed)
    decks = _load_decks()
    existing_ids = {d.deck_id for d in decks}
    created: list[DeckRecord] = []

    def next_random_deck_id() -> str:
        for _ in range(2000):
            candidate = f"{deck_id_prefix_clean}-{_random_hex(rng, 8)}"
            if candidate not in existing_ids:
                return candidate
        raise ValueError("Failed to allocate a unique random deck id after many attempts.")

    for i in range(count):
        random_deck_id = str(deck_id).strip() if deck_id is not None else next_random_deck_id()
        if random_deck_id == "":
            raise ValueError("deck_id cannot be blank")
        if random_deck_id in existing_ids:
            raise ValueError(f"Deck id already exists: {random_deck_id}")
        existing_ids.add(random_deck_id)

        leader_id = rng.choice(leader_ids)
        base_id = rng.choice(base_ids)
        main_cards = _build_random_main_cards(
            card_ids=main_card_ids,
            main_size=main_size,
            max_copies=max_copies,
            rng=rng,
        )
        display_name = (
            f"{name_prefix_clean} {main_size} #{i + 1}" if count > 1 else f"{name_prefix_clean} {main_size}"
        )
        swudb = {
            "metadata": {
                "name": display_name,
                "author": author_clean,
            },
            "leader": {"id": leader_id, "count": 1},
            "base": {"id": base_id, "count": 1},
            "deck": main_cards,
        }
        record = DeckRecord(
            deck_id=random_deck_id,
            pool=pool,
            swudb=swudb,
            added_at=_now_iso(),
        )
        decks.append(record)
        created.append(record)
        deck_id = None  # ensure single explicit id is used only once

    _save_decks(decks)
    return created


def _extract_set_id(card: dict[str, Any]) -> str:
    return str(card.get("id", "")).strip()


def _extract_count(card: dict[str, Any]) -> int:
    try:
        return int(card.get("count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _remove_one_copy(swudb: dict[str, Any], set_id: str) -> bool:
    for zone in ("deck", "sideboard"):
        cards = swudb.get(zone, [])
        if not isinstance(cards, list):
            continue
        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            if _extract_set_id(card) != set_id:
                continue
            count = _extract_count(card)
            if count <= 0:
                continue
            if count == 1:
                del cards[idx]
            else:
                card["count"] = count - 1
            return True
    return False


def _normalize_swudb_deck(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Normalizes accepted SWUDB payload variants before validation.

    If `base` is missing, we infer it only when exactly one known base card
    appears in deck/sideboard entries.
    """
    if not isinstance(payload, dict):
        raise ValueError("swudb must be a JSON object")

    swudb: dict[str, Any] = copy.deepcopy(payload)
    warnings: list[str] = []

    base = swudb.get("base")
    if isinstance(base, dict):
        base_id = str(base.get("id", "")).strip()
        if base_id:
            base["id"] = base_id
            try:
                base_count = int(base.get("count", 1) or 1)
            except (TypeError, ValueError):
                base_count = 1
            base["count"] = max(1, base_count)
            return swudb, warnings

    known_bases = _known_base_set_ids()
    candidates: list[str] = []
    for zone in ("deck", "sideboard"):
        cards = swudb.get(zone, [])
        if not isinstance(cards, list):
            continue
        for card in cards:
            if not isinstance(card, dict):
                continue
            set_id = _extract_set_id(card)
            if not set_id or _extract_count(card) < 1:
                continue
            if set_id in known_bases and set_id not in candidates:
                candidates.append(set_id)

    if len(candidates) == 1:
        inferred = candidates[0]
        swudb["base"] = {"id": inferred, "count": 1}
        if _remove_one_copy(swudb, inferred):
            warnings.append(
                f"Base was inferred as {inferred} from deck data and removed from card entries."
            )
        else:
            warnings.append(f"Base was inferred as {inferred} from deck data.")
        return swudb, warnings

    if len(candidates) > 1:
        joined = ", ".join(candidates)
        raise ValueError(
            "Missing SWUDB field: base. Multiple possible base cards were found "
            f"({joined}); add an explicit `base` object."
        )

    raise ValueError(
        "Missing SWUDB field: base. Add `\"base\": {\"id\": \"<SET_###>\", \"count\": 1}` "
        "to your deck JSON."
    )



def _validate_swudb_deck(payload: dict[str, Any]) -> None:
    required_top = ["metadata", "leader", "base", "deck"]
    for key in required_top:
        if key not in payload:
            raise ValueError(f"Missing SWUDB field: {key}")

    base = payload.get("base")
    if not isinstance(base, dict) or not str(base.get("id", "")).strip():
        raise ValueError("SWUDB field `base` must be an object like {\"id\":\"SET_###\",\"count\":1}")

    if not isinstance(payload["deck"], list) or len(payload["deck"]) == 0:
        raise ValueError("SWUDB deck list must be a non-empty array")



def _deck_main_count(swudb: dict[str, Any]) -> int:
    return sum(int(card.get("count", 0)) for card in swudb.get("deck", []))


def _coerce_min_cards(value: Any, default: int = DEFAULT_MIN_DECK_SIZE) -> int:
    if value is None:
        return int(default)
    min_cards = int(value)
    if min_cards not in SUPPORTED_MIN_DECK_SIZES:
        allowed = ", ".join(str(v) for v in sorted(SUPPORTED_MIN_DECK_SIZES))
        raise ValueError(f"min_cards must be one of: {allowed}")
    return min_cards


def _assert_min_deck_size(swudb: dict[str, Any], min_cards: int, deck_label: str) -> None:
    size = _deck_main_count(swudb)
    if size < min_cards:
        raise ValueError(f"{deck_label} has {size} cards; minimum required is {min_cards}")


def _cards_to_expanded_ids(swudb: dict[str, Any]) -> tuple[list[str], list[str]]:
    material = []
    leader = swudb.get("leader", {})
    base = swudb.get("base", {})

    # Engine expects base at character index 0 and leader at CharacterPieces() offset.
    if isinstance(base, dict) and base.get("id"):
        material.extend([str(base["id"])] * int(base.get("count", 1)))
    if isinstance(leader, dict) and leader.get("id"):
        material.extend([str(leader["id"])] * int(leader.get("count", 1)))

    main: list[str] = []
    for card in swudb.get("deck", []):
        cid = str(card.get("id", "")).strip()
        if not cid:
            continue
        count = int(card.get("count", 0))
        if count < 1:
            continue
        main.extend([cid] * count)

    return material, main



def _deck_to_runner_string(swudb: dict[str, Any]) -> str:
    material, main = _cards_to_expanded_ids(swudb)
    return " ".join(material) + "\n" + " ".join(main)



def _load_decks() -> list[DeckRecord]:
    return [
        DeckRecord(
            deck_id=d["deck_id"],
            pool=d["pool"],
            swudb=d["swudb"],
            added_at=d["added_at"],
        )
        for d in _read_json_list(DECKS_FILE)
    ]



def _save_decks(decks: list[DeckRecord]) -> None:
    serialized = [
        {
            "deck_id": d.deck_id,
            "pool": d.pool,
            "swudb": d.swudb,
            "added_at": d.added_at,
        }
        for d in decks
    ]
    _write_json_list(DECKS_FILE, serialized)



def _find_deck(decks: list[DeckRecord], deck_id: str) -> DeckRecord:
    for deck in decks:
        if deck.deck_id == deck_id:
            return deck
    raise ValueError(f"Deck not found: {deck_id}")


def _delete_deck(deck_id: str) -> DeckRecord:
    decks = _load_decks()
    target = _find_deck(decks, deck_id)
    remaining = [d for d in decks if d.deck_id != deck_id]
    _save_decks(remaining)
    return target


def _update_deck(deck_id: str, *, swudb: dict[str, Any] | None = None, pool: str | None = None) -> DeckRecord:
    decks = _load_decks()
    updated: DeckRecord | None = None
    for deck in decks:
        if deck.deck_id != deck_id:
            continue
        if swudb is not None:
            deck.swudb = swudb
        if pool is not None:
            deck.pool = pool
        updated = deck
        break
    if updated is None:
        raise ValueError(f"Deck not found: {deck_id}")
    _save_decks(decks)
    return updated


def _rename_deck(deck_id: str, *, name: str, author: str | None = None) -> DeckRecord:
    cleaned_name = str(name).strip()
    if not cleaned_name:
        raise ValueError("name is required")
    decks = _load_decks()
    updated: DeckRecord | None = None
    for deck in decks:
        if deck.deck_id != deck_id:
            continue
        metadata = deck.swudb.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            deck.swudb["metadata"] = metadata
        metadata["name"] = cleaned_name
        if author is not None:
            metadata["author"] = str(author).strip() or "unknown"
        updated = deck
        break
    if updated is None:
        raise ValueError(f"Deck not found: {deck_id}")
    _save_decks(decks)
    return updated



def cmd_deck_upload(args: argparse.Namespace) -> int:
    decks = _load_decks()
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    normalized, warnings = _normalize_swudb_deck(payload)
    _validate_swudb_deck(normalized)

    deck_id = args.deck_id or uuid.uuid4().hex[:12]
    if any(d.deck_id == deck_id for d in decks):
        raise ValueError(f"Deck id already exists: {deck_id}")

    record = DeckRecord(deck_id=deck_id, pool=args.pool, swudb=normalized, added_at=_now_iso())
    decks.append(record)
    _save_decks(decks)

    print(f"Uploaded deck {record.deck_id} :: {record.name} [{record.pool}] by {record.author}")
    for warning in warnings:
        print(f"warning: {warning}")
    return 0



def cmd_deck_random(args: argparse.Namespace) -> int:
    created = _create_random_decks(
        count=int(args.count),
        pool=str(args.pool),
        main_size=int(args.main_size),
        seed=None if getattr(args, "seed", None) is None else int(args.seed),
        deck_id=str(args.deck_id).strip() if getattr(args, "deck_id", None) else None,
        deck_id_prefix=str(args.deck_id_prefix),
        name_prefix=str(args.name_prefix),
        author=str(args.author),
        max_copies=int(args.max_copies),
    )
    print(f"Created {len(created)} random deck(s) in pool '{args.pool}'")
    for deck in created:
        print(
            f"{deck.deck_id}\t{deck.pool}\t{deck.name}\t"
            f"leader={deck.swudb.get('leader', {}).get('id', '')}\t"
            f"base={deck.swudb.get('base', {}).get('id', '')}\t"
            f"main={_deck_main_count(deck.swudb)}"
        )
    return 0


def cmd_deck_list(args: argparse.Namespace) -> int:
    decks = _load_decks()
    if args.pool != "all":
        decks = [d for d in decks if d.pool == args.pool]

    if not decks:
        print("No decks found.")
        return 0

    for deck in decks:
        deck_size = sum(int(c.get("count", 0)) for c in deck.swudb.get("deck", []))
        print(f"{deck.deck_id}\t{deck.pool}\t{deck.name}\t{deck.author}\t{deck_size} cards")
    return 0



def cmd_deck_show(args: argparse.Namespace) -> int:
    deck = _find_deck(_load_decks(), args.deck_id)
    if args.format == "swudb":
        print(json.dumps(deck.swudb, indent=2))
        return 0

    material, main = _cards_to_expanded_ids(deck.swudb)
    print(f"deck_id: {deck.deck_id}")
    print(f"name: {deck.name}")
    print(f"pool: {deck.pool}")
    print(f"leader/base: {' '.join(material)}")
    print(f"main_count: {len(main)}")
    return 0


def cmd_deck_delete(args: argparse.Namespace) -> int:
    removed = _delete_deck(args.deck_id)
    print(f"Deleted deck {removed.deck_id} :: {removed.name}")
    return 0



def _load_sims() -> list[dict[str, Any]]:
    return _read_json_list(SIMS_FILE)



def _save_sims(sims: list[dict[str, Any]]) -> None:
    _write_json_list(SIMS_FILE, sims)


def _extract_illegal_event_rows(
    results: list[MatchResult],
    opponents: list[DeckRecord],
    games_per_opponent: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_action: dict[str, int] = {}
    by_phase: dict[str, int] = {}
    by_player: dict[str, int] = {}
    by_opponent: dict[str, dict[str, Any]] = {}
    match_illegal_seen: set[int] = set()

    for opp in opponents:
        by_opponent[opp.deck_id] = {
            "deck_id": opp.deck_id,
            "deck_name": opp.name,
            "pool": opp.pool,
            "games": 0,
            "illegal_actions": 0,
            "matches_with_illegal": 0,
        }

    for result in results:
        opponent_idx = result.match_id // games_per_opponent if games_per_opponent > 0 else 0
        if opponent_idx < 0 or opponent_idx >= len(opponents):
            continue
        opp = opponents[opponent_idx]
        by_opponent[opp.deck_id]["games"] += 1
        had_illegal = False

        outcome = result.outcome if isinstance(result.outcome, dict) else {}
        events = outcome.get("events", [])
        if not isinstance(events, list):
            events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if bool(event.get("apply_ok", True)):
                continue

            had_illegal = True
            match_illegal_seen.add(int(result.match_id))

            action = event.get("action", {}) if isinstance(event.get("action"), dict) else {}
            phase_begin = event.get("phase_state_begin", {}) if isinstance(event.get("phase_state_begin"), dict) else {}
            p1 = phase_begin.get("player_1", {}) if isinstance(phase_begin.get("player_1"), dict) else {}
            p2 = phase_begin.get("player_2", {}) if isinstance(phase_begin.get("player_2"), dict) else {}
            p1_res = p1.get("resources", {}) if isinstance(p1.get("resources"), dict) else {}
            p2_res = p2.get("resources", {}) if isinstance(p2.get("resources"), dict) else {}
            meta = phase_begin.get("meta", {}) if isinstance(phase_begin.get("meta"), dict) else {}
            card = event.get("card", {}) if isinstance(event.get("card"), dict) else {}
            action_type = str(action.get("type", "unknown"))
            phase = str(event.get("phase", ""))
            player = int(event.get("player", 0))
            choice = action.get("buttonInput", "")
            if choice in ("", None):
                choice = action.get("cardID", "")
            mode_raw = str(action.get("mode", "")).strip()
            action_mode = int(mode_raw) if mode_raw not in ("", "None") else 0

            row = {
                "match_id": int(result.match_id),
                "seed": int(result.seed),
                "opponent_index": int(opponent_idx),
                "opponent_deck_id": opp.deck_id,
                "opponent_name": opp.name,
                "opponent_pool": opp.pool,
                "step": int(event.get("step", 0)),
                "round": int(event.get("round", 0)),
                "phase": phase,
                "player": player,
                "action_type": action_type,
                "action_mode": action_mode,
                "action_choice": str(choice),
                "card_id": str(card.get("id", "")),
                "card_raw_id": str(card.get("raw_id", "")),
                "message": str(event.get("message", "")),
                "legal_action_count": int(event.get("legal_action_count", 0)),
                "legal_actions_by_type": event.get("legal_actions_by_type", {}) if isinstance(event.get("legal_actions_by_type"), dict) else {},
                "turn_player": int(meta.get("turn_player", 0)),
                "turn_phase": str(meta.get("turn_phase", "")),
                "next_player": int(event.get("next_player", 0)),
                "next_phase": str(event.get("next_phase", "")),
                "p1_hp": int((p1.get("base", {}) or {}).get("health", 0)) if isinstance(p1.get("base", {}), dict) else 0,
                "p2_hp": int((p2.get("base", {}) or {}).get("health", 0)) if isinstance(p2.get("base", {}), dict) else 0,
                "p1_ready_resources": int(p1_res.get("ready_cards", 0)),
                "p2_ready_resources": int(p2_res.get("ready_cards", 0)),
            }
            rows.append(row)

            by_action[action_type] = by_action.get(action_type, 0) + 1
            by_phase[phase] = by_phase.get(phase, 0) + 1
            by_player[str(player)] = by_player.get(str(player), 0) + 1
            by_opponent[opp.deck_id]["illegal_actions"] += 1

        if had_illegal:
            by_opponent[opp.deck_id]["matches_with_illegal"] += 1

    rows.sort(key=lambda r: (int(r.get("match_id", 0)), int(r.get("step", 0))))
    by_action_sorted = dict(sorted(by_action.items(), key=lambda kv: (-kv[1], kv[0])))
    by_phase_sorted = dict(sorted(by_phase.items(), key=lambda kv: (-kv[1], kv[0])))
    by_player_sorted = dict(sorted(by_player.items(), key=lambda kv: (-kv[1], kv[0])))
    by_opponent_rows = sorted(by_opponent.values(), key=lambda r: (-int(r.get("illegal_actions", 0)), str(r.get("deck_id", ""))))

    return {
        "total_illegal_actions": len(rows),
        "matches_with_illegal": len(match_illegal_seen),
        "by_action_type": by_action_sorted,
        "by_phase": by_phase_sorted,
        "by_player": by_player_sorted,
        "by_opponent": by_opponent_rows,
        "rows": rows,
    }



def cmd_sim_create(args: argparse.Namespace) -> int:
    decks = _load_decks()
    candidate = _find_deck(decks, args.candidate)
    min_cards = _coerce_min_cards(getattr(args, "min_cards", DEFAULT_MIN_DECK_SIZE))
    _assert_min_deck_size(candidate.swudb, min_cards, f"Candidate deck '{candidate.deck_id}'")

    if args.opponents == "all":
        opponents = [d for d in decks if d.deck_id != candidate.deck_id and d.pool in {"meta", "starter"}]
    else:
        opponents = [d for d in decks if d.deck_id != candidate.deck_id and d.pool == args.opponents]

    if not opponents:
        raise ValueError("No opponent decks found for selected set. Upload decks to meta/starter pools first.")
    invalid_opponents = [d for d in opponents if _deck_main_count(d.swudb) < min_cards]
    if invalid_opponents:
        sample = ", ".join(f"{d.deck_id}({_deck_main_count(d.swudb)})" for d in invalid_opponents[:8])
        more = f" (+{len(invalid_opponents)-8} more)" if len(invalid_opponents) > 8 else ""
        raise ValueError(
            f"Opponent decks below minimum {min_cards} cards: {sample}{more}. "
            "Use a lower minimum or upload larger decks."
        )

    deck_pairs = [(_deck_to_runner_string(candidate.swudb), _deck_to_runner_string(o.swudb)) for o in opponents]
    results = run_benchmark(
        deck_pairs=deck_pairs,
        n_games=args.games,
        seed_policy={
            "global_seed": args.seed,
            "php_script": args.php_script,
            "policy": args.policy,
            "mcts_iterations": args.mcts_iterations,
            "mcts_max_depth": args.mcts_max_depth,
        },
        workers=args.workers,
    )

    grouped: dict[int, list[MatchResult]] = {}
    for result in results:
        bucket = result.match_id // args.games
        grouped.setdefault(bucket, []).append(result)

    opponent_results = []
    for idx, opp in enumerate(opponents):
        rows = grouped.get(idx, [])
        wins = sum(1 for r in rows if r.winner == 1)
        games = len(rows)
        win_rate = (wins / games) if games else 0.0
        turns = [r.turns for r in rows]
        illegal_actions = 0
        matches_with_illegal = 0
        for r in rows:
            outcome = r.outcome if isinstance(r.outcome, dict) else {}
            stats = outcome.get("stats", {}) if isinstance(outcome.get("stats"), dict) else {}
            illegal_count = int(stats.get("illegal_actions", 0))
            illegal_actions += illegal_count
            if illegal_count > 0:
                matches_with_illegal += 1
        opponent_results.append(
            {
                "deck_id": opp.deck_id,
                "deck_name": opp.name,
                "pool": opp.pool,
                "games": games,
                "wins": wins,
                "win_rate": round(win_rate, 4),
                "avg_turns": round(statistics.fmean(turns), 2) if turns else 0.0,
                "illegal_actions": illegal_actions,
                "matches_with_illegal": matches_with_illegal,
            }
        )

    all_games = sum(r["games"] for r in opponent_results)
    all_wins = sum(r["wins"] for r in opponent_results)
    illegal_audit = _extract_illegal_event_rows(results, opponents, args.games)

    sim_id = args.sim_id or datetime.now(timezone.utc).strftime("sim-%Y%m%d-%H%M%S")
    sim_payload = {
        "sim_id": sim_id,
        "created_at": _now_iso(),
        "candidate_deck_id": candidate.deck_id,
        "candidate_name": candidate.name,
        "opponent_set": args.opponents,
        "games_per_opponent": args.games,
        "seed": args.seed,
        "workers": args.workers,
        "policy": args.policy,
        "mcts_iterations": int(args.mcts_iterations or 0),
        "mcts_max_depth": int(args.mcts_max_depth or 0),
        "min_cards": min_cards,
        "overall": {
            "games": all_games,
            "wins": all_wins,
            "losses": all_games - all_wins,
            "win_rate": round((all_wins / all_games), 4) if all_games else 0.0,
            "illegal_actions": int(illegal_audit.get("total_illegal_actions", 0)),
            "matches_with_illegal": int(illegal_audit.get("matches_with_illegal", 0)),
        },
        "opponents": opponent_results,
        "illegal_move_audit": illegal_audit,
    }

    sims = _load_sims()
    sims.append(sim_payload)
    _save_sims(sims)

    print(f"Created simulation {sim_id}")
    print(json.dumps(sim_payload["overall"], indent=2))
    return 0



def _find_sim(sim_id: str) -> dict[str, Any]:
    for sim in _load_sims():
        if sim.get("sim_id") == sim_id:
            return sim
    raise ValueError(f"Simulation not found: {sim_id}")



def cmd_sim_results(args: argparse.Namespace) -> int:
    sim = _find_sim(args.sim_id)
    print(json.dumps(sim["overall"], indent=2))
    return 0



def cmd_sim_decks(args: argparse.Namespace) -> int:
    sim = _find_sim(args.sim_id)
    print(f"candidate\t{sim['candidate_deck_id']}\t{sim['candidate_name']}")
    for opp in sim.get("opponents", []):
        print(f"opponent\t{opp['deck_id']}\t{opp['deck_name']}\t{opp['pool']}")
    return 0



def cmd_sim_analysis(args: argparse.Namespace) -> int:
    sim = _find_sim(args.sim_id)
    rows = sim.get("opponents", [])
    if not rows:
        print("No opponent rows found.")
        return 0

    print(f"Simulation: {sim['sim_id']}")
    print(f"Candidate: {sim['candidate_deck_id']} :: {sim['candidate_name']}")
    print(f"Policy: {sim.get('policy', 'random_legal')}")
    print(f"Overall win rate: {sim['overall']['win_rate']:.2%} ({sim['overall']['wins']}/{sim['overall']['games']})")
    illegal_actions = int(sim.get("overall", {}).get("illegal_actions", 0))
    matches_with_illegal = int(sim.get("overall", {}).get("matches_with_illegal", 0))
    print(f"Illegal actions: {illegal_actions} across {matches_with_illegal} matches")

    tier_summary: dict[str, dict[str, float]] = {}
    for r in rows:
        tier = r["pool"]
        tier_summary.setdefault(tier, {"wins": 0.0, "games": 0.0})
        tier_summary[tier]["wins"] += float(r["wins"])
        tier_summary[tier]["games"] += float(r["games"])

    print("\nBy tier:")
    for tier, s in sorted(tier_summary.items()):
        wr = (s["wins"] / s["games"]) if s["games"] else 0.0
        print(f"- {tier}: {wr:.2%} ({int(s['wins'])}/{int(s['games'])})")

    best = max(rows, key=lambda r: r["win_rate"])
    worst = min(rows, key=lambda r: r["win_rate"])
    print("\nMatchup extremes:")
    print(f"- Best:  {best['deck_id']} ({best['deck_name']}) => {best['win_rate']:.2%} over {best['games']} games")
    print(f"- Worst: {worst['deck_id']} ({worst['deck_name']}) => {worst['win_rate']:.2%} over {worst['games']} games")

    print("\nPer-opponent:")
    for r in sorted(rows, key=lambda x: x["win_rate"], reverse=True):
        print(
            f"- {r['deck_id']} [{r['pool']}] {r['deck_name']}: "
            f"{r['wins']}/{r['games']} ({r['win_rate']:.2%}), avg_turns={r['avg_turns']}"
        )
    return 0


def _parse_policy_list(raw: str) -> list[str]:
    parts = [p.strip() for p in str(raw).split(",")]
    policies: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p == "":
            continue
        if p not in SUPPORTED_POLICIES:
            allowed = ", ".join(SUPPORTED_POLICIES)
            raise ValueError(f"Unsupported policy '{p}'. Allowed: {allowed}")
        if p in seen:
            continue
        seen.add(p)
        policies.append(p)
    if not policies:
        raise ValueError("No valid policies selected for shootout.")
    return policies


def _parse_csv_values(raw: str | None) -> list[str]:
    parts = [p.strip() for p in str(raw or "").split(",")]
    values: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part == "" or part in seen:
            continue
        seen.add(part)
        values.append(part)
    return values


def _resolve_loop_candidate_ids(
    primary_candidate: str,
    candidate_pool_csv: str,
    include_store_pool: bool,
) -> list[str]:
    candidate_ids: list[str] = []
    seen: set[str] = set()

    def add_candidate(deck_id: str) -> None:
        deck_id = str(deck_id).strip()
        if deck_id == "" or deck_id in seen:
            return
        seen.add(deck_id)
        candidate_ids.append(deck_id)

    add_candidate(primary_candidate)
    for deck_id in _parse_csv_values(candidate_pool_csv):
        add_candidate(deck_id)

    if include_store_pool:
        for deck in _load_decks():
            if deck.pool == "candidate":
                add_candidate(deck.deck_id)

    if not candidate_ids:
        raise ValueError("No candidate decks resolved for loop run.")
    return candidate_ids


def _run_loop_hook(
    command_template: str | None,
    *,
    iteration: int,
    run_dir: Path,
    stage: str,
    fail_on_error: bool,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    template = str(command_template or "").strip()
    if template == "":
        return {"stage": stage, "skipped": True}

    rendered = template.format(iteration=iteration, run_dir=str(run_dir), stage=stage)
    argv = shlex.split(rendered)
    if not argv:
        return {"stage": stage, "skipped": True}

    env = dict(os.environ)
    env.update(
        {
            "DECKXPERT_LOOP_ITERATION": str(iteration),
            "DECKXPERT_LOOP_RUN_DIR": str(run_dir),
            "DECKXPERT_LOOP_STAGE": stage,
        }
    )
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})

    proc = subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
    payload = {
        "stage": stage,
        "command": argv,
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "skipped": False,
    }
    if proc.returncode != 0 and fail_on_error:
        raise ValueError(
            f"Loop hook failed at stage={stage} exit={proc.returncode}. "
            f"stderr={(proc.stderr or '').strip()[:500]}"
        )
    return payload


def _collect_rl_rows_for_candidate(
    *,
    candidate: DeckRecord,
    opponents: list[DeckRecord],
    policies: list[str],
    games: int,
    seed: int,
    workers: int,
    php_script: str | None,
    mcts_iterations: int,
    mcts_max_depth: int,
    hash_dim: int,
    match_logs_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    from .rl.dataset import build_training_rows_from_results

    deck_pairs = [(_deck_to_runner_string(candidate.swudb), _deck_to_runner_string(o.swudb)) for o in opponents]
    all_rows: list[dict[str, Any]] = []
    rows_by_policy: dict[str, int] = {}
    policy_reports: list[dict[str, Any]] = []

    for policy in policies:
        output_jsonl = None
        if match_logs_dir is not None:
            match_logs_dir.mkdir(parents=True, exist_ok=True)
            output_jsonl = str(match_logs_dir / f"{candidate.deck_id}.{policy}.matches.jsonl")

        results = run_benchmark(
            deck_pairs=deck_pairs,
            n_games=games,
            seed_policy={
                "global_seed": seed,
                "php_script": php_script,
                "policy": policy,
                "mcts_iterations": mcts_iterations if policy == "mcts" else 0,
                "mcts_max_depth": mcts_max_depth if policy == "mcts" else 0,
            },
            workers=workers,
            output_jsonl=output_jsonl,
            output_parquet=None,
        )

        rows = build_training_rows_from_results(results, source_policy=policy, hash_dim=hash_dim)
        for row in rows:
            row["candidate_deck_id"] = candidate.deck_id
            row["candidate_name"] = candidate.name
        all_rows.extend(rows)
        rows_by_policy[policy] = len(rows)

        total_games = len(results)
        wins = sum(1 for r in results if int(r.winner) == 1)
        turns = [r.turns for r in results]
        illegal_audit = _extract_illegal_event_rows(results, opponents, games)
        policy_reports.append(
            {
                "policy": policy,
                "games": total_games,
                "wins": wins,
                "losses": total_games - wins,
                "win_rate": round((wins / total_games), 4) if total_games else 0.0,
                "avg_turns": round(statistics.fmean(turns), 2) if turns else 0.0,
                "illegal_actions": int(illegal_audit.get("total_illegal_actions", 0)),
                "matches_with_illegal": int(illegal_audit.get("matches_with_illegal", 0)),
                "rows_collected": len(rows),
                "match_log_path": output_jsonl,
            }
        )
    return all_rows, rows_by_policy, policy_reports


def _write_rl_dataset_bundle(
    *,
    rows: list[dict[str, Any]],
    output_prefix: Path,
    meta: dict[str, Any],
) -> dict[str, Any]:
    from .rl.action_space import ActionVocab
    from .rl.dataset import attach_action_indices, write_jsonl_rows

    if len(rows) == 0:
        raise ValueError("No training rows collected. Verify policies/decks and runner output.")

    vocab = ActionVocab()
    for row in rows:
        vocab.add(str(row.get("action_key", "")))
    attach_action_indices(rows, vocab)

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    dataset_path = output_prefix.with_suffix(".jsonl")
    vocab_path = output_prefix.with_suffix(".vocab.json")
    meta_path = output_prefix.with_suffix(".meta.json")

    write_jsonl_rows(dataset_path, rows)
    vocab.save_json(vocab_path)

    payload = dict(meta)
    payload.update(
        {
            "total_rows": int(len(rows)),
            "action_vocab_size": int(len(vocab)),
            "dataset_path": str(dataset_path),
            "vocab_path": str(vocab_path),
        }
    )
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _safe_daily_backup(refresh_today=True)
    return {
        "dataset_path": str(dataset_path),
        "vocab_path": str(vocab_path),
        "meta_path": str(meta_path),
        "total_rows": int(len(rows)),
        "action_vocab_size": int(len(vocab)),
        "meta": payload,
    }


def _evaluate_candidate(
    *,
    candidate: DeckRecord,
    opponents: list[DeckRecord],
    games: int,
    seed: int,
    workers: int,
    php_script: str | None,
    policy: str,
    mcts_iterations: int,
    mcts_max_depth: int,
) -> dict[str, Any]:
    deck_pairs = [(_deck_to_runner_string(candidate.swudb), _deck_to_runner_string(o.swudb)) for o in opponents]
    results = run_benchmark(
        deck_pairs=deck_pairs,
        n_games=games,
        seed_policy={
            "global_seed": seed,
            "php_script": php_script,
            "policy": policy,
            "mcts_iterations": mcts_iterations if policy == "mcts" else 0,
            "mcts_max_depth": mcts_max_depth if policy == "mcts" else 0,
        },
        workers=workers,
        output_jsonl=None,
        output_parquet=None,
    )
    total_games = len(results)
    wins = sum(1 for r in results if int(r.winner) == 1)
    turns = [r.turns for r in results]
    illegal_audit = _extract_illegal_event_rows(results, opponents, games)
    return {
        "candidate_deck_id": candidate.deck_id,
        "candidate_name": candidate.name,
        "games": total_games,
        "wins": wins,
        "losses": total_games - wins,
        "win_rate": round((wins / total_games), 4) if total_games else 0.0,
        "avg_turns": round(statistics.fmean(turns), 2) if turns else 0.0,
        "illegal_actions": int(illegal_audit.get("total_illegal_actions", 0)),
        "matches_with_illegal": int(illegal_audit.get("matches_with_illegal", 0)),
    }


def _resolve_candidate_and_opponents(
    candidate_id: str,
    opponent_set: str,
    min_cards: int,
) -> tuple[DeckRecord, list[DeckRecord]]:
    decks = _load_decks()
    candidate = _find_deck(decks, candidate_id)
    _assert_min_deck_size(candidate.swudb, min_cards, f"Candidate deck '{candidate.deck_id}'")

    if opponent_set == "all":
        opponents = [d for d in decks if d.deck_id != candidate.deck_id and d.pool in {"meta", "starter"}]
    else:
        opponents = [d for d in decks if d.deck_id != candidate.deck_id and d.pool == opponent_set]

    if not opponents:
        raise ValueError("No opponent decks found for selected set. Upload decks to meta/starter pools first.")
    invalid_opponents = [d for d in opponents if _deck_main_count(d.swudb) < min_cards]
    if invalid_opponents:
        sample = ", ".join(f"{d.deck_id}({_deck_main_count(d.swudb)})" for d in invalid_opponents[:8])
        more = f" (+{len(invalid_opponents)-8} more)" if len(invalid_opponents) > 8 else ""
        raise ValueError(
            f"Opponent decks below minimum {min_cards} cards: {sample}{more}. "
            "Use a lower minimum or upload larger decks."
        )

    return candidate, opponents


def cmd_sim_shootout(args: argparse.Namespace) -> int:
    min_cards = _coerce_min_cards(getattr(args, "min_cards", DEFAULT_MIN_DECK_SIZE))
    candidate, opponents = _resolve_candidate_and_opponents(args.candidate, args.opponents, min_cards)
    policies = _parse_policy_list(args.policies)

    deck_pairs = [(_deck_to_runner_string(candidate.swudb), _deck_to_runner_string(o.swudb)) for o in opponents]
    per_policy: list[dict[str, Any]] = []

    for policy in policies:
        results = run_benchmark(
            deck_pairs=deck_pairs,
            n_games=args.games,
            seed_policy={
                "global_seed": args.seed,
                "php_script": args.php_script,
                "policy": policy,
                "mcts_iterations": args.mcts_iterations if policy == "mcts" else 0,
                "mcts_max_depth": args.mcts_max_depth if policy == "mcts" else 0,
            },
            workers=args.workers,
        )
        illegal_audit = _extract_illegal_event_rows(results, opponents, args.games)
        turns = [r.turns for r in results]
        total_games = len(results)
        total_wins = sum(1 for r in results if int(r.winner) == 1)
        avg_turns = round(statistics.fmean(turns), 2) if turns else 0.0

        grouped: dict[int, list[MatchResult]] = {}
        for result in results:
            bucket = result.match_id // args.games if args.games > 0 else 0
            grouped.setdefault(bucket, []).append(result)
        by_opponent: list[dict[str, Any]] = []
        for idx, opp in enumerate(opponents):
            rows = grouped.get(idx, [])
            wins = sum(1 for r in rows if int(r.winner) == 1)
            games = len(rows)
            win_rate = (wins / games) if games else 0.0
            by_opponent.append({
                "deck_id": opp.deck_id,
                "deck_name": opp.name,
                "pool": opp.pool,
                "games": games,
                "wins": wins,
                "win_rate": round(win_rate, 4),
            })

        per_policy.append({
            "policy": policy,
            "games": total_games,
            "wins": total_wins,
            "losses": total_games - total_wins,
            "win_rate": round((total_wins / total_games), 4) if total_games else 0.0,
            "avg_turns": avg_turns,
            "illegal_actions": int(illegal_audit.get("total_illegal_actions", 0)),
            "matches_with_illegal": int(illegal_audit.get("matches_with_illegal", 0)),
            "mcts_iterations": int(args.mcts_iterations if policy == "mcts" else 0),
            "mcts_max_depth": int(args.mcts_max_depth if policy == "mcts" else 0),
            "by_opponent": by_opponent,
            "illegal_move_audit": illegal_audit,
        })

    ranked = sorted(
        per_policy,
        key=lambda row: (-float(row["win_rate"]), int(row["illegal_actions"]), float(row["avg_turns"]), str(row["policy"])),
    )

    print("Policy shootout")
    print(f"Candidate: {candidate.deck_id} :: {candidate.name}")
    print(f"Opponents: {args.opponents} ({len(opponents)} decks)")
    print(f"Games/opponent: {args.games} | Seed: {args.seed} | Workers: {args.workers}")
    print("")
    print("Rank  Policy            Win Rate   W-L        Games  Illegal  Avg Turns  MCTS(i/d)")
    for i, row in enumerate(ranked, start=1):
        policy = str(row["policy"])
        wr = f"{float(row['win_rate']) * 100:6.2f}%"
        wl = f"{int(row['wins'])}-{int(row['losses'])}"
        games = int(row["games"])
        illegal = int(row["illegal_actions"])
        avg_turns = f"{float(row['avg_turns']):.2f}"
        mcts_id = "-"
        if policy == "mcts":
            mcts_id = f"{int(row['mcts_iterations'])}/{int(row['mcts_max_depth'])}"
        print(f"{i:>4}  {policy:<16}  {wr:<8}  {wl:<9}  {games:>5}  {illegal:>7}  {avg_turns:>9}  {mcts_id:>9}")

    payload = {
        "created_at": _now_iso(),
        "candidate_deck_id": candidate.deck_id,
        "candidate_name": candidate.name,
        "opponent_set": args.opponents,
        "opponent_count": len(opponents),
        "games_per_opponent": int(args.games),
        "seed": int(args.seed),
        "workers": int(args.workers),
        "min_cards": int(min_cards),
        "requested_policies": policies,
        "ranked": ranked,
    }

    out_json = str(args.out_json or "").strip()
    if out_json != "":
        out_path = Path(out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print("")
        print(f"Wrote shootout report: {out_path}")
    return 0


def cmd_rl_collect(args: argparse.Namespace) -> int:
    min_cards = _coerce_min_cards(getattr(args, "min_cards", DEFAULT_MIN_DECK_SIZE))
    candidate, opponents = _resolve_candidate_and_opponents(args.candidate, args.opponents, min_cards)
    policies = _parse_policy_list(args.policies)
    all_rows, collected_by_policy, policy_reports = _collect_rl_rows_for_candidate(
        candidate=candidate,
        opponents=opponents,
        policies=policies,
        games=args.games,
        seed=args.seed,
        workers=args.workers,
        php_script=args.php_script,
        mcts_iterations=args.mcts_iterations,
        mcts_max_depth=args.mcts_max_depth,
        hash_dim=args.hash_dim,
        match_logs_dir=None,
    )
    for report in policy_reports:
        policy = str(report.get("policy", "unknown"))
        count = int(report.get("rows_collected", 0))
        print(f"Collected {count} rows from policy={policy}")

    if args.output_prefix:
        prefix = Path(args.output_prefix)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        prefix = Path("sim_harness/data/rl") / f"{candidate.deck_id}-{ts}"

    meta_payload = {
        "created_at": _now_iso(),
        "candidate_deck_id": candidate.deck_id,
        "candidate_name": candidate.name,
        "opponent_set": args.opponents,
        "opponent_count": len(opponents),
        "games_per_opponent": int(args.games),
        "seed": int(args.seed),
        "workers": int(args.workers),
        "min_cards": int(min_cards),
        "policies": policies,
        "hash_dim": int(args.hash_dim),
        "mcts_iterations": int(args.mcts_iterations),
        "mcts_max_depth": int(args.mcts_max_depth),
        "rows_by_policy": collected_by_policy,
        "policy_reports": policy_reports,
    }
    bundle = _write_rl_dataset_bundle(rows=all_rows, output_prefix=prefix, meta=meta_payload)

    print("")
    print(f"Dataset rows: {bundle['total_rows']}")
    print(f"Action vocab size: {bundle['action_vocab_size']}")
    print(f"Dataset: {bundle['dataset_path']}")
    print(f"Vocab:   {bundle['vocab_path']}")
    print(f"Meta:    {bundle['meta_path']}")
    return 0


def cmd_rl_train(args: argparse.Namespace) -> int:
    from .rl.train import train_policy_value_model

    summary = train_policy_value_model(
        dataset_path=args.dataset,
        vocab_path=args.vocab,
        model_out=args.model_out,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        val_split=args.val_split,
        hidden_dim=args.hidden_dim,
        hidden_layers=args.hidden_layers,
        dropout=args.dropout,
        value_loss_weight=args.value_loss_weight,
        seed=args.seed,
        device=args.device,
    )
    _safe_daily_backup(refresh_today=True)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_rl_loop(args: argparse.Namespace) -> int:
    from .rl.train import train_policy_value_model

    min_cards = _coerce_min_cards(getattr(args, "min_cards", DEFAULT_MIN_DECK_SIZE))
    policies = _parse_policy_list(args.policies)
    if args.iterations < 1:
        raise ValueError("iterations must be >= 1")
    if args.seed_step < 1:
        raise ValueError("seed_step must be >= 1")
    if args.eval_games < 1:
        raise ValueError("eval_games must be >= 1")
    if args.eval_policy not in SUPPORTED_POLICIES:
        allowed = ", ".join(SUPPORTED_POLICIES)
        raise ValueError(f"Unsupported eval policy '{args.eval_policy}'. Allowed: {allowed}")

    run_id = str(args.run_id or datetime.now(timezone.utc).strftime("loop-%Y%m%d-%H%M%S"))
    run_dir = Path(args.run_dir) if args.run_dir else Path("sim_harness/data/rl/loops") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    active_candidate_id = str(args.candidate)
    run_meta = {
        "run_id": run_id,
        "created_at": _now_iso(),
        "run_dir": str(run_dir),
        "iterations": int(args.iterations),
        "active_candidate_start": active_candidate_id,
        "candidate_pool_csv": str(args.candidate_pool or ""),
        "include_candidate_store_pool": bool(args.include_candidate_store_pool),
        "opponents": str(args.opponents),
        "games_per_opponent": int(args.games),
        "eval_games_per_opponent": int(args.eval_games),
        "seed": int(args.seed),
        "seed_step": int(args.seed_step),
        "workers": int(args.workers),
        "min_cards": int(min_cards),
        "policies": policies,
        "eval_policy": str(args.eval_policy),
        "mcts_iterations": int(args.mcts_iterations),
        "mcts_max_depth": int(args.mcts_max_depth),
        "eval_mcts_iterations": int(args.eval_mcts_iterations),
        "eval_mcts_max_depth": int(args.eval_mcts_max_depth),
        "hash_dim": int(args.hash_dim),
        "train": {
            "epochs": int(args.epochs),
            "batch_size": int(args.batch_size),
            "lr": float(args.lr),
            "weight_decay": float(args.weight_decay),
            "val_split": float(args.val_split),
            "hidden_dim": int(args.hidden_dim),
            "hidden_layers": int(args.hidden_layers),
            "dropout": float(args.dropout),
            "value_loss_weight": float(args.value_loss_weight),
            "seed": int(args.train_seed),
            "device": str(args.device),
        },
        "hooks": {
            "deck_generator_cmd": str(args.deck_generator_cmd or ""),
            "post_train_hook": str(args.post_train_hook or ""),
            "allow_hook_failures": bool(args.allow_hook_failures),
        },
        "advance_candidate_on_eval": bool(args.advance_candidate_on_eval),
    }
    (run_dir / "run.meta.json").write_text(json.dumps(run_meta, indent=2) + "\n", encoding="utf-8")

    iteration_reports: list[dict[str, Any]] = []
    for iteration in range(1, int(args.iterations) + 1):
        iteration_seed = int(args.seed) + ((iteration - 1) * int(args.seed_step))
        iter_dir = run_dir / f"iteration_{iteration:03d}"
        collect_dir = iter_dir / "collect"
        train_dir = iter_dir / "train"
        eval_dir = iter_dir / "eval"
        collect_dir.mkdir(parents=True, exist_ok=True)
        train_dir.mkdir(parents=True, exist_ok=True)
        eval_dir.mkdir(parents=True, exist_ok=True)

        print("")
        print(f"[loop] iteration={iteration} seed={iteration_seed} active_candidate={active_candidate_id}")

        pre_hook = _run_loop_hook(
            args.deck_generator_cmd,
            iteration=iteration,
            run_dir=run_dir,
            stage="deck_generator",
            fail_on_error=not bool(args.allow_hook_failures),
            extra_env={
                "DECKXPERT_LOOP_SEED": str(iteration_seed),
                "DECKXPERT_LOOP_ACTIVE_CANDIDATE": str(active_candidate_id),
            },
        )

        candidate_ids = _resolve_loop_candidate_ids(
            primary_candidate=active_candidate_id,
            candidate_pool_csv=args.candidate_pool,
            include_store_pool=bool(args.include_candidate_store_pool),
        )
        print(f"[loop] candidate_pool_size={len(candidate_ids)} ({', '.join(candidate_ids)})")

        all_rows: list[dict[str, Any]] = []
        candidate_collect_reports: list[dict[str, Any]] = []
        for idx, candidate_id in enumerate(candidate_ids):
            candidate_seed = iteration_seed + (idx * 9973)
            candidate, opponents = _resolve_candidate_and_opponents(candidate_id, args.opponents, min_cards)
            rows, rows_by_policy, policy_reports = _collect_rl_rows_for_candidate(
                candidate=candidate,
                opponents=opponents,
                policies=policies,
                games=args.games,
                seed=candidate_seed,
                workers=args.workers,
                php_script=args.php_script,
                mcts_iterations=args.mcts_iterations,
                mcts_max_depth=args.mcts_max_depth,
                hash_dim=args.hash_dim,
                match_logs_dir=collect_dir / "matches",
            )
            all_rows.extend(rows)
            candidate_collect_reports.append(
                {
                    "candidate_deck_id": candidate.deck_id,
                    "candidate_name": candidate.name,
                    "candidate_seed": candidate_seed,
                    "opponent_count": len(opponents),
                    "rows_collected": len(rows),
                    "rows_by_policy": rows_by_policy,
                    "policy_reports": policy_reports,
                }
            )
            print(f"[loop] collected candidate={candidate.deck_id} rows={len(rows)}")

        collect_prefix = collect_dir / "training_data"
        collect_meta = {
            "created_at": _now_iso(),
            "iteration": iteration,
            "run_id": run_id,
            "candidate_ids": candidate_ids,
            "opponent_set": args.opponents,
            "games_per_opponent": int(args.games),
            "workers": int(args.workers),
            "min_cards": int(min_cards),
            "policies": policies,
            "hash_dim": int(args.hash_dim),
            "mcts_iterations": int(args.mcts_iterations),
            "mcts_max_depth": int(args.mcts_max_depth),
            "candidate_reports": candidate_collect_reports,
        }
        bundle = _write_rl_dataset_bundle(rows=all_rows, output_prefix=collect_prefix, meta=collect_meta)
        print(
            "[loop] dataset rows="
            f"{bundle['total_rows']} vocab={bundle['action_vocab_size']} path={bundle['dataset_path']}"
        )

        model_path = train_dir / "policy_value.pt"
        train_summary = train_policy_value_model(
            dataset_path=bundle["dataset_path"],
            vocab_path=bundle["vocab_path"],
            model_out=str(model_path),
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            weight_decay=args.weight_decay,
            val_split=args.val_split,
            hidden_dim=args.hidden_dim,
            hidden_layers=args.hidden_layers,
            dropout=args.dropout,
            value_loss_weight=args.value_loss_weight,
            seed=args.train_seed + iteration - 1,
            device=args.device,
        )
        _safe_daily_backup(refresh_today=True)
        print(f"[loop] model={train_summary.get('model_path', str(model_path))}")

        eval_rows: list[dict[str, Any]] = []
        for idx, candidate_id in enumerate(candidate_ids):
            eval_seed = iteration_seed + 500000 + (idx * 9967)
            candidate, opponents = _resolve_candidate_and_opponents(candidate_id, args.opponents, min_cards)
            row = _evaluate_candidate(
                candidate=candidate,
                opponents=opponents,
                games=args.eval_games,
                seed=eval_seed,
                workers=args.workers,
                php_script=args.php_script,
                policy=args.eval_policy,
                mcts_iterations=args.eval_mcts_iterations,
                mcts_max_depth=args.eval_mcts_max_depth,
            )
            row["eval_seed"] = eval_seed
            eval_rows.append(row)

        eval_ranked = sorted(
            eval_rows,
            key=lambda row: (
                -float(row["win_rate"]),
                int(row["illegal_actions"]),
                float(row["avg_turns"]),
                str(row["candidate_deck_id"]),
            ),
        )
        eval_payload = {
            "iteration": iteration,
            "run_id": run_id,
            "policy": args.eval_policy,
            "games_per_opponent": int(args.eval_games),
            "ranked": eval_ranked,
        }
        eval_report_path = eval_dir / "candidate_ranking.json"
        eval_report_path.write_text(json.dumps(eval_payload, indent=2) + "\n", encoding="utf-8")

        best_candidate_id = eval_ranked[0]["candidate_deck_id"] if eval_ranked else active_candidate_id
        if bool(args.advance_candidate_on_eval):
            active_candidate_id = str(best_candidate_id)
            print(f"[loop] next active candidate set to {active_candidate_id}")

        post_hook = _run_loop_hook(
            args.post_train_hook,
            iteration=iteration,
            run_dir=run_dir,
            stage="post_train",
            fail_on_error=not bool(args.allow_hook_failures),
            extra_env={
                "DECKXPERT_LOOP_SEED": str(iteration_seed),
                "DECKXPERT_LOOP_ACTIVE_CANDIDATE": str(active_candidate_id),
                "DECKXPERT_LOOP_MODEL_PATH": str(train_summary.get("model_path", str(model_path))),
                "DECKXPERT_LOOP_DATASET_PATH": str(bundle["dataset_path"]),
                "DECKXPERT_LOOP_VOCAB_PATH": str(bundle["vocab_path"]),
                "DECKXPERT_LOOP_BEST_CANDIDATE": str(best_candidate_id),
                "DECKXPERT_LOOP_EVAL_REPORT": str(eval_report_path),
            },
        )

        iteration_report = {
            "iteration": iteration,
            "seed": iteration_seed,
            "active_candidate_start": candidate_ids[0] if candidate_ids else active_candidate_id,
            "candidate_ids": candidate_ids,
            "collect": bundle,
            "train": train_summary,
            "evaluation": {
                "policy": args.eval_policy,
                "games_per_opponent": int(args.eval_games),
                "best_candidate_deck_id": best_candidate_id,
                "ranking_path": str(eval_report_path),
                "ranked": eval_ranked,
            },
            "hooks": {
                "deck_generator": pre_hook,
                "post_train": post_hook,
            },
            "active_candidate_end": active_candidate_id,
        }
        iteration_report_path = iter_dir / "iteration_report.json"
        iteration_report_path.write_text(json.dumps(iteration_report, indent=2) + "\n", encoding="utf-8")
        iteration_reports.append(iteration_report)

    run_summary = {
        "run_id": run_id,
        "created_at": run_meta["created_at"],
        "finished_at": _now_iso(),
        "iterations_requested": int(args.iterations),
        "iterations_completed": len(iteration_reports),
        "run_dir": str(run_dir),
        "final_active_candidate": active_candidate_id,
        "iteration_reports": [str(run_dir / f"iteration_{i:03d}" / "iteration_report.json") for i in range(1, len(iteration_reports) + 1)],
    }
    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(json.dumps(run_summary, indent=2) + "\n", encoding="utf-8")
    _safe_daily_backup(refresh_today=True)

    print("")
    print(f"[loop] completed iterations={len(iteration_reports)}")
    print(f"[loop] run_dir={run_dir}")
    print(f"[loop] summary={summary_path}")
    return 0



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deckxpert simulation manager CLI")
    sub = parser.add_subparsers(dest="entity", required=True)

    deck = sub.add_parser("deck", help="Manage deck library")
    deck_sub = deck.add_subparsers(dest="action", required=True)

    deck_upload = deck_sub.add_parser("upload", help="Upload SWUDB deck JSON")
    deck_upload.add_argument("--file", required=True, help="Path to SWUDB deck JSON")
    deck_upload.add_argument("--pool", choices=["meta", "starter", "candidate"], required=True)
    deck_upload.add_argument("--deck-id", help="Optional custom deck id")
    deck_upload.set_defaults(func=cmd_deck_upload)

    deck_random = deck_sub.add_parser("random", help="Generate random decks (1 leader + 1 base + 30/50 main cards)")
    deck_random.add_argument("--count", type=int, default=1, help="How many random decks to generate")
    deck_random.add_argument("--pool", choices=["candidate", "meta", "starter"], default="candidate")
    deck_random.add_argument("--main-size", type=int, choices=sorted(SUPPORTED_MIN_DECK_SIZES), default=DEFAULT_MIN_DECK_SIZE)
    deck_random.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducibility")
    deck_random.add_argument("--deck-id", default=None, help="Explicit deck id (only when --count 1)")
    deck_random.add_argument("--deck-id-prefix", default="random", help="Deck id prefix for generated ids")
    deck_random.add_argument("--name-prefix", default="Random Deck", help="Deck metadata name prefix")
    deck_random.add_argument("--author", default="sim_harness_random", help="Deck metadata author")
    deck_random.add_argument("--max-copies", type=int, default=3, help="Max copies per non-leader/base card")
    deck_random.set_defaults(func=cmd_deck_random)

    deck_list = deck_sub.add_parser("list", help="List decks")
    deck_list.add_argument("--pool", choices=["all", "meta", "starter", "candidate"], default="all")
    deck_list.set_defaults(func=cmd_deck_list)

    deck_show = deck_sub.add_parser("show", help="Show one deck")
    deck_show.add_argument("deck_id")
    deck_show.add_argument("--format", choices=["summary", "swudb"], default="summary")
    deck_show.set_defaults(func=cmd_deck_show)

    deck_delete = deck_sub.add_parser("delete", help="Delete one deck")
    deck_delete.add_argument("deck_id")
    deck_delete.set_defaults(func=cmd_deck_delete)

    sim = sub.add_parser("sim", help="Manage simulations")
    sim_sub = sim.add_subparsers(dest="action", required=True)

    sim_create = sim_sub.add_parser("create", help="Create a simulation for one candidate deck")
    sim_create.add_argument("--candidate", required=True, help="Candidate deck id")
    sim_create.add_argument("--opponents", choices=["meta", "starter", "all"], default="all")
    sim_create.add_argument("--games", type=int, default=20, help="Games per opponent")
    sim_create.add_argument("--seed", type=int, default=42)
    sim_create.add_argument("--workers", type=int, default=4)
    sim_create.add_argument("--php-script", default=None)
    sim_create.add_argument("--sim-id", default=None)
    sim_create.add_argument("--min-cards", type=int, choices=sorted(SUPPORTED_MIN_DECK_SIZES), default=DEFAULT_MIN_DECK_SIZE)
    sim_create.add_argument(
        "--policy",
        choices=list(SUPPORTED_POLICIES),
        default="random_legal",
    )
    sim_create.add_argument("--mcts-iterations", type=int, default=16)
    sim_create.add_argument("--mcts-max-depth", type=int, default=14)
    sim_create.set_defaults(func=cmd_sim_create)

    sim_results = sim_sub.add_parser("results", help="Show top-level sim results")
    sim_results.add_argument("sim_id")
    sim_results.set_defaults(func=cmd_sim_results)

    sim_decks = sim_sub.add_parser("decks", help="Show decks in simulation")
    sim_decks.add_argument("sim_id")
    sim_decks.set_defaults(func=cmd_sim_decks)

    sim_analysis = sim_sub.add_parser("analysis", help="Detailed simulation analysis")
    sim_analysis.add_argument("sim_id")
    sim_analysis.set_defaults(func=cmd_sim_analysis)

    sim_shootout = sim_sub.add_parser("shootout", help="Compare multiple policies on the same matchup/seed set")
    sim_shootout.add_argument("--candidate", required=True, help="Candidate deck id")
    sim_shootout.add_argument("--opponents", choices=["meta", "starter", "all"], default="all")
    sim_shootout.add_argument("--games", type=int, default=20, help="Games per opponent")
    sim_shootout.add_argument("--seed", type=int, default=42)
    sim_shootout.add_argument("--workers", type=int, default=4)
    sim_shootout.add_argument("--php-script", default=None)
    sim_shootout.add_argument("--min-cards", type=int, choices=sorted(SUPPORTED_MIN_DECK_SIZES), default=DEFAULT_MIN_DECK_SIZE)
    sim_shootout.add_argument(
        "--policies",
        default="random_legal,heuristic,mcts",
        help="Comma-separated list. Example: random_legal,heuristic,mcts",
    )
    sim_shootout.add_argument("--mcts-iterations", type=int, default=16)
    sim_shootout.add_argument("--mcts-max-depth", type=int, default=14)
    sim_shootout.add_argument("--out-json", default=None, help="Optional report output path")
    sim_shootout.set_defaults(func=cmd_sim_shootout)

    rl = sub.add_parser("rl", help="RL dataset/model tooling")
    rl_sub = rl.add_subparsers(dest="action", required=True)

    rl_collect = rl_sub.add_parser("collect", help="Collect supervised policy/value dataset from simulated games")
    rl_collect.add_argument("--candidate", required=True, help="Candidate deck id")
    rl_collect.add_argument("--opponents", choices=["meta", "starter", "all"], default="all")
    rl_collect.add_argument("--games", type=int, default=20, help="Games per opponent")
    rl_collect.add_argument("--seed", type=int, default=42)
    rl_collect.add_argument("--workers", type=int, default=4)
    rl_collect.add_argument("--php-script", default=None)
    rl_collect.add_argument("--min-cards", type=int, choices=sorted(SUPPORTED_MIN_DECK_SIZES), default=DEFAULT_MIN_DECK_SIZE)
    rl_collect.add_argument(
        "--policies",
        default="heuristic,mcts",
        help="Comma-separated policy list. Example: heuristic,mcts",
    )
    rl_collect.add_argument("--mcts-iterations", type=int, default=16)
    rl_collect.add_argument("--mcts-max-depth", type=int, default=14)
    rl_collect.add_argument("--hash-dim", type=int, default=256, help="Hashed card-feature dimensions")
    rl_collect.add_argument("--output-prefix", default=None, help="Output prefix (without extension)")
    rl_collect.set_defaults(func=cmd_rl_collect)

    rl_train = rl_sub.add_parser("train", help="Train policy/value model from exported dataset")
    rl_train.add_argument("--dataset", required=True, help="Dataset jsonl path from rl collect")
    rl_train.add_argument("--vocab", required=True, help="Action vocab json path from rl collect")
    rl_train.add_argument("--model-out", required=True, help="Output model checkpoint path (.pt)")
    rl_train.add_argument("--epochs", type=int, default=10)
    rl_train.add_argument("--batch-size", type=int, default=256)
    rl_train.add_argument("--lr", type=float, default=1e-3)
    rl_train.add_argument("--weight-decay", type=float, default=1e-5)
    rl_train.add_argument("--val-split", type=float, default=0.1)
    rl_train.add_argument("--hidden-dim", type=int, default=256)
    rl_train.add_argument("--hidden-layers", type=int, default=2)
    rl_train.add_argument("--dropout", type=float, default=0.1)
    rl_train.add_argument("--value-loss-weight", type=float, default=1.0)
    rl_train.add_argument("--seed", type=int, default=42)
    rl_train.add_argument("--device", default="auto", help="auto/cpu/cuda")
    rl_train.set_defaults(func=cmd_rl_train)

    rl_loop = rl_sub.add_parser("loop", help="Run iterative collect->train->evaluate loop with per-iteration artifacts")
    rl_loop.add_argument("--candidate", required=True, help="Primary candidate deck id")
    rl_loop.add_argument("--candidate-pool", default="", help="Optional extra candidate deck ids (csv)")
    rl_loop.add_argument(
        "--include-candidate-store-pool",
        action="store_true",
        help="Include all decks from pool=candidate in each loop iteration",
    )
    rl_loop.add_argument("--opponents", choices=["meta", "starter", "all"], default="all")
    rl_loop.add_argument("--iterations", type=int, default=3)
    rl_loop.add_argument("--games", type=int, default=20, help="Self-play games per opponent during collection")
    rl_loop.add_argument("--eval-games", type=int, default=20, help="Evaluation games per opponent")
    rl_loop.add_argument("--seed", type=int, default=42)
    rl_loop.add_argument("--seed-step", type=int, default=1000, help="Seed increment per iteration")
    rl_loop.add_argument("--workers", type=int, default=4)
    rl_loop.add_argument("--php-script", default=None)
    rl_loop.add_argument("--min-cards", type=int, choices=sorted(SUPPORTED_MIN_DECK_SIZES), default=DEFAULT_MIN_DECK_SIZE)
    rl_loop.add_argument(
        "--policies",
        default="heuristic,mcts",
        help="Comma-separated policy list for dataset collection",
    )
    rl_loop.add_argument("--mcts-iterations", type=int, default=16)
    rl_loop.add_argument("--mcts-max-depth", type=int, default=14)
    rl_loop.add_argument("--eval-policy", choices=list(SUPPORTED_POLICIES), default="mcts")
    rl_loop.add_argument("--eval-mcts-iterations", type=int, default=24)
    rl_loop.add_argument("--eval-mcts-max-depth", type=int, default=18)
    rl_loop.add_argument("--hash-dim", type=int, default=256)
    rl_loop.add_argument("--run-id", default=None, help="Optional loop run id")
    rl_loop.add_argument("--run-dir", default=None, help="Optional loop output directory")
    rl_loop.add_argument("--deck-generator-cmd", default=None, help="Optional command run at each iteration start")
    rl_loop.add_argument("--post-train-hook", default=None, help="Optional command run after each model train")
    rl_loop.add_argument(
        "--allow-hook-failures",
        action="store_true",
        help="Do not fail loop when optional hook commands exit non-zero",
    )
    rl_loop.add_argument(
        "--advance-candidate-on-eval",
        action="store_true",
        help="Set next iteration primary candidate to top eval-ranked deck",
    )
    rl_loop.add_argument("--epochs", type=int, default=10)
    rl_loop.add_argument("--batch-size", type=int, default=256)
    rl_loop.add_argument("--lr", type=float, default=1e-3)
    rl_loop.add_argument("--weight-decay", type=float, default=1e-5)
    rl_loop.add_argument("--val-split", type=float, default=0.1)
    rl_loop.add_argument("--hidden-dim", type=int, default=256)
    rl_loop.add_argument("--hidden-layers", type=int, default=2)
    rl_loop.add_argument("--dropout", type=float, default=0.1)
    rl_loop.add_argument("--value-loss-weight", type=float, default=1.0)
    rl_loop.add_argument("--train-seed", type=int, default=42, help="Base training seed")
    rl_loop.add_argument("--device", default="auto", help="auto/cpu/cuda")
    rl_loop.set_defaults(func=cmd_rl_loop)

    return parser



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _safe_daily_backup(refresh_today=False)
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
