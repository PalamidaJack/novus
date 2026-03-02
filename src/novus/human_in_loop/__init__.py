"""
Human-in-the-loop support for NOVUS.

Provides approval checkpoints, intervention capabilities, and oversight
for critical agent actions.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Callable, Dict, Any, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import structlog

logger = structlog.get_logger()


class ApprovalStatus(str, Enum):
    """Status of human approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"
    AUTO_REJECTED = "auto_rejected"


class ActionCategory(str, Enum):
    """Categories of actions requiring approval."""
    CODE_EXECUTION = "code_execution"
    FILE_WRITE = "file_write"
    NETWORK_CALL = "network_call"
    DATABASE_WRITE = "database_write"
    COST_OVER_THRESHOLD = "cost_over_threshold"
    EXTERNAL_API = "external_api"
    DESTRUCTIVE_OPERATION = "destructive_operation"
    HIGH_RISK = "high_risk"
    CUSTOM = "custom"


@dataclass
class ActionRequest:
    """Request for human approval."""
    id: str
    agent_id: str
    agent_name: str
    category: ActionCategory
    action_description: str
    action_details: Dict[str, Any]
    timestamp: datetime
    timeout_seconds: int = 300
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Risk assessment
    risk_level: str = "medium"  # low, medium, high, critical
    estimated_cost: Optional[float] = None
    affected_resources: List[str] = field(default_factory=list)


@dataclass
class ApprovalDecision:
    """Human decision on an action."""
    request_id: str
    status: ApprovalStatus
    decided_by: Optional[str] = None  # User ID or "auto"
    decision_timestamp: datetime = field(default_factory=datetime.utcnow)
    reason: Optional[str] = None
    conditions: List[str] = field(default_factory=list)  # "run_in_dry_mode", etc.


