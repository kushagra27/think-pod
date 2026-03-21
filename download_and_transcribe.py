#!/usr/bin/env python3
"""Download Modern Wisdom episodes from RSS and transcribe with faster-whisper."""

import xml.etree.ElementTree as ET
import requests
import os
import json
import time
import re
import subprocess

RSS_URL = "https://feeds.megaphone.fm/SIXMSB5088139739"
BASE_DIR = "/root/.openclaw/workspace/projects/podcast-thinking"
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "transcripts/chris-williamson")
INDEX_FILE = os.path.join(TRANSCRIPT_DIR, "_index.json")

# How many episodes to process
MAX_EPISODES = 8

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

NAMESPACES = {
    'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
}


def parse_rss():
    """Parse RSS feed and return episode list."""
    print("Fetching RSS feed...")
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
        
        # Create safe filename
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s]+', '-', slug).strip('-')[:80]
        
        episodes.append({
            'title': title,
            'slug': slug,
            'audio_url': audio_url,
            'duration_sec': duration_sec,
            'pub_date': pub_date,
            'episode_num': ep_num,
        })
    
    print(f"Found {len(episodes)} episodes in RSS feed")
    return episodes


def download_audio(episode):
    """Download audio file, return path."""
    filename = f"{episode['slug']}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    
    if os.path.exists(filepath):
        print(f"  Already downloaded: {filename}")
        return filepath
    
    print(f"  Downloading: {episode['title'][:60]}...")
    resp = requests.get(episode['audio_url'], stream=True, timeout=60)
    resp.raise_for_status()
    
    with open(filepath, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"    ✓ Downloaded ({size_mb:.1f} MB)")
    return filepath


def transcribe_audio(audio_path, episode, model):
    """Transcribe audio file using faster-whisper."""
    transcript_file = os.path.join(TRANSCRIPT_DIR, f"{episode['slug']}.txt")
    
    if os.path.exists(transcript_file):
        print(f"  Already transcribed: {episode['slug']}")
        return transcript_file
    
    print(f"  Transcribing: {episode['title'][:60]}...")
    print(f"    (duration: {episode['duration_sec']//60}min - this will take a while on CPU)")
    
    segments, info = model.transcribe(audio_path, language="en", beam_size=3)
    
    lines = []
    lines.append(f"# {episode['title']}")
    lines.append(f"# Date: {episode['pub_date']}")
    lines.append(f"# Duration: {episode['duration_sec']//60} minutes")
    lines.append(f"# Language: {info.language} (prob: {info.language_probability:.2f})")
    lines.append("")
    
    for segment in segments:
        timestamp = f"[{int(segment.start//60):02d}:{int(segment.start%60):02d}]"
        lines.append(f"{timestamp} {segment.text.strip()}")
    
    with open(transcript_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"    ✓ Transcribed → {transcript_file}")
    return transcript_file


def main():
    episodes = parse_rss()
    
    # Load existing index
    index = {}
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            index = json.load(f)
    
    # Process most recent episodes first
    to_process = [e for e in episodes if e['slug'] not in index][:MAX_EPISODES]
    print(f"\nWill process {len(to_process)} episodes")

    from faster_whisper import WhisperModel
    print("Loading Whisper model once for batch run...")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    
    for i, episode in enumerate(to_process):
        print(f"\n[{i+1}/{len(to_process)}] {episode['title']}")
        
        try:
            # Download
            audio_path = download_audio(episode)
            
            # Transcribe
            transcript_path = transcribe_audio(audio_path, episode, model)
            
            # Update index
            index[episode['slug']] = {
                'title': episode['title'],
                'episode_num': episode['episode_num'],
                'pub_date': episode['pub_date'],
                'duration_sec': episode['duration_sec'],
                'transcript_file': transcript_path,
                'audio_file': audio_path,
            }
            
            # Save index after each episode
            with open(INDEX_FILE, 'w') as f:
                json.dump(index, f, indent=2)
            
            # Clean up audio to save disk space
            # Keep audio files for now (useful for voice cloning later)
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue
    
    print(f"\n{'='*60}")
    print(f"Done! Total transcripts: {len(index)}")
    print(f"Index: {INDEX_FILE}")


if __name__ == "__main__":
    main()
