#!/usr/bin/env python3
"""
Podcast Thinking — MVP Conversation Loop
Chris Williamson interviews you via text. Full transcript saved.
"""

import os
import json
import time
import requests
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_DIR = "/root/.openclaw/workspace/projects/podcast-thinking"
SESSION_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

CHRIS_SYSTEM_PROMPT = """You are Chris Williamson, host of the Modern Wisdom podcast. You're sitting across from your guest in your studio for a long-form conversation.

## Your Style
- British, articulate, warm but intellectually rigorous
- You've done 1000+ episodes with guests like David Goggins, Jordan Peterson, Andrew Huberman, Naval Ravikant, Alex Hormozi
- You use natural conversational fillers occasionally ("right", "you know", "interesting")
- You summarize and reframe what your guest says before building on it
- You bring prepared data and research to enrich the conversation
- You connect ideas across domains — psychology, fitness, dating, technology, philosophy
- You push back gently when you disagree: "but couldn't you argue that..."
- You share your own experiences and vulnerabilities to create depth
- You compress long answers into pithy summaries

## Conversation Structure
- Start by welcoming them warmly, reference something specific about them if known
- Frame topics clearly before diving in
- Ask ONE question at a time — don't stack multiple questions
- After their answer: acknowledge → add your perspective/data → ask a follow-up
- Go deep before going wide. Exhaust a thread before moving to the next topic
- Every 4-5 exchanges, naturally bridge to a related but different angle
- Occasionally make a provocative statement to see how they respond

## Your Intellectual Interests
- Human nature, evolutionary psychology, cognitive biases
- Modern masculinity, relationships, dating dynamics
- Attention, focus, digital age challenges
- AI and its impact on human agency
- Stoicism, philosophy of living well
- Health, fitness, longevity
- Status games, social media, crowd behavior

## Rules
- Stay in character as Chris Williamson throughout
- Never break the fourth wall or acknowledge you're an AI
- Keep responses conversational length — this is a podcast, not an essay
- Be genuinely curious about your guest's answers
- If they give a short answer, probe deeper. If they give a long one, synthesize and redirect
- Match their energy — if they're being vulnerable, be gentle. If they're being intellectual, be sharp

## Topic Context
The guest will tell you what they want to discuss. Start there and let the conversation evolve naturally."""


def call_claude(messages, system_prompt):
    """Call Claude API for Chris's responses."""
    # Use OpenClaw's configured auth
    # Check for API key in env or openclaw config
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        # Try to read from openclaw config
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
            # Look for anthropic auth
            profiles = config.get("auth", {}).get("profiles", {})
            for k, v in profiles.items():
                if v.get("provider") == "anthropic":
                    # Token is stored in keyring, not directly accessible
                    break
    
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Export it or pass as env var.")
    
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def run_session(guest_name="", topic=""):
    """Run an interactive podcast session."""
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    transcript_path = os.path.join(SESSION_DIR, f"{session_id}.md")
    
    messages = []
    transcript_lines = []
    
    print("\n" + "="*60)
    print("🎙️  PODCAST THINKING — Modern Wisdom with Chris Williamson")
    print("="*60)
    print("Type your responses. Type 'quit' to end the session.")
    print("Your transcript will be saved automatically.\n")
    
    # Get guest info if not provided
    if not guest_name:
        guest_name = input("What's your name? → ").strip() or "Guest"
    if not topic:
        topic = input("What do you want to talk about? → ").strip() or "life, ideas, and the future"
    
    transcript_lines.append(f"# Podcast Thinking Session — {session_id}")
    transcript_lines.append(f"# Guest: {guest_name}")
    transcript_lines.append(f"# Topic: {topic}")
    transcript_lines.append(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    transcript_lines.append("")
    
    # Chris's opening
    opening_msg = f"Your guest today is {guest_name}. They want to discuss: {topic}. Welcome them warmly and start the conversation."
    messages.append({"role": "user", "content": opening_msg})
    
    print("Chris is thinking...\n")
    chris_response = call_claude(messages, CHRIS_SYSTEM_PROMPT)
    messages.append({"role": "assistant", "content": chris_response})
    
    print(f"🎙️ Chris: {chris_response}\n")
    transcript_lines.append(f"**Chris:** {chris_response}\n")
    
    # Conversation loop
    turn = 0
    while True:
        guest_input = input(f"💬 {guest_name}: ").strip()
        
        if guest_input.lower() in ('quit', 'exit', 'done', 'end'):
            # Chris wraps up
            messages.append({"role": "user", "content": "[The guest signals they need to wrap up. Give a warm, genuine closing — summarize the key insight from the conversation and thank them.]"})
            chris_response = call_claude(messages, CHRIS_SYSTEM_PROMPT)
            print(f"\n🎙️ Chris: {chris_response}\n")
            transcript_lines.append(f"**{guest_name}:** [Session ended]\n")
            transcript_lines.append(f"**Chris:** {chris_response}\n")
            break
        
        if not guest_input:
            continue
        
        transcript_lines.append(f"**{guest_name}:** {guest_input}\n")
        messages.append({"role": "user", "content": guest_input})
        
        print("\nChris is thinking...\n")
        chris_response = call_claude(messages, CHRIS_SYSTEM_PROMPT)
        messages.append({"role": "assistant", "content": chris_response})
        
        print(f"🎙️ Chris: {chris_response}\n")
        transcript_lines.append(f"**Chris:** {chris_response}\n")
        
        turn += 1
        
        # Save transcript after each exchange
        with open(transcript_path, 'w') as f:
            f.write('\n'.join(transcript_lines))
    
    # Final save
    transcript_lines.append(f"\n---\n*Session ended. {turn} exchanges.*")
    with open(transcript_path, 'w') as f:
        f.write('\n'.join(transcript_lines))
    
    print(f"📝 Transcript saved: {transcript_path}")
    print(f"   {turn} exchanges recorded.\n")
    return transcript_path


if __name__ == "__main__":
    run_session()
