# RCA Agent Prompts

This directory contains prompts for the Root Cause Analysis (RCA) agent, optimized for investigating distributed system failures.

## Prompt Versions

### v6.txt (Original)
- **Size:** 4,110 words, 32,994 characters
- **Mode:** Single monolithic prompt
- **Description:** Original comprehensive prompt with all phases, examples, and guidance in one file
- **Best for:** Stability, well-tested behavior

### v7.txt (Optimized Single-File)
- **Size:** 2,170 words, 17,817 characters (**47% reduction**)
- **Mode:** Single monolithic prompt
- **Description:** Optimized version with:
  - Condensed examples (show pattern once, not 3×)
  - Streamlined tool reference
  - Compressed JSON template
  - Simplified Bayesian guidance
  - Removed redundancy
- **Best for:** Lower token usage while maintaining all functionality, drop-in replacement for v6

### v7_base.txt + v7_phase{0-5}.txt (Dynamic Phase Loading)
- **Size:** ~1,200 words base + ~400-700 words per phase = **~1,600-1,900 words per turn (55-60% reduction)**
- **Mode:** Phased prompts with dynamic loading
- **Description:** Base prompt always loaded + phase-specific prompt loaded based on current investigation phase
  - `v7_base.txt`: System prompt with phase navigation map (always loaded)
  - `v7_phase0.txt`: Phase 0 - SITUATIONAL_AWARENESS
  - `v7_phase1.txt`: Phase 1 - HYPOTHESIS_GENERATION
  - `v7_phase2.txt`: Phase 2 - EVIDENCE_GATHERING
  - `v7_phase3.txt`: Phase 3 - DEEP_VALIDATION
  - `v7_phase4.txt`: Phase 4 - CAUSAL_CONFIRMATION
  - `v7_phase5.txt`: Phase 5 - SYNTHESIS
- **Best for:** Maximum token efficiency, better focus per phase, clearer phase-specific guidance

## Configuration

### Using Single Prompt Mode (Default)

**Config file (`core/config.py`):**
```python
REACT_PROMPT_VERSION = "v7"  # or "v6"
PROMPT_MODE = "single"
```

**Environment variables:**
```bash
export UFFLOW_PROMPT_VERSION=v7
export UFFLOW_PROMPT_MODE=single
```

This loads the entire prompt from `v7.txt` on every turn.

### Using Phased Prompt Mode

**Config file (`core/config.py`):**
```python
REACT_PROMPT_VERSION = "v7"
PROMPT_MODE = "phased"
```

**Environment variables:**
```bash
export UFFLOW_PROMPT_VERSION=v7
export UFFLOW_PROMPT_MODE=phased
```

This dynamically loads:
- `v7_base.txt` (always) + `v7_phase0.txt` (on Turn 1)
- `v7_base.txt` (always) + `v7_phase2.txt` (when in EVIDENCE_GATHERING phase)
- etc.

## How Phased Mode Works

### Phase Transition Logic

The agent's `state.active.phase` determines which phase-specific prompt loads:

```python
state.active.phase = "SITUATIONAL_AWARENESS"  # Loads v7_phase0.txt
state.active.phase = "HYPOTHESIS_GENERATION"   # Loads v7_phase1.txt
state.active.phase = "EVIDENCE_GATHERING"      # Loads v7_phase2.txt
state.active.phase = "DEEP_VALIDATION"         # Loads v7_phase3.txt
state.active.phase = "CAUSAL_CONFIRMATION"     # Loads v7_phase4.txt
state.active.phase = "SYNTHESIS"               # Loads v7_phase5.txt
```

### Phase Navigation

The base prompt (`v7_base.txt`) contains a compact phase navigation map that's always visible:

```
Phase 0: SITUATIONAL_AWARENESS
  Exit: Have blast radius + timeline + changes → Phase 1

Phase 1: HYPOTHESIS_GENERATION
  Exit: 3-5 ranked hypotheses → Phase 2

Phase 2: EVIDENCE_GATHERING
  Exit: Confidence > 0.90 → Phase 3
  Stuck: All ruled out → Phase 1

Phase 3: DEEP_VALIDATION
  Exit: Mechanism confirmed → Phase 4
  Stuck: Cannot confirm → Phase 2

Phase 4: CAUSAL_CONFIRMATION
  Exit: Dependencies healthy → Phase 5
  Pivot: Unhealthy dependency → Phase 2

Phase 5: SYNTHESIS
  Exit: Call finish()
```

