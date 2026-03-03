from __future__ import annotations

import argparse
import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import MatchResult, run_benchmark

DATA_DIR = Path("sim_harness") / "data"
DECKS_FILE = DATA_DIR / "decks.json"
SIMS_FILE = DATA_DIR / "simulations.json"
SUPPORTED_MIN_DECK_SIZES = {30, 50}
DEFAULT_MIN_DECK_SIZE = 50


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
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")



def _validate_swudb_deck(payload: dict[str, Any]) -> None:
    required_top = ["metadata", "leader", "base", "deck"]
    for key in required_top:
        if key not in payload:
            raise ValueError(f"Missing SWUDB field: {key}")

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



def cmd_deck_upload(args: argparse.Namespace) -> int:
    decks = _load_decks()
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    _validate_swudb_deck(payload)

    deck_id = args.deck_id or uuid.uuid4().hex[:12]
    if any(d.deck_id == deck_id for d in decks):
        raise ValueError(f"Deck id already exists: {deck_id}")

    record = DeckRecord(deck_id=deck_id, pool=args.pool, swudb=payload, added_at=_now_iso())
    decks.append(record)
    _save_decks(decks)

    print(f"Uploaded deck {record.deck_id} :: {record.name} [{record.pool}] by {record.author}")
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



def _load_sims() -> list[dict[str, Any]]:
    return _read_json_list(SIMS_FILE)



def _save_sims(sims: list[dict[str, Any]]) -> None:
    _write_json_list(SIMS_FILE, sims)



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
        seed_policy={"global_seed": args.seed, "php_script": args.php_script},
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
        opponent_results.append(
            {
                "deck_id": opp.deck_id,
                "deck_name": opp.name,
                "pool": opp.pool,
                "games": games,
                "wins": wins,
                "win_rate": round(win_rate, 4),
                "avg_turns": round(statistics.fmean(turns), 2) if turns else 0.0,
            }
        )

    all_games = sum(r["games"] for r in opponent_results)
    all_wins = sum(r["wins"] for r in opponent_results)

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
        "min_cards": min_cards,
        "overall": {
            "games": all_games,
            "wins": all_wins,
            "losses": all_games - all_wins,
            "win_rate": round((all_wins / all_games), 4) if all_games else 0.0,
        },
        "opponents": opponent_results,
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
    print(f"Overall win rate: {sim['overall']['win_rate']:.2%} ({sim['overall']['wins']}/{sim['overall']['games']})")

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

    deck_list = deck_sub.add_parser("list", help="List decks")
    deck_list.add_argument("--pool", choices=["all", "meta", "starter", "candidate"], default="all")
    deck_list.set_defaults(func=cmd_deck_list)

    deck_show = deck_sub.add_parser("show", help="Show one deck")
    deck_show.add_argument("deck_id")
    deck_show.add_argument("--format", choices=["summary", "swudb"], default="summary")
    deck_show.set_defaults(func=cmd_deck_show)

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

    return parser



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
