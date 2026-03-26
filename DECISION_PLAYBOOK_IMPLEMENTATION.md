# Decision Playbook Implementation — ARC-AGI-3

## Overview

Implementation of the **VETO → SCORING → PREPORUKA → AUDIT** decision framework from the Decision Playbook for ARC-AGI-3 action selection.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ThinkingReflexionAgent                    │
├─────────────────────────────────────────────────────────────┤
│  LLM (Planner/Critic) → Candidate Actions                   │
│         ↓                                                     │
│  ┌──────────────────────────────────────────────┐           │
│  │        Decision Engine                        │           │
│  │                                               │           │
│  │  1. VETO PHASE                                │           │
│  │     - Boundary violations (V1)                │           │
│  │     - Wall collisions (V2)                    │           │
│  │     - Repeated failures (V3)                  │           │
│  │     - Energy critical (V4)                    │           │
│  │     - Ignore rotator (V5)                     │           │
│  │     - Loop detection (V6)                     │           │
│  │                                               │           │
│  │  2. SCORING PHASE                             │           │
│  │     - Progress toward door (30%)              │           │
│  │     - Energy efficiency (25%)                 │           │
│  │     - Exploration value (20%)                 │           │
│  │     - Rotator proximity (15%)                 │           │
│  │     - Safety margin (10%)                     │           │
│  │                                               │           │
│  │  3. PREPORUKA PHASE                           │           │
│  │     - Clear winner (>20% gap)                 │           │
│  │     - Score-based selection                   │           │
│  │     - Single survivor auto-select             │           │
│  │                                               │           │
│  │  4. AUDIT PHASE                               │           │
│  │     - JSONL log with HMAC                     │           │
│  │     - Full decision trail                     │           │
│  └──────────────────────────────────────────────┘           │
│         ↓                                                     │
│  Final Action (GameAction.RESET/ACTION1-6)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Files Structure

```
ARC-AGI-3-Agents/
├── decision_engine/
│   ├── __init__.py              # Package exports
│   └── decision_engine.py       # Core DecisionEngine class
├── config/
│   ├── veto_criteria.json       # VETO rules configuration
│   └── scoring_metrics.json     # Scoring weights configuration
├── agents/
│   └── thinking_reflexion_agent.py  # Integrated with Decision Engine
└── logs/
    └── decision_audit.jsonl     # Audit trail (auto-generated)
```

---

## Configuration

### VETO Criteria (`config/veto_criteria.json`)

```json
{
  "veto_rules": [
    {
      "id": "V1",
      "name": "boundary_violation",
      "severity": "CRITICAL",
      "auto_veto": true
    },
    {
      "id": "V2",
      "name": "wall_collision", 
      "severity": "CRITICAL",
      "auto_veto": true
    },
    {
      "id": "V3",
      "name": "repeated_failure",
      "severity": "HIGH",
      "threshold": 3
    }
  ]
}
```

### Scoring Metrics (`config/scoring_metrics.json`)

```json
{
  "metrics": [
    {
      "name": "progress_toward_door",
      "weight": 0.30,
      "direction": "maximize"
    },
    {
      "name": "energy_efficiency",
      "weight": 0.25,
      "direction": "maximize"
    }
  ],
  "scoring_method": "weighted_sum",
  "min_score_threshold": 50.0
}
```

---

## Usage Example

