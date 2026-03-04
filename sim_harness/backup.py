from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path("sim_harness") / "data"
DEFAULT_RETENTION_DAYS = 30
BACKUP_DIR_NAME = "backups"
RL_BLOBS_DIR_NAME = "rl_blobs"


def _daily_stamp() -> str:
    return datetime.now().date().isoformat()


def _is_daily_snapshot_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name
    if len(name) != 10:
        return False
    try:
        datetime.strptime(name, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _prune_old_snapshots(backup_root: Path, retention_days: int) -> list[str]:
    snapshots = sorted([p for p in backup_root.iterdir() if _is_daily_snapshot_dir(p)], key=lambda p: p.name, reverse=True)
    removed: list[str] = []
    for old in snapshots[retention_days:]:
        shutil.rmtree(old, ignore_errors=True)
        removed.append(old.name)
    return removed


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    shutil.copy2(src, dst)
    return True


def _archive_rl_dir(rl_dir: Path, dst_tar_gz: Path) -> dict[str, Any]:
    files = [p for p in rl_dir.rglob("*") if p.is_file()]
    files.sort(key=lambda p: str(p.relative_to(rl_dir)))
    if len(files) == 0:
        return {"present": False, "files": 0, "size_bytes": 0, "fingerprint": ""}

    digest = hashlib.sha256()
    total_bytes = 0
    for path in files:
        rel = str(path.relative_to(rl_dir)).replace("\\", "/")
        st = path.stat()
        digest.update(rel.encode("utf-8"))
        digest.update(b"|")
        digest.update(str(int(st.st_size)).encode("ascii"))
        digest.update(b"|")
        digest.update(str(int(st.st_mtime_ns)).encode("ascii"))
        digest.update(b"\n")
        total_bytes += int(st.st_size)
    fingerprint = digest.hexdigest()

    with tarfile.open(dst_tar_gz, "w:gz") as tar:
        tar.add(rl_dir, arcname="rl")
    return {
        "present": True,
        "files": len(files),
        "size_bytes": total_bytes,
        "fingerprint": fingerprint,
    }


def _prune_orphaned_rl_blobs(backup_root: Path, blobs_dir: Path) -> list[str]:
    if not blobs_dir.exists():
        return []
    referenced: set[str] = set()
    for snap in backup_root.iterdir():
        if not _is_daily_snapshot_dir(snap):
            continue
        manifest = snap / "manifest.json"
        if not manifest.exists():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        blob_name = str(payload.get("rl_blob", "")).strip()
        if blob_name:
            referenced.add(blob_name)

    removed: list[str] = []
    for blob in blobs_dir.iterdir():
        if not blob.is_file():
            continue
        if blob.name not in referenced:
            blob.unlink(missing_ok=True)
            removed.append(blob.name)
    return removed


def ensure_daily_data_backup(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    refresh_today: bool = False,
) -> dict[str, Any]:
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")

    data_dir = Path(data_dir)
    backup_root = data_dir / BACKUP_DIR_NAME
    blobs_dir = backup_root / RL_BLOBS_DIR_NAME
    backup_root.mkdir(parents=True, exist_ok=True)
    blobs_dir.mkdir(parents=True, exist_ok=True)

    stamp = _daily_stamp()
    snapshot_dir = backup_root / stamp
    manifest_path = snapshot_dir / "manifest.json"

    if snapshot_dir.exists() and not refresh_today:
        removed = _prune_old_snapshots(backup_root, retention_days)
        removed_blobs = _prune_orphaned_rl_blobs(backup_root, blobs_dir)
        return {
            "created": False,
            "refreshed": False,
            "snapshot_dir": str(snapshot_dir),
            "removed": removed,
            "removed_rl_blobs": removed_blobs,
        }

    tmp_dir = backup_root / f".tmp-{stamp}-{datetime.now().strftime('%H%M%S%f')}"
    tmp_dir.mkdir(parents=True, exist_ok=False)

    decks_src = data_dir / "decks.json"
    sims_src = data_dir / "simulations.json"
    rl_src = data_dir / "rl"

    copied = {
        "decks_json": _copy_if_exists(decks_src, tmp_dir / "decks.json"),
        "simulations_json": _copy_if_exists(sims_src, tmp_dir / "simulations.json"),
    }
    rl_info: dict[str, Any] = {"present": False, "files": 0, "size_bytes": 0, "fingerprint": ""}
    rl_blob = ""
    if rl_src.exists() and rl_src.is_dir():
        blob_tmp = tmp_dir / "rl_data.tar.gz"
        rl_info = _archive_rl_dir(rl_src, blob_tmp)
        if bool(rl_info.get("present")):
            fp = str(rl_info.get("fingerprint", "")).strip()
            if fp:
                rl_blob = f"{fp}.tar.gz"
                blob_dst = blobs_dir / rl_blob
                if not blob_dst.exists():
                    blob_tmp.rename(blob_dst)
                else:
                    blob_tmp.unlink(missing_ok=True)
            else:
                blob_tmp.unlink(missing_ok=True)
        else:
            blob_tmp.unlink(missing_ok=True)

    manifest = {
        "created_at": datetime.now().isoformat(),
        "snapshot_day": stamp,
        "retention_days": int(retention_days),
        "data_dir": str(data_dir),
        "copied": copied,
        "rl_archive": rl_info,
        "rl_blob": rl_blob,
    }
    _write_manifest(tmp_dir / "manifest.json", manifest)

    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir, ignore_errors=True)
    tmp_dir.rename(snapshot_dir)

    removed = _prune_old_snapshots(backup_root, retention_days)
    removed_blobs = _prune_orphaned_rl_blobs(backup_root, blobs_dir)
    return {
        "created": True,
        "refreshed": bool(refresh_today),
        "snapshot_dir": str(snapshot_dir),
        "manifest": str(manifest_path),
        "removed": removed,
        "removed_rl_blobs": removed_blobs,
    }
