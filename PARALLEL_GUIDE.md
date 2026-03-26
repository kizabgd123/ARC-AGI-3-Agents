# Parallel Agent Runner Guide

## Overview

The `parallel_runner.py` script provides enhanced parallelization options for running ARC-AGI-3 agents across multiple games.

## Features

✅ **Same agent on multiple games** - Original Swarm behavior  
✅ **Different agents on different games** - Custom assignments  
✅ **Configurable concurrency** - Limit max parallel threads  
✅ **Batch processing** - Split runs into multiple scorecards  
✅ **Independent parallel games** - Fastest option for testing  

---

## Quick Start

### Basic Usage - Same Agent on Multiple Games

```bash
cd ARC-AGI-3-Agents

# Run LLM agent on 3 games simultaneously
uv run parallel_runner.py --agent=llm --games=ar25,ls20,bp35

# Run random agent on 5 games
uv run parallel_runner.py --agent=random --games=ar25,ls20,bp35,cd82,dc22
```

### Custom Assignments - Different Agents per Game

```bash
# Assign specific agents to specific games
uv run parallel_runner.py \
  --assign llm:ar25 \
  --assign fastllm:ls20 \
  --assign random:bp35 \
  --assign reasoningllm:cd82

# Mix and match
uv run parallel_runner.py \
  --assign llm:ar25 \
  --assign llm:ls20 \
  --assign fastllm:bp35
```

### Limit Concurrency

```bash
# Run 10 games but only 3 at a time
uv run parallel_runner.py \
  --agent=llm \
  --games=ar25,ls20,bp35,cd82,dc22,ft09,g50t,ka59,lf52,lp85 \
  --max-concurrent=3
```

### Batch Processing (Multiple Scorecards)

```bash
# Split 6 games into batches of 2 (3 scorecards total)
uv run parallel_runner.py \
  --agent=llm \
  --games=ar25,ls20,bp35,cd82,dc22,ft09 \
  --batch-size=2
```

### Parallel Games Mode (Fastest)

Each game runs completely independently with its own scorecard:

```bash
# Run 5 games in parallel (max speed)
uv run parallel_runner.py \
  --agent=llm \
  --games=ar25,ls20,bp35,cd82,dc22 \
  --parallel-games \
  --max-concurrent=5
```

---

## Command Reference

### Required Arguments (choose one mode)

**Mode 1: Single agent on multiple games**
```bash
--agent=AGENT_NAME --games=game1,game2,game3
```

**Mode 2: Custom assignments**
```bash
--assign agent1:game1 --assign agent2:game2 --assign agent3:game3
```

### Optional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--max-concurrent N` | Max parallel threads/games | All at once |
| `--batch-size N` | Split into batches of N | Single batch |
| `--parallel-games` | Independent games mode | Off |
| `--tags tag1,tag2` | Tags for scorecards | None |
| `--debug` | Enable debug logging | Off |

---

## Available Agents

```
random              - Random baseline
llm                 - LLM-based reasoning
fastllm             - Optimized LLM
reasoningllm        - Chain-of-thought LLM
guidedllm           - Structured LLM
multimodalllm       - Vision + text LLM
smolcodingagent     - SmolAgents code-based
smolvisionagent     - SmolAgents vision-based
langgraphfunc       - LangGraph functional
langgraphtextonly   - LangGraph text-only
langgraphthinking   - LangGraph with reasoning
langgraphrandom     - LangGraph random
```

## Available Games (25 total)

```
ar25  bp35  cd82  cn04  dc22  ft09  g50t  ka59  lf52
lp85  ls20  m0r0  r11l  re86  s5i5  sb26  sc25  sk48
sp80  su15  tn36  tr87  tu93  vc33  wa30
```

---

## Output

### Console Output

