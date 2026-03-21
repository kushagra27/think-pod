#!/usr/bin/env python3
"""Download Modern Wisdom episodes from RSS and transcribe with Groq Whisper API."""

import xml.etree.ElementTree as ET
import requests
import os
import json
import time
import re
import subprocess
import sys

RSS_URL = "https://feeds.megaphone.fm/SIXMSB5088139739"
BASE_DIR = "/root/.openclaw/workspace/projects/podcast-thinking"
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "transcripts/chris-williamson")
INDEX_FILE = os.path.join(TRANSCRIPT_DIR, "_index.json")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

MAX_EPISODES = 30
CHUNK_DURATION_SEC = 600  # 10-minute chunks (well under 25MB at 48kbps)

NAMESPACES = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)


def parse_rss():
    """Parse RSS feed and return episode list."""
    print("Fetching RSS feed...", flush=True)
    resp = requests.get(RSS_URL, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    episodes = []
    for item in root.findall('.//item'):
        title = item.find('title').text or ""
        enclosure = item.find('enclosure')
        if enclosure is None:
            continue
        audio_url = enclosure.get('url', '')
        duration = item.find('itunes:duration', NAMESPACES)
        duration_sec = int(duration.text) if duration is not None and duration.text.isdigit() else 0
        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
        ep_num = item.find('itunes:episode', NAMESPACES)
        ep_num = int(ep_num.text) if ep_num is not None and ep_num.text.isdigit() else 0
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s]+', '-', slug).strip('-')[:80]
        episodes.append({
            'title': title, 'slug': slug, 'audio_url': audio_url,
            'duration_sec': duration_sec, 'pub_date': pub_date, 'episode_num': ep_num,
        })
    print(f"Found {len(episodes)} episodes in RSS feed", flush=True)
    return episodes


def download_audio(episode):
    """Download audio file."""
    filename = f"{episode['slug']}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(f"  Already downloaded: {filename}", flush=True)
        return filepath
    print(f"  Downloading: {episode['title'][:60]}...", flush=True)
    resp = requests.get(episode['audio_url'], stream=True, timeout=120)
    resp.raise_for_status()
    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"    ✓ Downloaded ({size_mb:.1f} MB)", flush=True)
    return filepath


def split_audio(audio_path, episode):
    """Split audio into chunks and convert to mono 16kHz for smaller files."""
    chunk_dir = os.path.join(AUDIO_DIR, "chunks", episode['slug'])
    os.makedirs(chunk_dir, exist_ok=True)
    
    # Check if chunks already exist
    existing = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.mp3')])
    if existing:
        return [os.path.join(chunk_dir, f) for f in existing]
    
    duration = episode['duration_sec']
    if duration == 0:
        # Get duration from ffprobe
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True
        )
        duration = int(float(result.stdout.strip()))
    
    chunks = []
    for start in range(0, duration, CHUNK_DURATION_SEC):
        chunk_idx = start // CHUNK_DURATION_SEC
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx:03d}.mp3")
        subprocess.run([
            'ffmpeg', '-i', audio_path,
            '-ss', str(start), '-t', str(CHUNK_DURATION_SEC),
            '-ac', '1', '-ar', '16000', '-b:a', '48k',
            '-y', '-loglevel', 'error', chunk_path
        ], check=True)
        chunks.append(chunk_path)
    
    print(f"    Split into {len(chunks)} chunks", flush=True)
    return chunks


def transcribe_chunk_groq(chunk_path, retries=3):
    """Transcribe a single chunk using Groq Whisper API."""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    
    for attempt in range(retries):
        try:
            with open(chunk_path, 'rb') as f:
                resp = requests.post(
                    url, headers=headers,
                    files={"file": (os.path.basename(chunk_path), f, "audio/mpeg")},
                    data={
                        "model": "whisper-large-v3",
                        "response_format": "verbose_json",
                        "language": "en",
                    },
                    timeout=120
                )
            
            if resp.status_code == 429:
                wait = int(resp.headers.get('retry-after', 30))
                print(f"    Rate limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            
            resp.raise_for_status()
            return resp.json()
        
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt+1}: {e}", flush=True)
                time.sleep(5 * (attempt + 1))
            else:
                raise
    return None


def transcribe_episode(audio_path, episode):
    """Transcribe full episode using Groq API with chunking."""
    transcript_file = os.path.join(TRANSCRIPT_DIR, f"{episode['slug']}.txt")
    if os.path.exists(transcript_file) and os.path.getsize(transcript_file) > 100:
        print(f"  Already transcribed: {episode['slug']}", flush=True)
        return transcript_file
    
    print(f"  Splitting audio into chunks...", flush=True)
    chunks = split_audio(audio_path, episode)
    
    print(f"  Transcribing {len(chunks)} chunks via Groq API...", flush=True)
    
    lines = []
    lines.append(f"# {episode['title']}")
    lines.append(f"# Date: {episode['pub_date']}")
    lines.append(f"# Duration: {episode['duration_sec']//60} minutes")
    lines.append(f"# Episode: {episode['episode_num']}")
    lines.append("")
    
    for i, chunk_path in enumerate(chunks):
        chunk_offset = i * CHUNK_DURATION_SEC
        print(f"    Chunk {i+1}/{len(chunks)}...", flush=True)
        
        result = transcribe_chunk_groq(chunk_path)
        if result and 'segments' in result:
            for seg in result['segments']:
                abs_start = chunk_offset + seg['start']
                mins = int(abs_start // 60)
                secs = int(abs_start % 60)
                text = seg['text'].strip()
                if text:
                    lines.append(f"[{mins:02d}:{secs:02d}] {text}")
        elif result and 'text' in result:
            abs_mins = chunk_offset // 60
            lines.append(f"[{abs_mins:02d}:00] {result['text']}")
        
        # Small delay between chunks to avoid rate limits
        time.sleep(1)
    
    with open(transcript_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"    ✓ Transcribed → {transcript_file}", flush=True)
    return transcript_file


def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set", flush=True)
        sys.exit(1)
    
    episodes = parse_rss()
    
    index = {}
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            index = json.load(f)
    
    to_process = [e for e in episodes if e['slug'] not in index][:MAX_EPISODES]
    print(f"\nWill process {len(to_process)} episodes", flush=True)
    
    for i, episode in enumerate(to_process):
        print(f"\n[{i+1}/{len(to_process)}] {episode['title']}", flush=True)
        t0 = time.time()
        
        try:
            audio_path = download_audio(episode)
            transcript_path = transcribe_episode(audio_path, episode)
            
            index[episode['slug']] = {
                'title': episode['title'],
                'episode_num': episode['episode_num'],
                'pub_date': episode['pub_date'],
                'duration_sec': episode['duration_sec'],
                'transcript_file': transcript_path,
            }
            
            with open(INDEX_FILE, 'w') as f:
                json.dump(index, f, indent=2)
            
            elapsed = time.time() - t0
            print(f"  Done in {elapsed:.0f}s", flush=True)
            
            # Clean up audio after successful transcription to save disk
            # Keep first 5 episodes' audio for voice cloning later
            if i >= 5:
                os.remove(audio_path)
                print(f"  Cleaned up audio to save disk", flush=True)
        
        except Exception as e:
            print(f"  ✗ Error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}", flush=True)
    print(f"Done! Total transcripts: {len(index)}", flush=True)


if __name__ == "__main__":
    main()
