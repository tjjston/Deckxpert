from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from .action_space import ActionVocab
from .dataset import load_dataset_rows, vectorize_rows
from .model import PolicyValueNet, torch


def _resolve_device(device: str) -> str:
    if torch is None:
        raise RuntimeError("PyTorch is not installed. Install torch to train policy/value models.")
    if device != "auto":
        return device
    return "cuda" if torch.cuda.is_available() else "cpu"


def train_policy_value_model(
    dataset_path: str,
    vocab_path: str,
    model_out: str,
    epochs: int = 10,
    batch_size: int = 256,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    val_split: float = 0.1,
    hidden_dim: int = 256,
    hidden_layers: int = 2,
    dropout: float = 0.1,
    value_loss_weight: float = 1.0,
    seed: int = 42,
    device: str = "auto",
) -> dict[str, Any]:
    if torch is None:
        raise RuntimeError("PyTorch is not installed. Install torch to train policy/value models.")
    if epochs < 1:
        raise ValueError("epochs must be >= 1")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if not (0.0 <= val_split < 0.9):
        raise ValueError("val_split must be in [0.0, 0.9)")

    torch.manual_seed(seed)
    np.random.seed(seed)

    rows = load_dataset_rows(dataset_path)
    vocab = ActionVocab.load_json(vocab_path)
    x_np, y_pi_np, y_v_np = vectorize_rows(rows, vocab)

    n = int(x_np.shape[0])
    perm = np.random.permutation(n)
    x_np = x_np[perm]
    y_pi_np = y_pi_np[perm]
    y_v_np = y_v_np[perm]

    n_val = int(n * val_split)
    n_train = n - n_val
    if n_train <= 0:
        raise ValueError("Not enough rows to form a training split.")

    x_train, y_pi_train, y_v_train = x_np[:n_train], y_pi_np[:n_train], y_v_np[:n_train]
    x_val, y_pi_val, y_v_val = x_np[n_train:], y_pi_np[n_train:], y_v_np[n_train:]

    dev = _resolve_device(device)
    x_train_t = torch.from_numpy(x_train).to(dev)
    y_pi_train_t = torch.from_numpy(y_pi_train).to(dev)
    y_v_train_t = torch.from_numpy(y_v_train).to(dev)

    x_val_t = torch.from_numpy(x_val).to(dev) if n_val > 0 else None
    y_pi_val_t = torch.from_numpy(y_pi_val).to(dev) if n_val > 0 else None
    y_v_val_t = torch.from_numpy(y_v_val).to(dev) if n_val > 0 else None

    model = PolicyValueNet(
        input_dim=int(x_np.shape[1]),
        action_dim=len(vocab),
        hidden_dim=hidden_dim,
        hidden_layers=hidden_layers,
        dropout=dropout,
    ).to(dev)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    ce = torch.nn.CrossEntropyLoss()
    mse = torch.nn.MSELoss()

    history: list[dict[str, float]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        train_losses: list[float] = []
        train_pi_losses: list[float] = []
        train_v_losses: list[float] = []
        train_acc: list[float] = []

        for start in range(0, n_train, batch_size):
            end = min(n_train, start + batch_size)
            xb = x_train_t[start:end]
            yb_pi = y_pi_train_t[start:end]
            yb_v = y_v_train_t[start:end]
            optimizer.zero_grad(set_to_none=True)
            logits, v_pred = model(xb)
            loss_pi = ce(logits, yb_pi)
            loss_v = mse(v_pred, yb_v)
            loss = loss_pi + (value_loss_weight * loss_v)
            loss.backward()
            optimizer.step()

            with torch.no_grad():
                pred = torch.argmax(logits, dim=1)
                acc = (pred == yb_pi).float().mean().item()
            train_losses.append(float(loss.item()))
            train_pi_losses.append(float(loss_pi.item()))
            train_v_losses.append(float(loss_v.item()))
            train_acc.append(float(acc))

        row: dict[str, float] = {
            "epoch": float(epoch),
            "train_loss": float(np.mean(train_losses) if train_losses else 0.0),
            "train_policy_loss": float(np.mean(train_pi_losses) if train_pi_losses else 0.0),
            "train_value_loss": float(np.mean(train_v_losses) if train_v_losses else 0.0),
            "train_policy_acc": float(np.mean(train_acc) if train_acc else 0.0),
        }

        if n_val > 0 and x_val_t is not None and y_pi_val_t is not None and y_v_val_t is not None:
            model.eval()
            with torch.no_grad():
                logits_val, v_val_pred = model(x_val_t)
                val_pi_loss = ce(logits_val, y_pi_val_t).item()
                val_v_loss = mse(v_val_pred, y_v_val_t).item()
                val_loss = val_pi_loss + (value_loss_weight * val_v_loss)
                val_acc = (torch.argmax(logits_val, dim=1) == y_pi_val_t).float().mean().item()
            row["val_loss"] = float(val_loss)
            row["val_policy_loss"] = float(val_pi_loss)
            row["val_value_loss"] = float(val_v_loss)
            row["val_policy_acc"] = float(val_acc)

        history.append(row)
        print(
            f"epoch={epoch:03d} train_loss={row['train_loss']:.4f} "
            f"train_acc={row['train_policy_acc']:.4f} "
            f"val_loss={row.get('val_loss', 0.0):.4f} "
            f"val_acc={row.get('val_policy_acc', 0.0):.4f}"
        )

    model_path = Path(model_out)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": int(x_np.shape[1]),
            "action_dim": int(len(vocab)),
            "hidden_dim": int(hidden_dim),
            "hidden_layers": int(hidden_layers),
            "dropout": float(dropout),
            "dataset_path": str(dataset_path),
            "vocab_path": str(vocab_path),
            "history": history,
        },
        model_path,
    )

    summary = {
        "model_path": str(model_path),
        "input_dim": int(x_np.shape[1]),
        "action_dim": int(len(vocab)),
        "train_rows": int(n_train),
        "val_rows": int(n_val),
        "epochs": int(epochs),
        "device": dev,
        "history_last": history[-1] if history else {},
    }
    summary_path = model_path.with_suffix(model_path.suffix + ".meta.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a policy/value network from sim_harness dataset exports.")
    parser.add_argument("--dataset", required=True, help="Path to dataset jsonl")
    parser.add_argument("--vocab", required=True, help="Path to action vocab json")
    parser.add_argument("--model-out", required=True, help="Output .pt file path")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--hidden-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--value-loss-weight", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto", help="auto/cpu/cuda")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
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
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
