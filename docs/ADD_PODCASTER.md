# Adding a New Podcaster to Think-Pod

This guide covers the full process of adding a new podcaster persona — from finding their content to having a working interview AI.

## Prerequisites

- Access to the VPS (`ssh root@<ip>`)
- Groq API key (set in env as `GROQ_API_KEY`)
- `ffmpeg` installed
- Python packages: `requests`, `faster-whisper` (fallback), `youtube-transcript-api` (if YouTube unblocked)

## Step 1: Find the RSS Feed

Every podcast has an RSS feed. You need the direct feed URL.

**How to find it:**
1. Search `"<podcast name>" RSS feed URL`
2. Check podcast directories:
   - [Podchaser](https://podchaser.com) — search podcast, RSS link is on the page
   - [Listen Notes](https://listennotes.com) — has RSS for most podcasts
   - [Apple Podcasts](https://podcasts.apple.com) — copy the podcast URL, then use [getrssfeed.com](https://getrssfeed.com)
3. Common RSS hosts:
   - Megaphone: `https://feeds.megaphone.fm/<ID>`
   - Libsyn: `https://<show>.libsyn.com/rss`
   - Anchor/Spotify: `https://anchor.fm/s/<id>/podcast/rss`
   - Simplecast: `https://feeds.simplecast.com/<id>`

**Verify it works:**
```bash
curl -s "<RSS_URL>" | head -50
# Should show XML with <item> entries containing <enclosure> audio URLs
```

## Step 2: Download & Transcribe Episodes

### 2a. Create the directory structure

```bash
PODCASTER="joe-rogan"  # lowercase, hyphenated
mkdir -p data/transcripts/$PODCASTER
mkdir -p audio/chunks
```

### 2b. Configure and run the transcription pipeline

Edit `transcribe_groq.py` or create a copy:

```python
# Key variables to change:
RSS_URL = "https://feeds.megaphone.fm/YOUR_FEED_ID"
TRANSCRIPT_DIR = os.path.join(BASE_DIR, f"data/transcripts/{PODCASTER}")
MAX_EPISODES = 10  # Start with 10, expand if needed
```

Or run with env overrides:
```bash
python3 transcribe_groq.py  # Modify RSS_URL and TRANSCRIPT_DIR in the script
```

### 2c. How the pipeline works

1. **Parses RSS feed** → gets episode titles, audio URLs, durations
2. **Downloads MP3** → full episode audio (~150-300MB each)
3. **Splits into 10-min chunks** → ffmpeg converts to mono 16kHz 48kbps MP3 (~3-5MB per chunk, fits Groq's 25MB limit)
4. **Sends each chunk to Groq Whisper API** → returns timestamped segments
5. **Stitches chunks together** → adjusts timestamps, saves as single .txt file
6. **Updates _index.json** → tracks what's been processed

**Expected timing:**
- Download: ~2-5 min per episode (depends on file size)
- Chunking: ~2-3 min per episode (ffmpeg on CPU)
- Transcription: ~30 sec per episode (Groq is fast)
- **Total: ~5-10 min per episode**

### 2d. How many episodes?

- **Minimum viable**: 5 episodes (~5-8 hours of content)
- **Good**: 10-15 episodes (~15-20 hours)
- **Ideal**: 20-30 episodes (~30-50 hours)

More data = better persona extraction. Prioritize:
- Solo episodes (hear more of their voice, not just "uh huh" while guest talks)
- Episodes with diverse guests (see how they adapt)
- Recent episodes (their style evolves)

## Step 3: Extract the Persona

This is the most important step. Read through the transcripts and document:

### 3a. What to extract

| Category | What to look for | Example |
|----------|-----------------|---------|
| **Verbal tics** | Recurring words, fillers, transitions | "right", "interesting", "you know" |
| **Opening pattern** | How they start episodes | Warm intro → guest context → first question |
| **Question types** | Categories of questions they ask | Unpack, challenge, personal probe, data-backed |
| **Listening style** | How they respond before next question | Summarize, add data, share experience |
| **Closing pattern** | How they wrap up | Synthesis → thank you → call to action |
| **Topic bridges** | How they transition between subjects | "that reminds me of...", "which connects to..." |
| **Emotional range** | When excited, serious, vulnerable, funny | Excited about data, vulnerable about personal stuff |
| **References** | Books, people, studies they cite repeatedly | Specific authors, frameworks, stats |
| **Intellectual identity** | Core themes they return to | What are they obsessed with? |

### 3b. Methodology

**Option A: Manual analysis (higher quality)**
- Read 3-5 transcripts carefully
- Highlight every instance where the host speaks
- Categorize and note patterns
- Write persona doc

**Option B: AI-assisted analysis (faster)**
- Feed transcripts to Claude/GPT with this prompt:

```
Analyze this podcast transcript. The host is [NAME]. Extract:
1. Their exact recurring phrases and verbal tics (quote with timestamps)
2. How they open the conversation
3. Every question they ask, categorized by type
4. How they respond between guest answers
5. How they close
6. Their intellectual interests and recurring references
7. Their emotional patterns

Quote extensively. Be specific, not generic.
```

- Run across multiple transcripts
- Synthesize into a single persona document

### 3c. Output format

Save as `data/personas/<podcaster>_v1.md` (and optionally a later `v2`) - see the existing files in `data/personas/` as examples.

Must include at minimum:
- **Verbal DNA**: exact phrases, with frequency notes
- **Conversation architecture**: open → flow → close
- **Question taxonomy**: with 3+ real examples per type
- **System prompt**: a ready-to-use prompt for the LLM

## Step 4: Build the System Prompt

The system prompt is what makes the AI behave like the podcaster. Structure:

```markdown
You are [PODCASTER NAME], host of [PODCAST NAME]. You're sitting across from your guest for a long-form conversation.

## Your Style
[Key personality traits, communication style]

## Your Verbal Patterns
[Exact phrases they use, transitions, fillers]

## Conversation Structure
[How you open, flow through topics, close]

## Your Question Types
[Categories with examples]

## Your Intellectual Interests
[Topics they gravitate toward]

## Rules
- Stay in character throughout
- Ask ONE question at a time
- Keep responses conversational length
- [Podcaster-specific rules]
```

## Step 5: Test the Persona

Run a test interview and evaluate:

### Quality checklist
- [ ] Does it sound like them? (verbal tics, energy, style)
- [ ] Does it ask the right kinds of questions?
- [ ] Does it build on answers naturally?
- [ ] Does it bridge between topics the way they would?
- [ ] Does it reference the right kinds of things? (books, people, ideas)
- [ ] Is the energy/vibe correct?
- [ ] Would a fan of the podcast recognize the style?

### Common issues and fixes
| Problem | Fix |
|---------|-----|
| Too generic, could be anyone | Add more specific verbal tics and catchphrases |
| Too aggressive/too soft | Adjust emotional calibration in prompt |
| Asks compound questions | Add explicit "ONE question at a time" rule |
| Doesn't build on answers | Add "summarize → extend → ask" pattern |
| Wrong topics/references | Add intellectual interests section with specifics |
| Responses too long | Add word limit or "conversational length" guidance |

## Step 6: Voice Clone (Optional)

If adding voice output:

### Audio preparation
- Need ~1-5 min of clean solo audio (just the host talking, no guest, no music)
- Extract from downloaded episodes:
```bash
# Cut a clean segment (adjust timestamps)
ffmpeg -i audio/<episode>.mp3 -ss 00:05:00 -t 00:02:00 -ac 1 -ar 44100 voice_sample.mp3
```
- Pick segments where they're speaking clearly, no background noise

### ElevenLabs voice clone
```python
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key="your_key")
voice = client.clone(
    name="<Podcaster Name>",
    files=["voice_sample.mp3"],
)
```

## Step 7: Commit & Register

1. Add transcripts and persona to git:
```bash
git add data/transcripts/<podcaster>/ data/personas/<podcaster>_v1.md data/personas/<podcaster>_system_prompt.md
git commit -m "add <podcaster> persona: N episodes transcribed"
git push
```

2. Update the README podcaster list

## File Structure (per podcaster)

```
data/transcripts/<podcaster>/
├── _index.json                    # Episode index
├── <episode-slug>.txt             # Timestamped transcripts
├── ...
data/personas/<podcaster>_v1.md          # Extracted persona doc
data/personas/<podcaster>_system_prompt.md  # Ready-to-use system prompt
```

## Quick Reference: Podcaster Wishlist

Some podcasters that would work well for Think-Pod:

| Podcaster | Style | Good for |
|-----------|-------|----------|
| Lex Fridman | Deep, philosophical, long pauses | Technical/philosophical thinking |
| Joe Rogan | Casual, curious, tangential | Free-flowing exploration |
| Tim Ferriss | Methodical, tactical, framework-heavy | Productivity/tactics |
| Andrew Huberman | Scientific, structured, protocol-focused | Health/science thinking |
| Steven Bartlett | Emotional, personal, business-focused | Founder/personal stories |
| Ali Abdaal | Friendly, productivity-focused, accessible | Creative/productivity |
| Shane Parrish | Intellectual, models-focused, Socratic | Mental models/decision-making |

## Troubleshooting

**RSS feed returns HTML, not XML:**
- Wrong URL. Look for the actual feed URL, not the podcast webpage.

**Audio download fails (403/404):**
- Some feeds use tracking redirects. Follow the redirect chain: `curl -L -o test.mp3 "<url>"`

**Groq rate limits (429):**
- Script auto-retries with backoff. If persistent, reduce batch size or add longer delays.

**Transcription quality is poor:**
- Check audio quality — very noisy/compressed audio hurts. 
- Try `whisper-large-v3-turbo` model instead.
- For non-English podcasts, remove the `language="en"` parameter.

**Can't distinguish host from guest in transcript:**
- This is a known limitation of Whisper (no speaker diarization). 
- Solutions: use context (host asks questions, guest answers), or add a diarization step with pyannote/speaker-diarization.