This ensures the agent:
1. Always knows what phase it's in
2. Knows how to transition to next phase
3. Knows recovery paths when stuck
4. Only sees detailed guidance for current phase

## Token Usage Comparison

| Prompt Version | Mode | Approx. Tokens/Turn | Reduction |
|----------------|------|---------------------|-----------|
| v6.txt | Single | ~5,500 | Baseline |
| v7.txt | Single | ~2,900 | -47% |
| v7 phased | Phased | ~2,400 | -56% |

*Token counts are approximate and vary based on transcript length*

## Effectiveness Improvements in v7

Beyond size reduction, v7 includes effectiveness improvements:

1. **Inverted Pyramid Structure:** Most critical info first (phase objectives), reference material last
2. **Just-in-Time Information:** Agent only sees what's needed for current phase
3. **Condensed Bayesian Guidance:** Inline likelihood ratios instead of verbose table + examples
4. **Phase-Specific Exit Criteria:** Clear checklist at end of each phase prompt
5. **Reduced Decision Paralysis:** Fewer explicit options = faster decisions
6. **Tool-to-Phase Mapping:** Tools organized by phase in navigation map
7. **Simplified Failure Recovery:** Simple "stuck >5 turns" heuristic instead of complex taxonomy

## Recommendations

### For Production Use
- **Start with:** `v7.txt` in single mode (proven optimization, easy migration)
- **Monitor:** Agent performance and RCA quality
- **Upgrade to:** Phased mode after validation (maximum efficiency)

### For Development/Testing
- **Use:** Phased mode to test dynamic loading
- **Validate:** Phase transitions work correctly
- **Compare:** RCA quality vs. v6/v7 single mode

### For Debugging
- **Single mode:** Easier to see full prompt in logs
- **Phased mode:** Better for understanding phase-specific behavior

## Migration Guide

### From v6 to v7 (Single Mode)

1. Update config:
   ```python
   REACT_PROMPT_VERSION = "v7"
   PROMPT_MODE = "single"  # Keep single mode
   ```

2. Test agent behavior on known incidents

3. Compare RCA quality and token usage

4. No code changes needed - drop-in replacement

### From v7 Single to v7 Phased

1. Update config:
   ```python
   REACT_PROMPT_VERSION = "v7"
   PROMPT_MODE = "phased"  # Enable phased mode
   ```

2. Verify phase-specific prompts exist (v7_phase0.txt through v7_phase5.txt)

3. Test phase transitions:
   - Phase 0 → Phase 1 (after situational awareness)
   - Phase 2 → Phase 3 (when confidence > 0.90)
   - Phase 4 → Phase 2 (when pivot needed)

4. Monitor logs for phase loading messages:
   ```
   INFO: Building phased prompt for phase: EVIDENCE_GATHERING
   ```

## Troubleshooting

### Issue: "Phased base prompt not found"
**Solution:** Ensure `v7_base.txt` exists in prompts directory

### Issue: Agent stuck in one phase
**Solution:** Check phase transition logic in phase-specific prompts. Agent should update `state.active.phase` when exit criteria met.

### Issue: Higher token usage than expected
**Solution:**
- Check transcript truncation is working
- Verify you're using phased mode, not single mode
- Check base_prompt + phase_prompt combined size

### Issue: Phase transitions not working
**Solution:**
- Check agent is updating `state.active.phase` field
- Verify phase names match exactly (case-sensitive)
- Check logs for phase loading messages

## Performance Metrics

Track these metrics when switching prompt modes:

1. **Token usage per turn:** Lower is better
2. **RCA accuracy:** Same or better quality
3. **Turns to completion:** Should remain similar
4. **Phase transition correctness:** Agent transitions at right times
5. **Stuck recovery:** Agent recovers from stuck states

## Future Enhancements

Potential improvements for phased mode:

1. **Context-aware tool filtering:** Only show tools relevant to current phase
2. **Phase-specific examples:** Load examples dynamically based on phase
3. **Adaptive phase loading:** Load next phase's prompt speculatively
4. **Phase-specific token budgets:** Allocate tokens dynamically per phase
