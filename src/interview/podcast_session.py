#!/usr/bin/env python3
"""
Podcast Thinking - interactive conversation loop for multiple podcasters.
"""

import argparse
import json
import os
import requests
import sys
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
BASE_DIR = '/root/.openclaw/workspace/projects/podcast-thinking'
DATA_DIR = os.path.join(BASE_DIR, 'data')
SESSION_DIR = os.path.join(DATA_DIR, 'sessions')
PODCASTERS_FILE = os.path.join(DATA_DIR, 'podcasters.json')
os.makedirs(SESSION_DIR, exist_ok=True)


def load_podcasters():
    with open(PODCASTERS_FILE) as f:
        return json.load(f)


def load_system_prompt(entry):
    path = os.path.join(BASE_DIR, entry['prompt_file'])
    with open(path) as f:
        return f.read().strip()


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


def call_claude(messages, system_prompt):
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
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 1024,
            'system': system_prompt,
            'messages': messages,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']


def run_session(podcaster_slug='', guest_name='', topic=''):
    podcasters = load_podcasters()
    if not podcaster_slug:
        podcaster_slug = choose_podcaster(podcasters)
    if podcaster_slug not in podcasters:
        raise ValueError(f'Unknown podcaster: {podcaster_slug}')

    podcaster = podcasters[podcaster_slug]
    system_prompt = load_system_prompt(podcaster)
    session_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    transcript_path = os.path.join(SESSION_DIR, f'{session_id}-{podcaster_slug}.md')

    messages = []
    transcript_lines = []

    print('\n' + '=' * 72)
    print(f"PODCAST THINKING - {podcaster['show']} with {podcaster['name']}")
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
    while True:
        guest_input = input(f"{guest_name}: ").strip()

        if guest_input.lower() in ('quit', 'exit', 'done', 'end'):
            messages.append({
                'role': 'user',
                'content': '[The guest signals they need to wrap up. Give a warm closing, summarize the key insight from the conversation, and thank them.]',
            })
            host_response = call_claude(messages, system_prompt)
            print(f"\n{podcaster['name']}: {host_response}\n")
            transcript_lines.append(f"**{guest_name}:** [Session ended]\n")
            transcript_lines.append(f"**{podcaster['name']}:** {host_response}\n")
            break

        if not guest_input:
            continue

        transcript_lines.append(f"**{guest_name}:** {guest_input}\n")
        messages.append({'role': 'user', 'content': guest_input})

        print(f"\n{podcaster['name']} is thinking...\n")
        host_response = call_claude(messages, system_prompt)
        messages.append({'role': 'assistant', 'content': host_response})

        print(f"{podcaster['name']}: {host_response}\n")
        transcript_lines.append(f"**{podcaster['name']}:** {host_response}\n")
        turn += 1

        with open(transcript_path, 'w') as f:
            f.write('\n'.join(transcript_lines))

    transcript_lines.append(f"\n---\n*Session ended. {turn} exchanges.*")
    with open(transcript_path, 'w') as f:
        f.write('\n'.join(transcript_lines))

    print(f'Transcript saved: {transcript_path}')
    print(f'  {turn} exchanges recorded.\n')
    return transcript_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--podcaster', help='Podcaster slug, for example lex-fridman')
    parser.add_argument('--guest-name', default='')
    parser.add_argument('--topic', default='')
    parser.add_argument('--list-podcasters', action='store_true')
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
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
