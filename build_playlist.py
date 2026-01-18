import requests
import json
import re
from pathlib import Path

UA = {
    "User-Agent": "OTT Navigator/1.6.5 (Linux;Android 12)"
}

BASE = Path(".")
OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)

def normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

# Load channels master data
with open("indian-channels.json", "r", encoding="utf-8") as f:
    data = json.load(f)["channels"]

channels_index = {}
for ch in data:
    keys = set()
    keys.add(normalize(ch["name"]))
    for a in ch.get("aliases", []):
        keys.add(normalize(a))
    for t in ch.get("tvgIds", []):
        keys.add(normalize(t))
    for k in keys:
        channels_index[k] = ch

found = {}
final_entries = []

# Read playlists
with open("playlists.txt") as f:
    urls = [l.strip() for l in f if l.strip()]

for url in urls:
    print("Fetching:", url)
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200:
            continue
        content = r.text.splitlines()
    except Exception as e:
        print("Failed:", e)
        continue

    current_extinf = None

    for line in content:
        if line.startswith("#EXTINF"):
            current_extinf = line
        elif line.startswith("http") and current_extinf:
            name_match = re.search(r',(.+)$', current_extinf)
            tvg_id = re.search(r'tvg-id="([^"]*)"', current_extinf)
            tvg_logo = re.search(r'tvg-logo="([^"]*)"', current_extinf)

            name = name_match.group(1).strip() if name_match else ""
            key = normalize(name)

            if key not in channels_index:
                continue

            ch = channels_index[key]
            if ch["lcn"] in found:
                continue  # already found from higher priority playlist

            found[ch["lcn"]] = True

            entry = (
                f'#EXTINF:-1 tvg-id="{ch["tvgIds"][0]}" '
                f'tvg-name="{ch["name"]}" '
                f'tvg-logo="{tvg_logo.group(1) if tvg_logo else ""}" '
                f'group-title="{ch["category"]}",'
                f'{ch["lcn"]}. {ch["name"]}\n'
                f'{line}\n'
            )

            final_entries.append((ch["lcn"], entry))
            current_extinf = None

# Sort by LCN
final_entries.sort(key=lambda x: x[0])

# Write final playlist
with open(OUTPUT / "final.m3u", "w", encoding="utf-8") as f:
    f.write("#EXTM3U\n")
    for _, entry in final_entries:
        f.write(entry)

print("DONE. Channels:", len(final_entries))
