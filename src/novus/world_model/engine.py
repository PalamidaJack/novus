"""
World Model Engine for NOVUS.

Implements JEPA-inspired world modeling for internal simulation
and counterfactual reasoning.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import structlog
import numpy as np

from novus.core.models import WorldModelPrediction

logger = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorldState:
    """Represents a state in the world model."""
    state_id: str
    features: Dict[str, Any]
    timestamp: datetime
    agent_id: Optional[str] = None
    
    def to_vector(self) -> List[float]:
        """Convert state to feature vector."""
        # Simple encoding - in production would use learned embeddings
        vec = []
        for key in sorted(self.features.keys()):
            val = self.features[key]
            if isinstance(val, bool):
                vec.append(1.0 if val else 0.0)
            elif isinstance(val, (int, float)):
                vec.append(float(val))
            elif isinstance(val, str):
                vec.append(hash(val) % 1000 / 1000.0)
            else:
                vec.append(0.0)
        return vec


@dataclass
class Action:
    """Represents an action in the world model."""
    action_id: str
    action_type: str  # "code", "search", "api_call", "reasoning", etc.
    parameters: Dict[str, Any]
    preconditions: Dict[str, Any] = None
    effects: Dict[str, Any] = None
    
    def to_vector(self) -> List[float]:
        """Convert action to feature vector."""
        vec = [
            hash(self.action_type) % 1000 / 1000.0,
            len(json.dumps(self.parameters)) / 10000.0,
        ]
        return vec


class WorldModel:
    """
    World Model for NOVUS.
    
    Implements:
    - State representation learning
    - Action effect prediction (physics, causality)
    - Counterfactual reasoning
    - Mental simulation
    
    Based on JEPA (Joint Embedding Predictive Architecture) principles.
    """
    
    def __init__(
        self,
        state_dim: int = 512,
        action_dim: int = 128,
        hidden_dim: int = 256,
        num_prediction_steps: int = 10
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.num_prediction_steps = num_prediction_steps
        
        # State encoder/decoder
        self.state_encoder = None  # Would be a neural network
        self.state_decoder = None
        
        # Dynamics model: next_state = f(state, action)
        self.dynamics_model = None  # Would be trained
        
        # Reward/cost model
        self.reward_model = None
        
        # State memory
        self.state_history: List[WorldState] = []
        self.max_history = 10000
        
        # Action library
        self.action_library: Dict[str, Action] = {}
        
        # Physics knowledge (hardcoded rules)
        self.physics_rules: List[Dict[str, Any]] = []
        
        logger.info(
            "world_model_initialized",
            state_dim=state_dim,
            action_dim=action_dim
        )
    
    async def predict(
        self,
        initial_state: Dict[str, Any],
        actions: List[Dict[str, Any]],
        num_samples: int = 1
    ) -> WorldModelPrediction:
        """
        Predict outcomes of a sequence of actions from initial state.
        
        This is the core "mental simulation" capability.
        """
        start_time = _utcnow()
        
        # Convert to internal representation
        current_state = WorldState(
            state_id="init",
            features=initial_state,
            timestamp=_utcnow()
        )
        
        predicted_states = []
        confidence_intervals = []
        
        for step, action_dict in enumerate(actions):
            # Get action from library or create
            action = self._get_action(action_dict)
            
            # Apply physics rules first
            current_state = self._apply_physics(current_state, action)
            
            # Predict next state using dynamics model
            next_state = await self._predict_next_state(current_state, action)
            
            predicted_states.append(next_state.features)
            
            # Estimate uncertainty
            confidence = self._estimate_confidence(step, len(actions))
            confidence_intervals.append({"lower": confidence[0], "upper": confidence[1]})
            
            current_state = next_state
        
        prediction_time = (_utcnow() - start_time).total_seconds() * 1000
        
        return WorldModelPrediction(
            initial_state=initial_state,
            actions=actions,
            predicted_states=predicted_states,
            confidence_intervals=confidence_intervals,
            model_version="0.1.0",
            prediction_time_ms=prediction_time
        )
    
    async def _predict_next_state(
        self,
        state: WorldState,
        action: Action
    ) -> WorldState:
        """
        Predict next state given current state and action.
        
        In production, this would use a learned dynamics model.
        For now, uses rule-based prediction with noise.
        """
        # Copy current features
        next_features = dict(state.features)
        
        # Apply action effects (if known)
        if action.effects:
            for key, value in action.effects.items():
                next_features[key] = value
        
        # Add some "uncertainty" for realistic simulation
        noise = {k: np.random.normal(0, 0.1) for k in next_features.keys()}
        
        # Simple state transition
        action_type = action.action_type
        if action_type == "search":
            next_features["knowledge"] = next_features.get("knowledge", 0) + 0.5
        elif action_type == "code_execution":
            next_features["computed"] = next_features.get("computed", 0) + 1
        elif action_type == "reasoning":
            next_features["reasoning_depth"] = next_features.get("reasoning_depth", 0) + 1
        
        # Clamp values
        for key in next_features:
            if isinstance(next_features[key], (int, float)):
                next_features[key] = max(0, min(1, next_features[key] + noise.get(key, 0)))
        
        return WorldState(
            state_id=f"step_{len(self.state_history)}",
            features=next_features,
            timestamp=_utcnow()
        )
    
    def _apply_physics(self, state: WorldState, action: Action) -> WorldState:
        """
        Apply hard physics constraints to state transitions.
        """
        features = dict(state.features)
        
        # Apply known physics rules
        for rule in self.physics_rules:
            # Check if rule applies
            if self._rule_applies(rule, state, action):
                # Apply constraint
                features = self._apply_rule(rule, features)
        
        return WorldState(
            state_id=state.state_id,
            features=features,
            timestamp=state.timestamp
        )
    
    def _rule_applies(self, rule: Dict, state: WorldState, action: Action) -> bool:
        """Check if a physics rule applies."""
        conditions = rule.get("conditions", {})
        for key, expected in conditions.items():
            if state.features.get(key) != expected:
                return False
        return True
    
    def _apply_rule(self, rule: Dict, features: Dict) -> Dict:
        """Apply a physics rule."""
        effects = rule.get("effects", {})
        return {**features, **effects}
    
    def _estimate_confidence(self, step: int, total_steps: int) -> Tuple[float, float]:
        """Estimate prediction confidence intervals."""
        # Confidence decreases with horizon
        base_confidence = 1.0 - (step / total_steps) * 0.3
        return (base_confidence - 0.1, base_confidence + 0.05)
    
    def _get_action(self, action_dict: Dict) -> Action:
        """Get or create action from dictionary."""
        action_id = action_dict.get("id", json.dumps(action_dict, sort_keys=True))
        
        if action_id not in self.action_library:
            self.action_library[action_id] = Action(
                action_id=action_id,
                action_type=action_dict.get("type", "unknown"),
                parameters=action_dict.get("parameters", {}),
                preconditions=action_dict.get("preconditions"),
                effects=action_dict.get("effects")
            )
        
        return self.action_library[action_id]
    
    async def simulate_counterfactual(
        self,
        initial_state: Dict[str, Any],
        actual_actions: List[Dict[str, Any]],
        hypothetical_actions: List[Dict[str, Any]],
        num_samples: int = 100
    ) -> Dict[str, Any]:
        """
        Run counterfactual simulations.
        
        Compare what would have happened vs what actually happened
        if different actions were taken.
        """
        # Run actual sequence
        actual = await self.predict(initial_state, actual_actions)
        
        # Run hypothetical sequence
        hypothetical = await self.predict(initial_state, hypothetical_actions)
        
        # Calculate differences
        differences = []
        for i in range(len(actual.predicted_states)):
            actual_state = actual.predicted_states[i]
            hypoth_state = hypothetical.predicted_states[i]
            
            diff = {
                "step": i,
                "differences": {
                    k: actual_state.get(k, 0) - hypoth_state.get(k, 0)
                    for k in set(actual_state.keys()) | set(hypoth_state.keys())
                }
            }
            differences.append(diff)
        
        return {
            "actual_outcome": actual.predicted_states[-1] if actual.predicted_states else {},
            "hypothetical_outcome": hypothetical.predicted_states[-1] if hypothetical.predicted_states else {},
            "differences": differences,
            "divergence_step": self._find_divergence_point(differences)
        }
    
    def _find_divergence_point(self, differences: List[Dict]) -> Optional[int]:
        """Find first step where states diverge significantly."""
        threshold = 0.2
        for diff in differences:
            vals = diff.get("differences", {}).values()
            if any(abs(v) > threshold for v in vals if isinstance(v, (int, float))):
                return diff["step"]
        return None
    
    async def learn_dynamics(
        self,
        state_action_pairs: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]
    ) -> None:
        """
        Learn dynamics model from experience.
        
        state_action_pairs: [(state, action, resulting_state), ...]
        
        In production, would train a neural network.
        """
        logger.info("learning_dynamics", num_examples=len(state_action_pairs))
        
        # Placeholder for actual learning
        # Would update self.dynamics_model
        
        self.state_history.extend([
            WorldState(
                state_id=f"learn_{i}",
                features=state,
                timestamp=_utcnow()
            )
            for i, (state, _, _) in enumerate(state_action_pairs)
        ])
        
        # Trim history
        if len(self.state_history) > self.max_history:
            self.state_history = self.state_history[-self.max_history:]
    
    def add_physics_rule(
        self,
        conditions: Dict[str, Any],
        effects: Dict[str, Any],
        description: str = ""
    ) -> None:
        """Add a hard physics constraint rule."""
        rule = {
            "conditions": conditions,
            "effects": effects,
            "description": description
        }
        self.physics_rules.append(rule)
        logger.info("physics_rule_added", description=description[:50])
    
    def get_stats(self) -> Dict[str, Any]:
        """Get world model statistics."""
        return {
            "state_dim": self.state_dim,
            "action_dim": self.action_dim,
            "history_size": len(self.state_history),
            "action_library_size": len(self.action_library),
            "physics_rules": len(self.physics_rules),
        }


class WorldModelPlanner:
    """
    Planner that uses the world model for decision making.
    
    Generates candidate plans and evaluates them through
    mental simulation before execution.
    """
    
    def __init__(self, world_model: WorldModel):
        self.world_model = world_model
    
    async def plan(
        self,
        goal_state: Dict[str, Any],
        initial_state: Dict[str, Any],
        max_plan_length: int = 10,
        num_candidates: int = 20
    ) -> Dict[str, Any]:
        """
        Generate and evaluate plans to reach goal state.
        
        Returns best plan with expected outcomes.
        """
        # Generate candidate action sequences
        candidates = self._generate_candidates(
            initial_state,
            max_plan_length,
            num_candidates
        )
        
        # Evaluate each candidate
        evaluated = []
        for candidate in candidates:
            prediction = await self.world_model.predict(initial_state, candidate)
            
            # Score the plan
            score = self._evaluate_plan(
                prediction.predicted_states[-1] if prediction.predicted_states else initial_state,
                goal_state,
                prediction.confidence_intervals
            )
            
            evaluated.append({
                "actions": candidate,
                "predicted_outcome": prediction.predicted_states[-1] if prediction.predicted_states else None,
                "score": score,
                "confidence": sum(
                    (c.get("lower", 0) + c.get("upper", 0)) / 2
                    for c in prediction.confidence_intervals
                ) / len(prediction.confidence_intervals) if prediction.confidence_intervals else 0
            })
        
        # Sort by score
        evaluated.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "best_plan": evaluated[0]["actions"] if evaluated else [],
            "best_score": evaluated[0]["score"] if evaluated else 0,
            "alternatives": evaluated[:5],
            "goal_state": goal_state,
            "initial_state": initial_state
        }
    
    def _generate_candidates(
        self,
        initial_state: Dict[str, Any],
        max_length: int,
        num_candidates: int
    ) -> List[List[Dict[str, Any]]]:
        """Generate candidate action sequences."""
        candidates = []
        
        # Simple random generation for now
        # In production would use more sophisticated methods
        action_types = [
            {"type": "search", "effects": {"knowledge": 0.2}},
            {"type": "code_execution", "effects": {"computed": 0.3}},
            {"type": "reasoning", "effects": {"reasoning_depth": 0.1}},
            {"type": "retrieve_memory", "effects": {"context": 0.2}},
        ]
        
        for _ in range(num_candidates):
            length = np.random.randint(1, max_length + 1)
            sequence = [
                {**action_types[i % len(action_types)], "id": f"a_{i}_{j}"}
                for j in range(length)
                for i in range(len(action_types))
            ][:length]
            candidates.append(sequence)
        
        return candidates
    
    def _evaluate_plan(
        self,
        final_state: Dict[str, Any],
        goal_state: Dict[str, Any],
        confidence_intervals: List[Dict]
    ) -> float:
        """Evaluate how well a plan achieves the goal."""
        score = 0.0
        
        for key, target_value in goal_state.items():
            actual_value = final_state.get(key, 0)
            
            if isinstance(target_value, bool):
                score += 1.0 if actual_value == target_value else 0.0
            elif isinstance(target_value, (int, float)):
                diff = abs(actual_value - target_value)
                score += max(0, 1.0 - diff)
        
        # Normalize by number of goals
        if goal_state:
            score /= len(goal_state)
        
        return score
