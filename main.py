import requests
import json
import re
import concurrent.futures
from pathlib import Path
import urllib3

urllib3.disable_warnings()

# --- CONFIG ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Connection": "keep-alive"
}
TIMEOUT = 10  # Seconds to wait for a stream to respond

# --- 1. ROBUST NORMALIZER ---
def normalize(text):
    if not text:
        return ""
    text = text.upper().strip()
    # Remove common junk
    text = re.sub(r'\b(TV|CHANNEL|LIVE|STREAM|FHD|HD|SD|HEVC|HINDI|INDIA|IN)\b', '', text)
    text = re.sub(r'[^A-Z0-9]', '', text) # Keep ONLY alphabets and numbers
    return text

# --- 2. LINK VALIDATOR ---
def is_stream_working(url):
    try:
        # We use stream=True to just get the headers, not download the video
        with requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True, verify=False) as r:
            if r.status_code == 200:
                return True
    except:
        return False
    return False

# --- LOAD DATA ---
with open("indian-channels.json", "r", encoding="utf-8") as f:
    channels = json.load(f)["channels"]

# Build search index
# structure: { "NORMALIZED_NAME": channel_obj, "ALIAS_NORM": channel_obj }
channel_map = {}
for ch in channels:
    # Main name
    norm = normalize(ch["name"])
    if norm: channel_map[norm] = ch
    
    # Aliases
    for alias in ch.get("aliases", []):
        norm_alias = normalize(alias)
        if norm_alias: channel_map[norm_alias] = ch

found_lcn = set()
final_entries = []
candidates = [] # Store potential matches to validate later

# --- READ PLAYLISTS ---
with open("playlists.txt", "r", encoding="utf-8") as f:
    urls = [u.strip() for u in f if u.strip()]

print(f"Loading {len(urls)} playlists...")

# Collect all potential streams
for url in urls:
    try:
        print(f"Scraping: {url}")
        r = requests.get(url, timeout=30, verify=False)
        lines = r.text.splitlines()
        
        extinf = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                extinf = line
                continue
            
            if line.startswith("http") and extinf:
                # Extract name
                name_match = re.search(r',(.+)$', extinf)
                if name_match:
                    raw_name = name_match.group(1).split(',')[0].strip() # Fix for some formats
                    norm_name = normalize(raw_name)
                    
                    # EXACT MATCH CHECK
                    if norm_name in channel_map:
                        ch_data = channel_map[norm_name]
                        # Only add if we haven't found a working link for this LCN yet
                        # We store ALL candidates to validate them in parallel
                        candidates.append({
                            "lcn": ch_data["lcn"],
                            "data": ch_data,
                            "url": line,
                            "raw_name": raw_name
                        })
                extinf = None
    except Exception as e:
        print(f"Error reading playlist {url}: {e}")

print(f"Found {len(candidates)} potential streams. Validating...")

# --- VALIDATE STREAMS (PARALLEL) ---
# We group candidates by LCN so we can stop checking an LCN once we find a working one
candidates_by_lcn = {}
for c in candidates:
    if c["lcn"] not in candidates_by_lcn:
        candidates_by_lcn[c["lcn"]] = []
    candidates_by_lcn[c["lcn"]].append(c)

working_count = 0

def check_channel_group(lcn, stream_list):
    # Try streams for this channel until one works
    for item in stream_list:
        if is_stream_working(item["url"]):
            return (lcn, item)
    return (lcn, None)

# Use ThreadPool to check multiple channels at once
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    # Submit one job per LCN
    future_to_lcn = {
        executor.submit(check_channel_group, lcn, streams): lcn 
        for lcn, streams in candidates_by_lcn.items()
    }
    
    for future in concurrent.futures.as_completed(future_to_lcn):
        lcn, result = future.result()
        if result:
            ch = result["data"]
            # Create the Perfect Entry
            logo = ch.get("logo", "")
            tvg_id = ch.get("tvg_id", "")
            
            entry = (
                f'#EXTINF:-1 '
                f'tvg-id="{tvg_id}" '
                f'tvg-name="{ch["name"]}" '
                f'tvg-logo="{logo}" '
                f'group-title="{ch["category"]}",'
                f'{ch["name"]}\n'
                f'{result["url"]}\n'
            )
            final_entries.append((lcn, entry))
            working_count += 1
            print(f"✅ [LCN {lcn}] {ch['name']} -> WORKING")
        else:
            print(f"❌ [LCN {lcn}] No working streams found.")

# --- WRITE OUTPUT ---
final_entries.sort(key=lambda x: x[0])
output_file = Path("channels.m3u")
with open(output_file, "w", encoding="utf-8") as f:
    f.write("#EXTM3U\n")
    for _, entry in final_entries:
        f.write(entry)

print("------------------------------------------------")
print(f"Final Playlist: {len(final_entries)} channels")
print(f"Saved to: {output_file.resolve()}")
