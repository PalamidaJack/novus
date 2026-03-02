"""Runtime policy engine for tool risk scoring and enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class PolicyDecision:
    allowed: bool
    action: str  # allow, block, escalate
    risk: str
    reason: str


class RuntimePolicyEngine:
    """Risk-tier tool policy with lightweight auto-approval semantics."""

    def __init__(
        self,
        auto_approve_low_risk: bool = True,
        block_high_risk_without_approval: bool = True,
        custom_risk_map: Dict[str, str] | None = None,
    ):
        self.auto_approve_low_risk = auto_approve_low_risk
        self.block_high_risk_without_approval = block_high_risk_without_approval
        self.risk_map = {
            "search_web": "low",
            "subagent_scan": "medium",
            "execute_code": "high",
        }
        if custom_risk_map:
            self.risk_map.update(custom_risk_map)

    def evaluate(self, tool: str, args: Dict[str, Any]) -> PolicyDecision:
        risk = self.risk_map.get(tool, "medium")

        if risk == "low" and self.auto_approve_low_risk:
            return PolicyDecision(True, "allow", risk, "low-risk auto-approved")

        if risk in {"high", "critical"} and self.block_high_risk_without_approval:
            return PolicyDecision(
                False,
                "escalate",
                risk,
                "high-risk action requires approval",
            )

        return PolicyDecision(True, "allow", risk, "allowed by policy")
