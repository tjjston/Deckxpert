from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

ZONE_REF_RE = re.compile(r"^([A-Z]+)-\d+$")


def _normalize_button_input(raw: Any) -> str:
    text = str(raw or "").strip()
    if text == "" or text == "-":
        return "-"
    upper = text.upper()
    if upper in {"YES", "NO"}:
        return upper
    if text.isdigit():
        return "<num>"
    if len(text) <= 4 and text.isalpha() and text.isupper():
        return text
    if any(c.isdigit() for c in text):
        return "<choice_num>"
    if len(text) <= 20 and text.replace("_", "").isalpha():
        return "<choice_word>"
    return "<choice>"


def _normalize_card_ref(raw: Any) -> str:
    if isinstance(raw, int):
        return "<index>"
    text = str(raw or "").strip()
    if text == "" or text == "0":
        return "0"
    if text.isdigit():
        return "<index>"
    zone_match = ZONE_REF_RE.match(text)
    if zone_match:
        return zone_match.group(1)
    if len(text) >= 8 and text.isdigit():
        return "<card>"
    return "<ref>"


def _normalize_chk_input(raw: Any) -> str:
    if isinstance(raw, list):
        return f"<list_{len(raw)}>"
    text = str(raw or "").strip()
    if text == "":
        return "0"
    if text.isdigit():
        return "<num>"
    return "<input>"


def _normalize_input_text(raw: Any) -> str:
    text = str(raw or "").strip()
    if text == "":
        return "0"
    if text.isdigit():
        return "<num>"
    if len(text) <= 24 and text.replace(" ", "").replace("-", "").isalpha():
        return "<text_word>"
    return "<text>"


def canonical_action_key(action: Mapping[str, Any]) -> str:
    action_type = str(action.get("type", "unknown")).strip() or "unknown"
    mode = int(action.get("mode", 0) or 0)
    button = _normalize_button_input(action.get("buttonInput", ""))
    card = _normalize_card_ref(action.get("cardID", 0))
    chk_count = int(action.get("chkCount", 0) or 0)
    chk_input = _normalize_chk_input(action.get("chkInput", ""))
    input_text = _normalize_input_text(action.get("inputText", ""))
    return f"{action_type}|m{mode}|b{button}|c{card}|k{chk_count}|x{chk_input}|t{input_text}"


@dataclass
class ActionVocab:
    key_to_idx: dict[str, int] = field(default_factory=dict)
    idx_to_key: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.idx_to_key)

    def add(self, key: str) -> int:
        if key in self.key_to_idx:
            return self.key_to_idx[key]
        idx = len(self.idx_to_key)
        self.key_to_idx[key] = idx
        self.idx_to_key.append(key)
        return idx

    def encode(self, key: str) -> int:
        if key not in self.key_to_idx:
            raise KeyError(f"Unknown action key: {key}")
        return self.key_to_idx[key]

    def decode(self, idx: int) -> str:
        return self.idx_to_key[idx]

    def to_dict(self) -> dict[str, Any]:
        return {"idx_to_key": list(self.idx_to_key)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionVocab":
        idx_to_key = [str(k) for k in payload.get("idx_to_key", [])]
        vocab = cls()
        for key in idx_to_key:
            vocab.add(key)
        return vocab

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "ActionVocab":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid vocab payload in {path}")
        return cls.from_dict(payload)
