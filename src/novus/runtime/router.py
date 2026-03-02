"""Dual-model routing for cost/performance-aware execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelRouteDecision:
    model: str
    tier: str
    reason: str


class RuntimeModelRouter:
    """Simple harness-level router for heavy/light model selection."""

    def __init__(self, heavy_model: str = "gpt-4", light_model: str = "gpt-4o-mini"):
        self.heavy_model = heavy_model
        self.light_model = light_model

    def select(self, task_type: str, complexity_hint: str = "medium") -> ModelRouteDecision:
        hard_types = {"plan", "debug", "edit", "architect", "reason"}
        if task_type in hard_types or complexity_hint == "high":
            return ModelRouteDecision(
                model=self.heavy_model,
                tier="heavy",
                reason=f"{task_type} requires deeper reasoning",
            )

        return ModelRouteDecision(
            model=self.light_model,
            tier="light",
            reason=f"{task_type} is routinized",
        )
