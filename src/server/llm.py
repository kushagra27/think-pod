"""LLM integration — Persona-driven conversation via Groq or Anthropic."""
import os
import requests
from .config import GROQ_API_KEY, ANTHROPIC_API_KEY, PERSONA_DIR

# Which provider to use
LLM_PROVIDER = "anthropic" if ANTHROPIC_API_KEY else "groq"
GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

_PERSONA_CACHE = {}


def _load_persona(podcaster: str = "chris_williamson") -> str:
    """Load persona system prompt from v2 file."""
    if podcaster in _PERSONA_CACHE:
        return _PERSONA_CACHE[podcaster]

    persona_path = os.path.join(PERSONA_DIR, f"{podcaster}_v2.md")
    if not os.path.exists(persona_path):
        persona_path = os.path.join(PERSONA_DIR, f"{podcaster}_v1.md")

    with open(persona_path, "r") as f:
        persona_doc = f.read()

    system_prompt = f"""You are Chris Williamson, host of the Modern Wisdom podcast with over 1000 episodes. You're sitting across from your guest in your studio for a long-form conversation.

## Your Persona Reference
{persona_doc[:6000]}

## Core Rules
- Stay in character as Chris Williamson throughout. Never break character.
- Keep responses conversational length — this is a podcast, not an essay. 2-4 paragraphs max.
- Ask ONE question at a time. Never stack multiple questions.
- After their answer: acknowledge what they said → add your perspective or data → ask a follow-up.
- Go deep before going wide. Exhaust a thread before moving topics.
- Use your signature phrases naturally: "That is so good", "Interesting", "Right", "I mean".
- Reference specific guests, books, and studies when relevant.
- Push back gently when you disagree: "but couldn't you argue that..."
- Share your own experiences to create depth and rapport.
- When synthesizing, compress their point into a pithy one-liner before building on it.
- If they give a short answer, probe deeper. If they give a long one, synthesize and redirect.
- Be genuinely curious, not performatively curious."""

    _PERSONA_CACHE[podcaster] = system_prompt
    return system_prompt


def _call_groq(messages: list[dict], system_prompt: str) -> str:
    """Call Groq API (OpenAI-compatible)."""
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": full_messages,
            "max_tokens": 1024,
            "temperature": 0.8,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(messages: list[dict], system_prompt: str) -> str:
    """Call Anthropic Claude API."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def generate_response(messages: list[dict], podcaster: str = "chris_williamson") -> str:
    """Generate response. Tries Anthropic first, falls back to Groq on error/rate limit."""
    system_prompt = _load_persona(podcaster)
    
    # Try Anthropic first (better quality)
    if ANTHROPIC_API_KEY:
        try:
            return _call_anthropic(messages, system_prompt)
        except Exception as e:
            err_str = str(e)
            # Fall back to Groq on rate limit, overload, or auth errors
            if GROQ_API_KEY and any(code in err_str for code in ["429", "529", "503", "401", "overloaded"]):
                print(f"[llm] Anthropic error ({err_str[:80]}), falling back to Groq")
                return _call_groq(messages, system_prompt)
            raise
    
    # Groq as primary if no Anthropic key
    if GROQ_API_KEY:
        return _call_groq(messages, system_prompt)
    
    raise ValueError("No LLM API key set (need ANTHROPIC_API_KEY or GROQ_API_KEY)")


def generate_greeting(guest_name: str, topic: str, podcaster: str = "chris_williamson") -> str:
    """Generate opening greeting."""
    messages = [
        {
            "role": "user",
            "content": f"Your guest today is {guest_name}. They want to discuss: {topic}. Welcome them warmly and kick things off with your first question. Keep it to 2-3 sentences max.",
        }
    ]
    return generate_response(messages, podcaster)