```python
from decision_engine import DecisionEngine

# Initialize
engine = DecisionEngine(
    veto_config_path="config/veto_criteria.json",
    scoring_config_path="config/scoring_metrics.json",
    audit_log_path="logs/decision_audit.jsonl"
)

# Define candidate actions
candidates = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "RESET"]

# Extract game state
game_state = {
    "player_position": (32, 32),
    "energy": 15,
    "energy_pill_visible": True,
    "key_matches_door": False
}

# VETO PHASE
survivors, vetoed = engine.run_veto_checks(candidates, game_state)
# survivors: ["ACTION1", "ACTION3", "RESET"]
# vetoed: {"ACTION2": ["V2: wall_collision"]}

# SCORING PHASE
scores = engine.score_actions(survivors, game_state)
# scores: {"ACTION1": 72.5, "ACTION3": 65.3, "RESET": 30.0}

# PREPORUKA PHASE
recommended, reason = engine.make_recommendation(survivors, scores, vetoed)
# recommended: "ACTION1", reason: DecisionReason.SCORE_BASED

# AUDIT PHASE
engine.log_decision(
    scenario_id="ar25_42",
    context="LockSmith level 3",
    candidates=candidates,
    vetoed=vetoed,
    scores=scores,
    recommended=recommended,
    reason=reason
)
```

---

## Audit Log Format

Each decision is logged as a JSONL record with HMAC signature:

```json
{
  "scenario_id": "ar25_42",
  "timestamp": "2026-03-26T14:32:15.123456Z",
  "initiator": "thinking_reflexion_agent",
  "context": "LockSmith level 3",
  "entities_evaluated": ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "RESET"],
  "vetoed": {
    "ACTION2": ["V2: wall_collision"]
  },
  "scores": {
    "ACTION1": 72.5,
    "ACTION3": 65.3,
    "RESET": 30.0
  },
  "recommended": "ACTION1",
  "decision_reason": "score_based",
  "human_override": null,
  "hmac_signature": "a3f2b8c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
}
```

---

## Decision Reasons

| Reason | Description | When Used |
|--------|-------------|-----------|
| `clear_winner` | Best score >20% ahead of second | Dominant choice |
| `score_based` | Highest score wins | Multiple survivors |
| `single_survivor` | Only one action passed VETO | Auto-select |
| `default` | No survivors, use RESET | Emergency fallback |
| `human_override` | Human intervened | Manual override |

---

## VETO Severity Levels

| Severity | Consequence | Example |
|----------|-------------|---------|
| `CRITICAL` | Block action, log error | Boundary violation, wall collision |
| `HIGH` | Block action, log warning | Repeated failure, energy critical |
| `MEDIUM` | Allow with audit flag | Loop detection, ignore rotator |

---

## Integration with ThinkingReflexionAgent

The Decision Engine is called in `choose_action()`:

1. **LLM generates candidate** → Planner suggests action
2. **VETO filters** → Remove dangerous/invalid actions
3. **SCORING ranks** → Evaluate remaining actions
4. **PREPORUKA selects** → Choose best action
5. **AUDIT logs** → Record full decision trail
6. **Execute action** → Return GameAction

This creates a **hybrid LLM + Rule-based** decision system:
- LLM provides intuition and strategic thinking
- Decision Engine provides safety checks and accountability

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Safety** | VETO prevents dangerous actions (walls, boundaries) |
| **Accountability** | Full audit trail with HMAC signatures |
| **Transparency** | Clear reasons for each decision |
| **Flexibility** | Configurable weights and veto rules |
| **Debuggability** | Easy to trace why action was chosen/blocked |

---

## Testing

```bash
# Run unit tests
pytest tests/test_decision_engine.py

# Test VETO checks
python -m pytest tests/test_veto.py -v

# Test scoring
python -m pytest tests/test_scoring.py -v

# Integration test
uv run parallel_runner.py --agent=thinkingreflexionagent \
  --games=ar25 --tags=decision_engine_test
```

---

## Future Enhancements

1. **Dynamic Weight Adjustment** — Learn optimal weights from game outcomes
2. **Human-in-the-Loop** — Allow manual override via API
3. **Multi-Agent Consensus** — Vote across multiple agents
4. **Real-time Dashboard** — Visualize decision audit trail
5. **Reinforcement Learning** — Optimize scoring weights via RL

---

## References

- Decision Playbook: `/home/kizabgd/Desktop/PRojekat-Orkestar/decision playbook.md`
- ARC-AGI-3 Docs: https://three.arcprize.org/docs
- LangGraph: https://langchain-ai.github.io/langgraph/
