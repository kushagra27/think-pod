#!/usr/bin/env python3
"""
Podcast Thinking - interactive conversation loop for multiple podcasters.
Supports optional reflection mode for deeper self-analysis conversations.
"""

import argparse
import json
import os
import re
import requests
import sys
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
BASE_DIR = '/root/.openclaw/workspace/projects/podcast-thinking'
DATA_DIR = os.path.join(BASE_DIR, 'data')
SESSION_DIR = os.path.join(DATA_DIR, 'sessions')
PATTERNS_DIR = os.path.join(DATA_DIR, 'patterns')
PROMPTS_DIR = os.path.join(DATA_DIR, 'prompts')
PODCASTERS_FILE = os.path.join(DATA_DIR, 'podcasters.json')

CHECKPOINT_INTERVAL = 5  # Run analysis every N guest exchanges
ANALYSIS_MODEL = 'claude-sonnet-4-20250514'
CONVERSATION_MODEL = 'claude-sonnet-4-20250514'

os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(PATTERNS_DIR, exist_ok=True)


def load_podcasters():
    with open(PODCASTERS_FILE) as f:
        return json.load(f)


def load_system_prompt(entry):
    path = os.path.join(BASE_DIR, entry['prompt_file'])
    with open(path) as f:
        return f.read().strip()