class HumanApprovalManager:
    """
    Manages human approval workflows for agent actions.
    
    Features:
    - Configurable approval rules by category
    - Timeout handling
    - Audit logging
    - Batch approvals
    - Auto-approval policies
    """
    
    def __init__(self):
        self.pending_requests: Dict[str, ActionRequest] = {}
        self.decisions: Dict[str, ApprovalDecision] = {}
        self.approval_handlers: List[Callable[[ActionRequest], None]] = []
        
        # Auto-approval policies
        self.auto_approve_policies: List[Callable[[ActionRequest], bool]] = []
        self.auto_reject_policies: List[Callable[[ActionRequest], bool]] = []
        
        # Default timeouts by category
        self.default_timeouts: Dict[ActionCategory, int] = {
            ActionCategory.CODE_EXECUTION: 300,
            ActionCategory.FILE_WRITE: 60,
            ActionCategory.NETWORK_CALL: 30,
            ActionCategory.DATABASE_WRITE: 120,
            ActionCategory.COST_OVER_THRESHOLD: 300,
            ActionCategory.EXTERNAL_API: 60,
            ActionCategory.DESTRUCTIVE_OPERATION: 600,
            ActionCategory.HIGH_RISK: 600,
            ActionCategory.CUSTOM: 300,
        }
        
        logger.info("human_approval_manager_initialized")
    
    async def request_approval(
        self,
        agent_id: str,
        agent_name: str,
        category: ActionCategory,
        description: str,
        details: Dict[str, Any],
        timeout_seconds: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        risk_level: str = "medium",
        estimated_cost: Optional[float] = None
    ) -> ApprovalDecision:
        """
        Request human approval for an action.
        
        Returns when approval is granted, rejected, or timeout expires.
        """
        import uuid
        
        request_id = str(uuid.uuid4())
        timeout = timeout_seconds or self.default_timeouts.get(category, 300)
        
        request = ActionRequest(
            id=request_id,
            agent_id=agent_id,
            agent_name=agent_name,
            category=category,
            action_description=description,
            action_details=details,
            timestamp=datetime.utcnow(),
            timeout_seconds=timeout,
            context=context or {},
            risk_level=risk_level,
            estimated_cost=estimated_cost
        )
        
        # Check auto-approval policies
        for policy in self.auto_approve_policies:
            if policy(request):
                decision = ApprovalDecision(
                    request_id=request_id,
                    status=ApprovalStatus.AUTO_APPROVED,
                    decided_by="auto",
                    reason="Matched auto-approval policy"
                )
                self.decisions[request_id] = decision
                logger.info("action_auto_approved", request_id=request_id, category=category.value)
                return decision
        
        # Check auto-reject policies
        for policy in self.auto_reject_policies:
            if policy(request):
                decision = ApprovalDecision(
                    request_id=request_id,
                    status=ApprovalStatus.AUTO_REJECTED,
                    decided_by="auto",
                    reason="Matched auto-reject policy"
                )
                self.decisions[request_id] = decision
                logger.warning("action_auto_rejected", request_id=request_id, category=category.value)
                return decision
        
        # Store pending request
        self.pending_requests[request_id] = request
        
        # Notify handlers (UI, webhooks, etc.)
        for handler in self.approval_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(request))
                else:
                    handler(request)
            except Exception as e:
                logger.error("approval_handler_error", error=str(e))
        
        logger.info(
            "approval_requested",
            request_id=request_id,
            agent=agent_name,
            category=category.value,
            timeout=timeout
        )
        
        # Wait for decision or timeout
        return await self._wait_for_decision(request_id, timeout)
    
    async def _wait_for_decision(
        self,
        request_id: str,
        timeout_seconds: int
    ) -> ApprovalDecision:
        """Wait for human decision or timeout."""
        start_time = datetime.utcnow()
        
        while True:
            # Check if decision made
            if request_id in self.decisions:
                decision = self.decisions[request_id]
                del self.pending_requests[request_id]
                return decision
            
            # Check timeout
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                decision = ApprovalDecision(
                    request_id=request_id,
                    status=ApprovalStatus.EXPIRED,
                    reason=f"Timeout after {timeout_seconds} seconds"
                )
                self.decisions[request_id] = decision
                del self.pending_requests[request_id]
                logger.warning("approval_timeout", request_id=request_id)
                return decision
            
            await asyncio.sleep(0.1)
    
    def approve(
        self,
        request_id: str,
        user_id: str,
        reason: Optional[str] = None,
        conditions: Optional[List[str]] = None
    ) -> bool:
        """Approve a pending request."""
        if request_id not in self.pending_requests:
            return False
        
        decision = ApprovalDecision(
            request_id=request_id,
            status=ApprovalStatus.APPROVED,
            decided_by=user_id,
            reason=reason,
            conditions=conditions or []
        )
        self.decisions[request_id] = decision
        
        logger.info("action_approved", request_id=request_id, user=user_id)
        return True
    
    def reject(
        self,
        request_id: str,
        user_id: str,
        reason: str
    ) -> bool:
        """Reject a pending request."""
        if request_id not in self.pending_requests:
            return False
        
        decision = ApprovalDecision(
            request_id=request_id,
            status=ApprovalStatus.REJECTED,
            decided_by=user_id,
            reason=reason
        )
        self.decisions[request_id] = decision
        
        logger.info("action_rejected", request_id=request_id, user=user_id, reason=reason)
        return True
    
    def add_approval_handler(self, handler: Callable[[ActionRequest], None]) -> None:
        """Add a handler for new approval requests."""
        self.approval_handlers.append(handler)
    
    def add_auto_approve_policy(
        self,
        policy: Callable[[ActionRequest], bool]
    ) -> None:
        """Add an auto-approval policy."""
        self.auto_approve_policies.append(policy)
    
    def add_auto_reject_policy(
        self,
        policy: Callable[[ActionRequest], bool]
    ) -> None:
        """Add an auto-reject policy."""
        self.auto_reject_policies.append(policy)
    
    def get_pending_requests(self) -> List[ActionRequest]:
        """Get all pending approval requests."""
        return list(self.pending_requests.values())
    
    def get_request_history(
        self,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[ApprovalDecision]:
        """Get historical decisions."""
        decisions = list(self.decisions.values())
        
        if agent_id:
            # Filter by agent (need to look up request)
            decisions = [
                d for d in decisions
                if d.request_id in self.pending_requests or True  # Simplified
            ]
        
        # Sort by timestamp descending
        decisions.sort(key=lambda d: d.decision_timestamp, reverse=True)
        return decisions[:limit]


class ApprovalRequired:
    """
    Decorator for methods requiring human approval.
    
    Usage:
        class MyAgent(Agent):
            @ApprovalRequired(ActionCategory.CODE_EXECUTION)
            async def run_code(self, code: str):
                return execute(code)
    """
    
    def __init__(
        self,
        category: ActionCategory,
        description_template: Optional[str] = None,
        timeout_seconds: Optional[int] = None
    ):
        self.category = category
        self.description_template = description_template
        self.timeout_seconds = timeout_seconds
    
    def __call__(self, func):
        async def wrapper(agent, *args, **kwargs):
            # Get or create approval manager
            if not hasattr(agent, '_approval_manager'):
                agent._approval_manager = HumanApprovalManager()
            
            manager = agent._approval_manager
            
            # Build description
            if self.description_template:
                description = self.description_template.format(*args, **kwargs)
            else:
                description = f"{func.__name__}({', '.join(map(str, args))})"
            
            # Request approval
            decision = await manager.request_approval(
                agent_id=agent.id,
                agent_name=agent.name,
                category=self.category,
                description=description,
                details={
                    "function": func.__name__,
                    "args": str(args),
                    "kwargs": str(kwargs)
                },
                timeout_seconds=self.timeout_seconds
            )
            
            if decision.status not in [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED]:
                raise PermissionError(
                    f"Action not approved: {decision.reason}"
                )
            
            # Execute the function
            return await func(agent, *args, **kwargs)
        
        return wrapper


# FastAPI endpoints for approval UI
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

approval_router = APIRouter(prefix="/approvals")

# Global manager instance
_approval_manager: Optional[HumanApprovalManager] = None

def get_approval_manager() -> HumanApprovalManager:
    """Get or create approval manager."""
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = HumanApprovalManager()
    return _approval_manager


class ApproveRequest(BaseModel):
    user_id: str
    reason: Optional[str] = None
    conditions: Optional[List[str]] = None


class RejectRequest(BaseModel):
    user_id: str
    reason: str


@approval_router.get("/pending")
async def get_pending_approvals():
    """Get all pending approval requests."""
    manager = get_approval_manager()
    requests = manager.get_pending_requests()
    
    return [
        {
            "id": req.id,
            "agent_id": req.agent_id,
            "agent_name": req.agent_name,
            "category": req.category.value,
            "description": req.action_description,
            "risk_level": req.risk_level,
            "estimated_cost": req.estimated_cost,
            "timestamp": req.timestamp.isoformat(),
            "timeout_seconds": req.timeout_seconds
        }
        for req in requests
    ]


@approval_router.post("/{request_id}/approve")
async def approve_request(request_id: str, body: ApproveRequest):
    """Approve a pending request."""
    manager = get_approval_manager()
    success = manager.approve(
        request_id=request_id,
        user_id=body.user_id,
        reason=body.reason,
        conditions=body.conditions
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return {"status": "approved"}


@approval_router.post("/{request_id}/reject")
async def reject_request(request_id: str, body: RejectRequest):
    """Reject a pending request."""
    manager = get_approval_manager()
    success = manager.reject(
        request_id=request_id,
        user_id=body.user_id,
        reason=body.reason
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return {"status": "rejected"}


@approval_router.get("/history")
async def get_approval_history(agent_id: Optional[str] = None, limit: int = 100):
    """Get approval history."""
    manager = get_approval_manager()
    decisions = manager.get_request_history(agent_id=agent_id, limit=limit)
    
    return [
        {
            "request_id": d.request_id,
            "status": d.status.value,
            "decided_by": d.decided_by,
            "timestamp": d.decision_timestamp.isoformat(),
            "reason": d.reason
        }
        for d in decisions
    ]
