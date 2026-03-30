#!/usr/bin/env python3
"""
End-to-end test for Deep Reflection mode via the Think-Pod API.

Simulates a 12-turn text-only conversation with reflection enabled,
verifying: session creation, checkpoint triggers, steering injection,
post-session analysis, and DB persistence.

Usage:
    python3 scripts/test_reflect.py [--turns 12] [--base-url http://127.0.0.1:8001]

Requires SUPABASE_URL, SUPABASE_SERVICE_KEY in .env (uses service key to
mint a test JWT, bypassing OAuth).
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Simulated guest responses — progressively deeper to trigger interesting analysis
GUEST_RESPONSES = [
    "I've been thinking a lot about what it means to really commit to something. Like, I spent years jumping between ideas and projects, never fully going all-in on one thing.",
    "Yeah, I think there was definitely fear underneath it. Fear of picking wrong. If I never fully commit, I never fully fail, right?",
    "Honestly? Probably my first startup. I poured everything into it for two years, and when it didn't work out, I told myself I'd never let myself get that invested again.",
    "That's a good question. I think I told everyone I was fine, that it was a learning experience. But privately I was gutted. I felt like I'd wasted everyone's time, including my own.",
    "I don't know if I've fully processed it even now. I keep busy. Building the next thing. But sometimes at 2am I wonder if I'm running toward something or running away from the last failure.",
    "My dad, probably. He had this thing where he'd start projects around the house — never finish any of them. I swore I'd be different, but here I am with a graveyard of half-built apps.",
    "Ha, yeah. I never connected those two things before. I'm so afraid of being like him that I overcorrect — I don't commit at all rather than commit and not finish.",
    "It's weird because rationally I know that's not how it works. Some of the best founders I know have multiple failures. But emotionally there's this voice that says 'if you fail again, it proves something about you.'",
    "That I'm fundamentally not good enough. That the first failure wasn't bad luck or bad timing — it was me. And if it happens again, that's confirmation.",
    "I think that's why I surround myself with busy-ness. If I'm always working on something, always in motion, I don't have to sit with that question.",
    "Maybe. But it's also lonely. I don't let people see the doubt. Everyone thinks I'm the confident one, the one who has it figured out. And I play that role because if they saw the real version...",
    "They'd lose faith in me. And then I'd lose the one thing I have — people believing I can do this. Without that, what am I?",
    "That's heavy. I don't think anyone's ever asked me that so directly. I guess I'd have to figure out who I am without the performance.",
    "Honestly? I have no idea. And that terrifies me more than any startup failing.",
]


def get_test_token() -> str:
    """Create a test user via Supabase admin API and get an access token."""
    # Use admin API to create/sign-in a test user
    test_email = os.environ.get("TEST_EMAIL", "test-reflect@thinkpod.local")
    test_password = os.environ.get("TEST_PASSWORD", "test-reflect-pw-" + SUPABASE_SERVICE_KEY[:8])

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # Try to sign in first
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": test_email, "password": test_password},
    )

    if resp.status_code == 200:
        return resp.json()["access_token"]

    # Create user via admin API
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=headers,
        json={
            "email": test_email,
            "password": test_password,
            "email_confirm": True,
        },
    )
    if resp.status_code not in (200, 201):
        # User might already exist but password wrong — try updating
        print(f"Create user response: {resp.status_code} {resp.text}")
        sys.exit(1)

    # Now sign in
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": test_email, "password": test_password},
    )
    if resp.status_code != 200:
        print(f"Sign-in failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    return resp.json()["access_token"]


def run_test(base_url: str, num_turns: int):
    print("=" * 60)
    print("Think-Pod Deep Reflection — E2E Test")
    print("=" * 60)

    # 1. Get auth token
    print("\n[1] Authenticating...")
    token = get_test_token()
    print(f"    ✓ Got JWT token ({len(token)} chars)")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 2. Start session with reflect=true
    print("\n[2] Starting reflection session...")
    resp = requests.post(
        f"{base_url}/api/session/start",
        headers=headers,
        json={
            "guest_name": "TestGuest",
            "topic": "commitment, fear of failure, and identity",
            "podcaster": "chris-williamson",
            "text_only": True,
            "reflect": True,
        },
    )
    if resp.status_code != 200:
        print(f"    ✗ Start failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    session_id = data["session_id"]
    reflect_flag = data.get("reflect", False)
    print(f"    ✓ Session: {session_id}")
    print(f"    ✓ Reflect: {reflect_flag}")
    print(f"    ✓ Greeting: {data['greeting_text'][:100]}...")

    if not reflect_flag:
        print("    ✗ REFLECT FLAG IS FALSE — this is the bug!")
        sys.exit(1)

    # 3. Run conversation turns
    checkpoint_interval = 8
    checkpoints_expected = 0
    turns_to_run = min(num_turns, len(GUEST_RESPONSES))

    print(f"\n[3] Running {turns_to_run} conversation turns...")
    for i in range(turns_to_run):
        turn_num = i + 1
        is_checkpoint = turn_num > 0 and turn_num % checkpoint_interval == 0
        if is_checkpoint:
            checkpoints_expected += 1

        marker = " ⚡ CHECKPOINT" if is_checkpoint else ""
        print(f"\n    Turn {turn_num}/{turns_to_run}{marker}")
        print(f"    Guest: {GUEST_RESPONSES[i][:60]}...")

        t0 = time.time()
        resp = requests.post(
            f"{base_url}/api/session/{session_id}/chat-text",
            headers=headers,
            json={
                "text": GUEST_RESPONSES[i],
                "text_only": True,
            },
        )
        elapsed = time.time() - t0

        if resp.status_code != 200:
            print(f"    ✗ Chat failed: {resp.status_code} {resp.text}")
            sys.exit(1)

        chat_data = resp.json()
        print(f"    Host: {chat_data['chris_text'][:80]}...")
        print(f"    ({elapsed:.1f}s, turn={chat_data['turn']})")

        if is_checkpoint:
            print(f"    → Checkpoint should have fired (turn {turn_num})")

    # 4. End session
    print(f"\n[4] Ending session...")
    t0 = time.time()
    resp = requests.post(
        f"{base_url}/api/session/{session_id}/end",
        headers=headers,
    )
    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f"    ✗ End failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    end_data = resp.json()
    print(f"    ✓ Ended in {elapsed:.1f}s")
    print(f"    ✓ Turns: {end_data['turns']}")
    print(f"    ✓ Reflect: {end_data.get('reflect', 'MISSING')}")
    print(f"    ✓ Analysis: {'YES (' + str(len(end_data.get('analysis') or '')) + ' chars)' if end_data.get('analysis') else 'NONE'}")

    # 5. Verify artifacts
    print(f"\n[5] Verifying artifacts...")

    # Check analysis endpoint
    resp = requests.get(
        f"{base_url}/api/sessions/{session_id}/analysis",
        headers=headers,
    )
    if resp.status_code == 200:
        print(f"    ✓ Analysis endpoint returns data")
    else:
        print(f"    ✗ Analysis endpoint: {resp.status_code}")

    # Check files
    session_dir = os.path.join(BASE_DIR, "data", "sessions")
    patterns_dir = os.path.join(BASE_DIR, "data", "patterns")

    transcript_file = os.path.join(session_dir, f"{session_id}.md")
    analysis_file = os.path.join(session_dir, f"{session_id}-analysis.md")
    checkpoint_file = os.path.join(session_dir, f"{session_id}-checkpoints.md")

    for label, path in [
        ("Transcript", transcript_file),
        ("Analysis", analysis_file),
        ("Checkpoints", checkpoint_file),
    ]:
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"    ✓ {label}: {path} ({size} bytes)")
        else:
            print(f"    ✗ {label}: NOT FOUND at {path}")

    # Check pattern file
    pattern_files = [f for f in os.listdir(patterns_dir) if session_id in f]
    if pattern_files:
        print(f"    ✓ Pattern: {pattern_files[0]}")
    else:
        print(f"    ✗ Pattern: NOT FOUND for session {session_id}")

    # 6. Check DB state
    print(f"\n[6] Checking DB state...")
    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    db_session = client.table("sessions").select("*").eq("id", session_id).execute()
    if db_session.data:
        row = db_session.data[0]
        print(f"    ✓ DB session exists")
        print(f"    ✓ DB reflect: {row.get('reflect', 'MISSING')}")
        print(f"    ✓ DB status: {row.get('status')}")
        print(f"    ✓ DB turns: {row.get('turns')}")
    else:
        print(f"    ✗ DB session NOT FOUND")

    # Check system messages (checkpoints)
    msgs = client.table("messages").select("*").eq("session_id", session_id).eq("role", "system").execute()
    print(f"    ✓ DB checkpoint messages: {len(msgs.data)}")
    for m in msgs.data:
        print(f"      - turn {m['turn_number']}: {m['content'][:80]}...")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    issues = []
    if not end_data.get("reflect"):
        issues.append("reflect=false in end response")
    if not end_data.get("analysis"):
        issues.append("no post-session analysis generated")
    if checkpoints_expected > 0 and len(msgs.data) == 0:
        issues.append(f"expected {checkpoints_expected} checkpoints, found 0 in DB")
    if checkpoints_expected > 0 and not os.path.exists(checkpoint_file):
        issues.append("checkpoint log file not created")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  ✗ {issue}")
    else:
        print("✓ ALL CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E test for Think-Pod reflection mode")
    parser.add_argument("--turns", type=int, default=12, help="Number of conversation turns")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API base URL")
    args = parser.parse_args()

    run_test(args.base_url, args.turns)
