import requests
import json
import re
from pathlib import Path
import urllib3

urllib3.disable_warnings()

HEADERS = {
    "User-Agent": "OTT Navigator/1.6.7 (Linux; Android 12)",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive"
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------- NORMALIZER (CRITICAL) ----------
def normalize(text):
    if not text:
        return ""

    text = text.upper().strip()

    # Remove language prefixes
    text = re.sub(r'^(HINDI|IN)\s*-\s*', '', text)

    # Replace AND → &
    text = text.replace("AND TV", "&TV")
    text = text.replace("AND PICTURES", "&PICTURES")
    text = text.replace("AND XPLOR", "&XPLOLOR")
    text = text.replace("AND", "&")

    # Remove symbols
    text = re.sub(r'[◉²™®]', '', text)

    # Remove junk words
    text = re.sub(r'\b(LIVE|CHANNEL|INDIA)\b', '', text)

    # Remove spaces & non-alphanum
    text = re.sub(r'[^A-Z0-9&]', '', text)

    return text.lower()

# ---------- LOAD MASTER CHANNELS ----------
with open("indian-channels.json", "r", encoding="utf-8") as f:
    channels = json.load(f)["channels"]

search_index = []
for ch in channels:
    keys = set()
    keys.add(normalize(ch["name"]))
    for a in ch.get("aliases", []):
        keys.add(normalize(a))
    search_index.append((ch, keys))

found_lcn = set()
final_entries = []

# ---------- READ PLAYLIST URLS ----------
with open("playlists.txt") as f:
    urls = [u.strip() for u in f if u.strip()]

for url in urls:
    print("Fetching:", url)
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
            verify=False
        )
        if r.status_code != 200:
            print("HTTP error:", r.status_code)
            continue
        lines = r.text.splitlines()
    except Exception as e:
        print("Download failed:", e)
        continue

    extinf = None

    for line in lines:
        if line.startswith("#EXTINF"):
            extinf = line
            continue

        if not line.startswith("http") or not extinf:
            continue

        # Extract channel name
        name_match = re.search(r',(.+)$', extinf)
        if not name_match:
            extinf = None
            continue

        raw_name = name_match.group(1).strip()
        norm_name = normalize(raw_name)

        for ch, keys in search_index:
            if ch["lcn"] in found_lcn:
                continue

            if any(k in norm_name or norm_name in k for k in keys):
                found_lcn.add(ch["lcn"])

                entry = (
                    f'#EXTINF:-1 '
                    f'tvg-name="{ch["name"]}" '
                    f'group-title="{ch["category"]}",'
                    f'{ch["lcn"]}. {ch["name"]}\n'
                    f'{line}\n'
                )

                final_entries.append((ch["lcn"], entry))
                print("MATCH:", raw_name, "->", ch["name"])
                break

        extinf = None

# ---------- SORT & WRITE ----------
final_entries.sort(key=lambda x: x[0])

with open(OUTPUT_DIR / "final.m3u", "w", encoding="utf-8") as f:
    f.write("#EXTM3U\n")
    for _, entry in final_entries:
        f.write(entry)

print("DONE. Channels found:", len(final_entries))
