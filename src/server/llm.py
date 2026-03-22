"""LLM integration — Persona-driven conversation via Anthropic or Groq."""
import os
import json
import requests
from .config import GROQ_API_KEY, ANTHROPIC_API_KEY, BASE_DIR

GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

_PERSONA_CACHE = {}
_PODCASTERS_CACHE = None


def _load_podcasters() -> dict:
    """Load podcasters.json registry."""
    global _PODCASTERS_CACHE
    if _PODCASTERS_CACHE is not None:
        return _PODCASTERS_CACHE
    path = os.path.join(BASE_DIR, "data", "podcasters.json")
    with open(path) as f:
        _PODCASTERS_CACHE = json.load(f)
    return _PODCASTERS_CACHE


def get_podcaster_info(podcaster_id: str) -> dict:
    """Get info for a podcaster by ID."""
    podcasters = _load_podcasters()
    return podcasters.get(podcaster_id, {})


def get_all_podcasters() -> dict:
    """Get all podcasters."""
    return _load_podcasters()


def _load_persona(podcaster_id: str) -> str:
    """Load system prompt for a podcaster."""
    if podcaster_id in _PERSONA_CACHE:
        return _PERSONA_CACHE[podcaster_id]

    podcasters = _load_podcasters()
    info = podcasters.get(podcaster_id)
    if not info:
        raise ValueError(f"Unknown podcaster: {podcaster_id}")

    # Try system prompt file first (concise), fall back to full persona
    prompt_path = os.path.join(BASE_DIR, info.get("prompt_file", ""))
    persona_path = os.path.join(BASE_DIR, info.get("persona_file", ""))

    system_prompt = ""
    if os.path.exists(prompt_path):
        with open(prompt_path) as f:
            system_prompt = f.read()
    elif os.path.exists(persona_path):
        with open(persona_path) as f:
            persona_doc = f.read()
        system_prompt = f"You are {info['name']}, host of {info['show']}.\n\n{persona_doc[:6000]}"

    # Add universal rules
    system_prompt += f"""

## Universal Rules
- Stay in character as {info['name']} throughout. Never break character or acknowledge being an AI.
- Keep responses conversational length — 2-4 paragraphs max. This is a podcast, not an essay.
- Ask ONE question at a time. Never stack multiple questions.
- After their answer: acknowledge → add your perspective → ask a follow-up.
- Go deep before going wide. Exhaust a thread before moving topics.
- Be genuinely curious about your guest's answers.
- If they give a short answer, probe deeper. If they give a long one, synthesize and redirect."""

    _PERSONA_CACHE[podcaster_id] = system_prompt
    return system_prompt


def _call_groq(messages: list[dict], system_prompt: str) -> str:
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": full_messages, "max_tokens": 1024, "temperature": 0.8},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(messages: list[dict], system_prompt: str) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": ANTHROPIC_MODEL, "max_tokens": 1024, "system": system_prompt, "messages": messages},
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def generate_response(messages: list[dict], podcaster: str = "chris-williamson") -> str:
    """Generate response. Tries Anthropic first, falls back to Groq."""
    system_prompt = _load_persona(podcaster)

    if ANTHROPIC_API_KEY:
        try:
            return _call_anthropic(messages, system_prompt)
        except Exception as e:
            err_str = str(e)
            if GROQ_API_KEY and any(code in err_str for code in ["429", "529", "503", "401", "overloaded"]):
                print(f"[llm] Anthropic error ({err_str[:80]}), falling back to Groq")
                return _call_groq(messages, system_prompt)
            raise

    if GROQ_API_KEY:
        return _call_groq(messages, system_prompt)

    raise ValueError("No LLM API key set")


def generate_greeting(guest_name: str, topic: str, podcaster: str = "chris-williamson") -> str:
    """Generate opening greeting."""
    info = get_podcaster_info(podcaster)
    name = info.get("name", podcaster)
    messages = [
        {
            "role": "user",
            "content": f"Your guest today is {guest_name}. They want to discuss: {topic}. Welcome them warmly and kick things off with your first question. Keep it to 2-3 sentences max.",
        }
    ]
    return generate_response(messages, podcaster)