```
2026-03-26 10:30:15 | INFO | Created 5 assignments:
2026-03-26 10:30:15 | INFO |   - llm → ar25
2026-03-26 10:30:15 | INFO |   - llm → ls20
2026-03-26 10:30:15 | INFO |   - llm → bp35
2026-03-26 10:30:15 | INFO |   - llm → cd82
2026-03-26 10:30:15 | INFO |   - llm → dc22
2026-03-26 10:30:15 | INFO | Opening scorecard with tags: ['experiment']
2026-03-26 10:30:16 | INFO | Scorecard opened: abc123
2026-03-26 10:30:16 | INFO | Starting 5 agent threads...
...
2026-03-26 10:32:45 | INFO | All agent threads completed
```

### Summary

```
============================================================
PARALLEL RUN SUMMARY
============================================================
Total batches: 1
Successful: 1
Failed: 0
Total duration: 149.23s (2.49 min)
✓ Batch 1: ar25(llm), ls20(llm), bp35(llm), cd82(llm), dc22(llm) - 149.23s
============================================================
```

### Log Files

- **parallel_logs.log** - Full detailed logs
- **logs.log** - Standard swarm logs (if using main.py)

---

## Comparison: main.py vs parallel_runner.py

| Feature | main.py | parallel_runner.py |
|---------|---------|-------------------|
| Single agent + multiple games | ✅ | ✅ |
| Different agents per game | ❌ | ✅ |
| Limit concurrency | ❌ | ✅ |
| Batch processing | ❌ | ✅ |
| Independent parallel games | ❌ | ✅ |
| Custom tags | ✅ | ✅ |
| Playback support | ✅ | ✅ |

---

## Tips

### 1. Fast Testing
Use `--parallel-games` for fastest iteration:
```bash
uv run parallel_runner.py --agent=random --games=ar25,ls20,bp35 --parallel-games
```

### 2. Resource Management
Limit concurrency to avoid API rate limits:
```bash
uv run parallel_runner.py --agent=llm --games=ar25,ls20,bp35,cd82,dc22 --max-concurrent=2
```

### 3. A/B Testing
Compare different agents on same game:
```bash
uv run parallel_runner.py \
  --assign llm:ar25 \
  --assign fastllm:ar25 \
  --assign reasoningllm:ar25 \
  --parallel-games
```

### 4. Tagging for Analysis
```bash
uv run parallel_runner.py \
  --agent=llm \
  --games=ar25,ls20,bp35 \
  --tags=experiment_v1,baseline
```

### 5. Debug Mode
```bash
DEBUG=True uv run parallel_runner.py --agent=llm --games=ar25
```

---

## Troubleshooting

### "No games available"
- Check API key in `.env`
- Verify internet connection
- Check API server status

### "Unknown agent"
- Check agent name spelling
- See `--help` for list of valid agents

### Timeout errors
- Reduce `--max-concurrent`
- Increase API timeout in environment

### Memory issues
- Use `--batch-size` to split large runs
- Reduce `--max-concurrent`

---

## Examples

### Full Game Suite with LLM
```bash
# Run LLM on all 25 games, 5 at a time
uv run parallel_runner.py \
  --agent=llm \
  --games=ar25,ls20,bp35,cd82,dc22,ft09,g50t,ka59,lf52,lp85,m0r0,r11l,re86,s5i5,sb26,sc25,sk48,sp80,su15,tn36,tr87,tu93,vc33,wa30 \
  --max-concurrent=5 \
  --tags=full_suite_llm
```

### Agent Comparison Study
```bash
# Test 3 agent types on same 3 games
uv run parallel_runner.py \
  --assign llm:ar25 --assign fastllm:ar25 --assign reasoningllm:ar25 \
  --assign llm:ls20 --assign fastllm:ls20 --assign reasoningllm:ls20 \
  --assign llm:bp35 --assign fastllm:bp35 --assign reasoningllm:bp35 \
  --parallel-games \
  --max-concurrent=9 \
  --tags=agent_comparison
```

### Playback Testing
```bash
# Playback multiple recordings in parallel
uv run parallel_runner.py \
  --assign ar25.random.abc123.recording.jsonl:ar25 \
  --assign ls20.random.def456.recording.jsonl:ls20 \
  --parallel-games
```
