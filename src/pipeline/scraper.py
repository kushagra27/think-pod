#!/usr/bin/env python3
"""Scrape Modern Wisdom transcripts from podscripts.co"""

import requests
import re
import os
import time
import json
from html import unescape

BASE_URL = "https://podscripts.co/podcasts/modern-wisdom/"
OUT_DIR = "/root/.openclaw/workspace/projects/podcast-thinking/data/transcripts/chris-williamson"
INDEX_FILE = os.path.join(OUT_DIR, "_index.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def get_episode_list(page=1):
    """Get list of episode slugs from the podcast page."""
    if page == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}?page={page}"
    
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    # Find episode links
    pattern = r'/podcasts/modern-wisdom/([\w\d-]+)'
    slugs = list(set(re.findall(pattern, resp.text)))
    return slugs


def get_transcript(slug):
    """Fetch full transcript for an episode."""
    url = f"{BASE_URL}{slug}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    # Extract title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', resp.text, re.DOTALL)
    title = unescape(title_match.group(1).strip()) if title_match else slug
    
    # Extract transcript text - look for the transcript content
    # The transcript is in timestamped blocks
    blocks = re.findall(r'Starting point is (\d{2}:\d{2}:\d{2})\s*\n(.*?)(?=Starting point is|\Z)', resp.text, re.DOTALL)
    
    if not blocks:
        # Try alternate pattern
        blocks = re.findall(r'(\d{2}:\d{2}:\d{2})\s*\n(.*?)(?=\d{2}:\d{2}:\d{2}|\Z)', resp.text, re.DOTALL)
    
    transcript_lines = []
    for timestamp, text in blocks:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        clean_text = re.sub(r'\s+', ' ', clean_text)
        if clean_text:
            transcript_lines.append(f"[{timestamp}] {clean_text}")
    
    return {
        "title": title,
        "slug": slug,
        "url": url,
        "transcript": "\n\n".join(transcript_lines),
        "block_count": len(transcript_lines)
    }


def main():
    # Load existing index
    index = {}
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            index = json.load(f)
    
    # Get episode slugs (first 5 pages to start)
    all_slugs = []
    for page in range(1, 6):
        print(f"Fetching episode list page {page}...")
        slugs = get_episode_list(page)
        if not slugs:
            break
        all_slugs.extend(slugs)
        time.sleep(1)
    
    all_slugs = list(set(all_slugs))
    print(f"Found {len(all_slugs)} unique episodes")
    
    # Download transcripts
    downloaded = 0
    for slug in sorted(all_slugs):
        if slug in index:
            continue
        
        filepath = os.path.join(OUT_DIR, f"{slug}.txt")
        if os.path.exists(filepath):
            continue
        
        try:
            print(f"  Downloading: {slug}")
            data = get_transcript(slug)
            
            if data["transcript"]:
                with open(filepath, "w") as f:
                    f.write(f"# {data['title']}\n")
                    f.write(f"# Source: {data['url']}\n\n")
                    f.write(data["transcript"])
                
                index[slug] = {
                    "title": data["title"],
                    "blocks": data["block_count"],
                    "file": filepath
                }
                downloaded += 1
                print(f"    ✓ {data['block_count']} blocks")
            else:
                print(f"    ✗ No transcript found")
            
            time.sleep(1.5)  # Be polite
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
            time.sleep(2)
    
    # Save index
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)
    
    print(f"\nDone! Downloaded {downloaded} new transcripts. Total: {len(index)}")


if __name__ == "__main__":
    main()
