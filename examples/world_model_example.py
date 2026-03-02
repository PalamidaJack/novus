#!/usr/bin/env python3
"""
Example: World Model Planning

Demonstrates using the world model for counterfactual planning.
"""

import asyncio
import json
from novus.world_model.engine import WorldModel, WorldModelPlanner


async def world_model_example():
    """World model planning example."""
    print("=" * 60)
    print("NOVUS World Model Example")
    print("=" * 60)
    
    # Initialize world model
    model = WorldModel()
    planner = WorldModelPlanner(model)
    
    print("\n--- Example 1: Predicting Action Outcomes ---")
    
    # Define initial state
    initial_state = {
        "knowledge": 0.0,
        "computed": 0.0,
        "energy": 1.0,
        "confidence": 0.5
    }
    
    # Define action sequence
    actions = [
        {"type": "search", "description": "Research topic"},
        {"type": "reasoning", "description": "Analyze findings"},
        {"type": "code_execution", "description": "Run simulation"}
    ]
    
    # Predict outcomes
    prediction = await model.predict(
        initial_state=initial_state,
        actions=actions,
        num_samples=1
    )
    
    print(f"Initial state: {json.dumps(initial_state, indent=2)}")
    print(f"\nActions:")
    for i, action in enumerate(actions, 1):
        print(f"  {i}. {action['description']} ({action['type']})")
    
    print(f"\nPredicted final state:")
    if prediction.predicted_states:
        print(json.dumps(prediction.predicted_states[-1], indent=2))
    
    print(f"\nPrediction confidence intervals:")
    for i, conf in enumerate(prediction.confidence_intervals):
        print(f"  Step {i}: [{conf['lower']:.2f}, {conf['upper']:.2f}]")
    
    print(f"\nPrediction time: {prediction.prediction_time_ms:.2f}ms")
    
    # Example 2: Counterfactual reasoning
    print("\n--- Example 2: Counterfactual Analysis ---")
    
    actual_actions = [
        {"type": "search", "description": "Search approach A"},
        {"type": "reasoning", "description": "Analyze A"}
    ]
    
    hypothetical_actions = [
        {"type": "search", "description": "Search approach B"},
        {"type": "reasoning", "description": "Analyze B"}
    ]
    
    counterfactual = await model.simulate_counterfactual(
        initial_state=initial_state,
        actual_actions=actual_actions,
        hypothetical_actions=hypothetical_actions,
        num_samples=50
    )
    
    print("Comparing two approaches...")
    print(f"\nActual outcome: {json.dumps(counterfactual['actual_outcome'], indent=2)}")
    print(f"\nHypothetical outcome: {json.dumps(counterfactual['hypothetical_outcome'], indent=2)}")
    
    if counterfactual['divergence_step'] is not None:
        print(f"\nApproaches diverged at step: {counterfactual['divergence_step']}")
    else:
        print("\nApproaches converged to similar outcomes")
    
    # Example 3: Automated planning
    print("\n--- Example 3: Automated Planning ---")
    
    goal_state = {
        "knowledge": 0.8,
        "computed": 0.5,
        "confidence": 0.9
    }
    
    plan = await planner.plan(
        goal_state=goal_state,
        initial_state=initial_state,
        max_plan_length=5
    )
    
    print(f"Goal state: {json.dumps(goal_state, indent=2)}")
    print(f"\nBest plan (score: {plan['best_score']:.2f}):")
    for i, action in enumerate(plan['best_plan'], 1):
        print(f"  {i}. {action.get('type', 'unknown')}")
    
    if plan['alternatives']:
        print(f"\nTop alternative plans:")
        for i, alt in enumerate(plan['alternatives'][:3], 1):
            print(f"  {i}. Score: {alt['score']:.2f} (confidence: {alt['confidence']:.2f})")
    
    # World model stats
    print("\n--- World Model Statistics ---")
    stats = model.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(world_model_example())