def load_prompt_file(filename):
    path = os.path.join(PROMPTS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().strip()


def load_latest_patterns(guest_name):
    """Load the most recent pattern file for this guest, if any."""
    safe_name = re.sub(r'[^\w]', '-', guest_name.lower()).strip('-')
    pattern_files = sorted([
        f for f in os.listdir(PATTERNS_DIR)
        if f.startswith(safe_name) and f.endswith('.json')
    ])
    if not pattern_files:
        return None
    latest = os.path.join(PATTERNS_DIR, pattern_files[-1])
    with open(latest) as f:
        return json.load(f)


def choose_podcaster(podcasters):
    keys = list(podcasters.keys())
    print('\nChoose a podcaster:')
    for i, key in enumerate(keys, start=1):
        entry = podcasters[key]
        print(f'  {i}. {entry["name"]} ({entry["show"]})')
    raw = input('Selection [1]: ').strip()
    if not raw:
        return keys[0]
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    if raw in podcasters:
        return raw
    raise ValueError(f'Unknown podcaster selection: {raw}')


def call_claude(messages, system_prompt, model=None):
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY not set. Export it before running a session.')

    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': model or CONVERSATION_MODEL,
            'max_tokens': 1024,
            'system': system_prompt,
            'messages': messages,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']


def call_claude_long(messages, system_prompt, model=None):
    """Same as call_claude but with higher token limit for analysis outputs."""
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY not set.')

    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': model or ANALYSIS_MODEL,
            'max_tokens': 4096,
            'system': system_prompt,
            'messages': messages,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']


def run_checkpoint(transcript_lines, checkpoint_prompt):
    """Run a checkpoint analysis on the conversation so far. Returns steering signal."""
    transcript_text = '\n'.join(transcript_lines)
    messages = [{
        'role': 'user',
        'content': f'Here is the conversation transcript so far:\n\n{transcript_text}\n\nAnalyze this conversation and produce your steering signals.',
    }]
    return call_claude(messages, checkpoint_prompt, model=ANALYSIS_MODEL)


def run_post_session_analysis(transcript_lines, analysis_prompt, prior_patterns=None):
    """Run full post-session analysis. Returns the analysis text."""
    transcript_text = '\n'.join(transcript_lines)

    user_content = f'Here is the full session transcript:\n\n{transcript_text}'
    if prior_patterns:
        user_content += f'\n\nHere is pattern data from previous sessions:\n\n```json\n{json.dumps(prior_patterns, indent=2)}\n```'
    user_content += '\n\nProduce both the reflection document and the structured pattern JSON.'

    messages = [{'role': 'user', 'content': user_content}]
    return call_claude_long(messages, analysis_prompt, model=ANALYSIS_MODEL)


def extract_pattern_json(analysis_text):
    """Extract the JSON block from the analysis output."""
    match = re.search(r'```json\s*(\{.*?\})\s*```', analysis_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def extract_analysis_doc(analysis_text):
    """Extract the document portion (everything before the JSON block)."""
    match = re.search(r'```json', analysis_text)
    if match:
        return analysis_text[:match.start()].strip()
    return analysis_text.strip()


def run_session(podcaster_slug='', guest_name='', topic='', reflect=False):
    podcasters = load_podcasters()
    if not podcaster_slug:
        podcaster_slug = choose_podcaster(podcasters)
    if podcaster_slug not in podcasters:
        raise ValueError(f'Unknown podcaster: {podcaster_slug}')

    podcaster = podcasters[podcaster_slug]
    system_prompt = load_system_prompt(podcaster)
    session_id = datetime.now().strftime('%Y%m%d-%H%M%S')

    # Reflection mode setup
    undertow_prompt = None
    checkpoint_prompt = None
    analysis_prompt = None
    prior_patterns = None
    steering_note = None
    steering_turns_remaining = 0

    if reflect:
        undertow_prompt = load_prompt_file('analytical_undertow.md')
        checkpoint_prompt = load_prompt_file('checkpoint_analysis.md')
        analysis_prompt = load_prompt_file('post_session_analysis.md')

        if not all([undertow_prompt, checkpoint_prompt, analysis_prompt]):
            print('Warning: Reflection mode enabled but prompt files are missing.')
            print(f'  Expected in: {PROMPTS_DIR}/')
            print('  Required: analytical_undertow.md, checkpoint_analysis.md, post_session_analysis.md')
            print('  Falling back to standard mode.\n')
            reflect = False

    if reflect:
        # Append analytical undertow to host system prompt
        system_prompt += f'\n\n---\n\n{undertow_prompt}'

        # Load prior patterns for this guest if available
        if guest_name:
            prior_patterns = load_latest_patterns(guest_name)
            if prior_patterns:
                system_prompt += (
                    f'\n\n## Prior Session Context\n'
                    f'This guest has done previous reflection sessions. '
                    f'Here are patterns identified previously — use them to inform '
                    f'your questions but do not reference them directly:\n\n'
                    f'```json\n{json.dumps(prior_patterns, indent=2)}\n```'
                )

    # File paths
    mode_label = 'reflect' if reflect else 'standard'
    transcript_path = os.path.join(SESSION_DIR, f'{session_id}-{podcaster_slug}-{mode_label}.md')
    analysis_path = os.path.join(SESSION_DIR, f'{session_id}-{podcaster_slug}-analysis.md')
    safe_guest = re.sub(r'[^\w]', '-', (guest_name or 'guest').lower()).strip('-')
    patterns_path = os.path.join(PATTERNS_DIR, f'{safe_guest}-{session_id}.json')

    messages = []
    transcript_lines = []

    print('\n' + '=' * 72)
    print(f"PODCAST THINKING - {podcaster['show']} with {podcaster['name']}")
    if reflect:
        print('  [Deep Reflection Mode Enabled]')
    print('=' * 72)
    print("Type your responses. Type 'quit' to end the session.")
    print('Your transcript will be saved automatically.\n')

    if not guest_name:
        guest_name = input("What's your name? -> ").strip() or 'Guest'
    if not topic:
        topic = input('What do you want to talk about? -> ').strip() or 'life, work, and the future'

    transcript_lines.extend([
        f'# Podcast Thinking Session - {session_id}',
        f'# Podcaster: {podcaster["name"]}',
        f'# Show: {podcaster["show"]}',
        f'# Guest: {guest_name}',
        f'# Topic: {topic}',
        f'# Mode: {"Deep Reflection" if reflect else "Standard"}',
        f'# Date: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '',
    ])

    opening_msg = (
        f'Your guest today is {guest_name}. '
        f'They want to discuss: {topic}. '
        f'Welcome them warmly and start the conversation in character as {podcaster["name"]}.'
    )
    messages.append({'role': 'user', 'content': opening_msg})

    print(f"{podcaster['name']} is thinking...\n")
    host_response = call_claude(messages, system_prompt)
    messages.append({'role': 'assistant', 'content': host_response})

    print(f"{podcaster['name']}: {host_response}\n")
    transcript_lines.append(f"**{podcaster['name']}:** {host_response}\n")

    turn = 0
    checkpoint_count = 0

    while True:
        guest_input = input(f"{guest_name}: ").strip()

        if guest_input.lower() in ('quit', 'exit', 'done', 'end'):
            # Closing
            messages.append({
                'role': 'user',
                'content': (
                    '[The guest signals they need to wrap up. Give a warm closing, '
                    'summarize the key insight from the conversation, and thank them.]'
                ),
            })
            host_response = call_claude(messages, system_prompt)
            print(f"\n{podcaster['name']}: {host_response}\n")
            transcript_lines.append(f"**{guest_name}:** [Session ended]\n")
            transcript_lines.append(f"**{podcaster['name']}:** {host_response}\n")
            break

        if not guest_input:
            continue

        transcript_lines.append(f"**{guest_name}:** {guest_input}\n")
        turn += 1

        # --- Checkpoint logic ---
        if reflect and turn > 0 and turn % CHECKPOINT_INTERVAL == 0:
            checkpoint_count += 1
            print(f"  [Reflection checkpoint {checkpoint_count}...]\n")
            try:
                steering_note = run_checkpoint(transcript_lines, checkpoint_prompt)
                steering_turns_remaining = 3
            except Exception as e:
                print(f"  [Checkpoint failed: {e}]\n")
                steering_note = None

        # Build the user message, with optional steering note
        if reflect and steering_note and steering_turns_remaining > 0:
            injected_content = (
                f'[INTERNAL STEERING — invisible to guest, do not reference directly. '
                f'Use this to guide your next question naturally in character:\n'
                f'{steering_note}]\n\n'
                f'{guest_input}'
            )
            messages.append({'role': 'user', 'content': injected_content})
            steering_turns_remaining -= 1
            if steering_turns_remaining <= 0:
                steering_note = None
        else:
            messages.append({'role': 'user', 'content': guest_input})

        print(f"\n{podcaster['name']} is thinking...\n")
        host_response = call_claude(messages, system_prompt)
        messages.append({'role': 'assistant', 'content': host_response})

        print(f"{podcaster['name']}: {host_response}\n")
        transcript_lines.append(f"**{podcaster['name']}:** {host_response}\n")

        # Auto-save transcript after each exchange
        with open(transcript_path, 'w') as f:
            f.write('\n'.join(transcript_lines))

    # --- Finalize transcript ---
    transcript_lines.append(f"\n---\n*Session ended. {turn} exchanges. Mode: {mode_label}.*")
    with open(transcript_path, 'w') as f:
        f.write('\n'.join(transcript_lines))
    print(f'Transcript saved: {transcript_path}')
    print(f'  {turn} exchanges recorded.\n')

    # --- Post-session analysis (reflection mode only) ---
    if reflect and turn >= 4:
        print('Running post-session reflection analysis...')
        print('  (This takes a moment — generating your reflection document.)\n')
        try:
            analysis_output = run_post_session_analysis(
                transcript_lines, analysis_prompt, prior_patterns
            )

            # Save full analysis document
            analysis_doc = extract_analysis_doc(analysis_output)
            with open(analysis_path, 'w') as f:
                f.write(f'# Reflection Analysis — {guest_name}\n')
                f.write(f'# Session: {session_id}\n')
                f.write(f'# Host: {podcaster["name"]}\n')
                f.write(f'# Date: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n')
                f.write(analysis_doc)
            print(f'  Reflection document saved: {analysis_path}')

            # Save structured patterns
            patterns = extract_pattern_json(analysis_output)
            if patterns:
                with open(patterns_path, 'w') as f:
                    json.dump(patterns, f, indent=2)
                print(f'  Pattern data saved: {patterns_path}')

                # Print key findings
                print('\n  Key findings:')
                if patterns.get('contradictions'):
                    print(f'    Contradictions detected: {len(patterns["contradictions"])}')
                if patterns.get('shadow_triggers'):
                    print(f'    Shadow triggers: {", ".join(patterns["shadow_triggers"])}')
                if patterns.get('avoidance_topics'):
                    print(f'    Avoidance topics: {", ".join(patterns["avoidance_topics"])}')
                if patterns.get('observer_moments'):
                    print(f'    Observer moments: {patterns["observer_moments"]}')
                if patterns.get('dominant_mode'):
                    print(f'    Dominant mode: {patterns["dominant_mode"]}')
            else:
                print('  (Could not extract structured patterns — analysis document still saved.)')

        except Exception as e:
            print(f'  Analysis failed: {e}')
            print('  Transcript was saved successfully. You can run analysis manually later.')

    elif reflect and turn < 4:
        print('Session too short for meaningful analysis (minimum 4 exchanges).')

    print()
    return transcript_path


def main():
    parser = argparse.ArgumentParser(
        description='Podcast Thinking — interactive conversation with AI podcast hosts.',
        epilog='Example: podcast-session --podcaster naval-ravikant --reflect',
    )
    parser.add_argument('--podcaster', help='Podcaster slug, e.g. lex-fridman')
    parser.add_argument('--guest-name', default='')
    parser.add_argument('--topic', default='')
    parser.add_argument('--list-podcasters', action='store_true')
    parser.add_argument(
        '--reflect',
        action='store_true',
        help='Enable deep reflection mode — adds psychological analysis, '
             'periodic checkpoints, and a post-session reflection document.',
    )
    args = parser.parse_args()

    podcasters = load_podcasters()
    if args.list_podcasters:
        for slug, entry in podcasters.items():
            print(f'{slug}\t{entry["name"]}\t{entry["show"]}')
        return

    run_session(
        podcaster_slug=args.podcaster or '',
        guest_name=args.guest_name,
        topic=args.topic,
        reflect=args.reflect,
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
