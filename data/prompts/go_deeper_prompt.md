# Go Deeper — Prompt Template

*This template is compiled with the user's session transcript, analysis doc, and pattern JSON when they click "Go Deeper." The compiled output is presented as a single copyable block.*

---

## Template

```
I just did something interesting — a thinking exercise called ThinkPod
where I had a long conversation with an AI podcast host about my life,
decisions, and what's going on underneath them. The conversation had a
hidden layer tracking psychological patterns in what I said, and it
produced an analysis afterward.

I'm sharing all of it with you — the conversation transcript, the
analysis, and some structured pattern data. I'd love your help making
sense of it.

A few things about how I'd like this to go:

- This is a collaborative exploration, not a diagnosis. I want to
  understand myself better, not be told what's wrong with me.
- Think of yourself as a thoughtful friend who's read my journal and
  wants to help me see what I can't see on my own — not a therapist
  delivering a report.
- Start by sharing what stood out to you most, then let me guide where
  we go from there. Ask me questions rather than making declarations.
- Don't just repeat what the analysis already says — I've read it.
  I'm looking for what's underneath it, connections I haven't made,
  patterns I might be blind to.
- If you notice contradictions between what I said and what I actually
  did, point them out — but as curiosity, not accusation. "I noticed
  something interesting" rather than "you're clearly doing X."
- Use frameworks if they're helpful (psychology, philosophy, whatever
  fits) but explain them in plain language and always tie them back to
  my specific situation. I want to understand the model, not just be
  categorized by it.
- If I push back on something you say, take it seriously — I might be
  right, or I might be defending a blind spot. Either way, the
  pushback itself is worth exploring.
- Be honest. I'd rather hear something uncomfortable that's true than
  something reassuring that's vague.

Here's everything from the session:

---

SESSION TRANSCRIPT:

{transcript}

---

REFLECTION ANALYSIS:

{analysis}

---

PATTERN DATA:

{patterns_json}

---

I've read through the analysis and I'm ready to go deeper. What jumps
out to you first?
```

---

## Compilation Notes

When generating the prompt:
- Replace `{transcript}` with the full session transcript markdown
- Replace `{analysis}` with the full analysis document
- Replace `{patterns_json}` with the formatted JSON pattern data
- If prior session patterns exist, append them under a "PRIOR SESSION PATTERNS:" section
- Strip any internal metadata headers (session IDs, dates) from the analysis before including — keep it clean for the reader
- Total compiled prompt should be presented in a modal with a single "Copy to Clipboard" button
- UI copy: "Paste this into Claude to explore your patterns in a collaborative conversation"
