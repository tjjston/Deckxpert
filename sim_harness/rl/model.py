from __future__ import annotations

from typing import Any

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - handled at runtime
    torch = None
    nn = None


if nn is not None:

    class PolicyValueNet(nn.Module):
        def __init__(
            self,
            input_dim: int,
            action_dim: int,
            hidden_dim: int = 256,
            hidden_layers: int = 2,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            layers: list[Any] = []
            in_dim = input_dim
            for _ in range(max(1, hidden_layers)):
                layers.append(nn.Linear(in_dim, hidden_dim))
                layers.append(nn.ReLU())
                if dropout > 0:
                    layers.append(nn.Dropout(dropout))
                in_dim = hidden_dim
            self.trunk = nn.Sequential(*layers)
            self.policy_head = nn.Linear(hidden_dim, action_dim)
            self.value_head = nn.Sequential(nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(), nn.Linear(hidden_dim // 2, 1), nn.Tanh())

        def forward(self, x):  # type: ignore[override]
            h = self.trunk(x)
            policy_logits = self.policy_head(h)
            value = self.value_head(h).squeeze(-1)
            return policy_logits, value

else:

    class PolicyValueNet:  # pragma: no cover - only used when torch missing
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "PyTorch is not installed. Install torch to use sim_harness RL training."
            )
