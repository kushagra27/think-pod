# Deep Reflection Mode — ThinkPod Extension

## What It Does

Deep Reflection mode transforms ThinkPod from a podcast-style thinking exercise into a guided self-analysis conversation. The host persona stays identical — same voice, same style, same personality. But underneath, an analytical layer tracks psychological patterns, steers toward productive territory, and produces a comprehensive reflection document after the session.

## How It Works

Three mechanisms operate invisibly:

**1. Analytical Undertow**
A set of analytical directives appended to the host's system prompt. The host tracks contradictions between stated values and described behavior, avoidance patterns, emotional intensity shifts, shadow triggers (disproportionate reactions to others' qualities), and moments of genuine self-awareness. The host never names these frameworks — they just ask better follow-up questions.

**2. Checkpoints**
Every 8 exchanges, a separate analysis pass reviews the transcript and produces concise steering signals. These get injected into the host's next response as invisible context, causing the conversation to naturally gravitate toward the most psychologically productive territory without the guest feeling redirected.

**3. Post-Session Analysis**
After the session ends, the full transcript runs through a comprehensive analysis prompt that produces:
- A readable reflection document mapping patterns, contradictions, avoidance, emotional landscape, and synthesis
- A structured JSON pattern file that persists across sessions for longitudinal tracking

## Usage

```bash
# Standard session (unchanged behavior)
python src/interview/podcast_session.py --podcaster naval-ravikant

# Deep reflection session
python src/interview/podcast_session.py --podcaster naval-ravikant --reflect

# With pre-filled info
python src/interview/podcast_session.py \
  --podcaster chris-williamson \
  --guest-name "Kush" \
  --topic "navigating ambition and identity after closing a startup" \
  --reflect
```

## File Structure

```
data/
  prompts/
    analytical_undertow.md      # Hidden analytical layer for host prompts
    checkpoint_analysis.md      # Checkpoint steering signal prompt
    post_session_analysis.md    # Post-session analysis prompt
  sessions/
    20260329-143000-naval-ravikant-reflect.md           # Transcript
    20260329-143000-naval-ravikant-analysis.md          # Reflection document
  patterns/
    kush-20260329-143000.json                           # Structured pattern data
```

## Longitudinal Tracking

Pattern files accumulate per guest. Each new reflection session loads the most recent pattern file and injects it as context — the host starts each session with awareness of previously identified patterns without explicitly referencing them. Over multiple sessions, the system tracks:

- How shadow triggers evolve
- Whether contradictions get addressed or deepen
- Shifts in dominant operating mode (desire-driven → obligation-driven → strategic)
- Emerging themes that span sessions
- Growth in observer capacity (moments of genuine self-examination)

## Tuning

**Checkpoint interval:** Edit `CHECKPOINT_INTERVAL` in `podcast_session.py`. Default is 8 exchanges. Lower for more frequent steering (can feel more directed), higher for more organic flow.

**Models:** Edit `ANALYSIS_MODEL` and `CONVERSATION_MODEL`. The conversation uses the same model as standard mode. Analysis passes can use a different model if needed — Opus for deeper analysis, Sonnet for speed.

**Prompt refinement:** The three prompt files in `data/prompts/` are the primary tuning surface. The analytical undertow controls what the host tracks. The checkpoint prompt controls steering signal quality. The post-session prompt controls analysis depth and output structure. Edit these directly — they're plain markdown.

## Design Principles

- The guest should never feel like they're in therapy
- The conversation should feel 20% sharper, not fundamentally different
- Confrontation uses the guest's own words as evidence, never clinical framing
- Contradictions are framed as curiosities, not accusations
- The system amplifies existing self-awareness, it doesn't create it from scratch
- Depth of input determines depth of output — the more honest the guest, the better the analysis
