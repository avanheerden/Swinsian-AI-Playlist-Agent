#!/usr/bin/env python3
"""
Swinsian AI Playlist Agent
Generates playlists in Swinsian based on natural language prompts using Claude.

Usage:
    python swinsian_agent.py "build me a playlist of 100 songs that rock and surprise"
    python swinsian_agent.py  # interactive mode
"""

import subprocess
import json
import sys
import re
import math
import random
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
MAX_TRACKS_FULL    = 1500   # send full metadata up to this size
MAX_TRACKS_COMPACT = 4000   # send compact catalog (id|title|artist) up to this size
CLAUDE_MODEL       = "claude-haiku-4-5-20251001"
# ─────────────────────────────────────────────────────────────────────────────


def run_applescript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
    return result.stdout.strip()


def is_swinsian_running() -> bool:
    try:
        out = run_applescript(
            'tell application "System Events" to return (name of processes) contains "Swinsian"'
        )
        return out.strip().lower() == "true"
    except Exception:
        return False


def get_library_tracks() -> list[dict]:
    """Fetch all tracks from Swinsian using fast bulk property fetching."""
    print("📚 Reading your Swinsian library…", flush=True)

    def fetch_property(prop: str) -> list[str]:
        script = f'''
tell application "Swinsian"
    set vals to {prop} of every track
    set AppleScript's text item delimiters to "~~~"
    set output to vals as string
    set AppleScript's text item delimiters to ""
    return output
end tell
'''
        raw = run_applescript(script)
        return raw.split("~~~") if raw else []

    print("   Fetching names…",       flush=True)
    names   = fetch_property("name")
    print("   Fetching artists…",     flush=True)
    artists = fetch_property("artist")
    print("   Fetching albums…",      flush=True)
    albums  = fetch_property("album")
    print("   Fetching genres…",      flush=True)
    genres  = fetch_property("genre")
    print("   Fetching years…",       flush=True)
    years   = fetch_property("year")
    print("   Fetching ratings…",     flush=True)
    ratings = fetch_property("rating")
    print("   Fetching play counts…", flush=True)
    plays   = fetch_property("play count")

    tracks = []
    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        tracks.append({
            "id":     i,
            "title":  name,
            "artist": artists[i].strip() if i < len(artists) else "",
            "album":  albums[i].strip()  if i < len(albums)  else "",
            "genre":  genres[i].strip()  if i < len(genres)  else "",
            "year":   years[i].strip()   if i < len(years)   else "",
            "rating": ratings[i].strip() if i < len(ratings) else "",
            "plays":  plays[i].strip()   if i < len(plays)   else "",
        })
    return tracks


def build_full_catalog(tracks: list[dict]) -> str:
    lines = [f'{t["id"]}|{t["title"]}|{t["artist"]}|{t["album"]}|{t["genre"]}|{t["year"]}|★{t["rating"]}|▶{t["plays"]}' for t in tracks]
    return "\n".join(lines)


def build_compact_catalog(tracks: list[dict]) -> str:
    lines = [f'{t["id"]}|{t["title"]}|{t["artist"]}' for t in tracks]
    return "\n".join(lines)


def ask_claude_for_playlist(prompt: str, tracks: list[dict]) -> tuple[str, list[int], str]:
    client = anthropic.Anthropic()
    total  = len(tracks)

    if total <= MAX_TRACKS_FULL:
        catalog      = build_full_catalog(tracks)
        catalog_desc = "id|title|artist|album|genre|year|rating|plays"
        print(f"   Sending full metadata for {total:,} tracks to Claude…", flush=True)
    elif total <= MAX_TRACKS_COMPACT:
        catalog      = build_compact_catalog(tracks)
        catalog_desc = "id|title|artist"
        print(f"   Sending compact catalog for {total:,} tracks to Claude…", flush=True)
    else:
        print(f"   Sampling {MAX_TRACKS_COMPACT:,} tracks from your {total:,}-track library…", flush=True)
        by_plays = sorted(tracks, key=lambda x: int(x["plays"] or 0), reverse=True)
        top      = by_plays[:MAX_TRACKS_COMPACT // 2]
        rest     = by_plays[MAX_TRACKS_COMPACT // 2:]
        random.shuffle(rest)
        tracks   = top + rest[:MAX_TRACKS_COMPACT - len(top)]
        catalog      = build_compact_catalog(tracks)
        catalog_desc = "id|title|artist"

    system = """You are an expert music curator with encyclopedic knowledge of genres, moods, eras, artists, and song characteristics.
You will receive a user's music library and a playlist request.
Your job: select the best tracks from the library to fulfil the request.

Rules:
- Return ONLY a JSON object in this exact format (no markdown, no extra text):
  {"playlist_name": "...", "ids": [id1, id2, ...], "rationale": "one sentence"}
- The ids must be integers from the catalog's first column.
- Honour quantity requests (e.g. "100 songs") as closely as possible given the library size.
- Prioritise variety, curation quality, and faithfulness to the request.
- If the library doesn't have enough matching tracks, pick the closest alternatives and note it in the rationale."""

    user_message = f"User request: {prompt}\n\nLibrary catalog ({catalog_desc}):\n{catalog}"

    print("🤖 Asking Claude to curate your playlist…", flush=True)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Claude returned unexpected format:\n{raw}")

    return data.get("playlist_name", "AI Playlist"), data.get("ids", []), data.get("rationale", "")


def create_swinsian_playlist(playlist_name: str, track_ids: list[int], all_tracks: list[dict]):
    id_to_track = {t["id"]: t for t in all_tracks}
    selected    = [id_to_track[i] for i in track_ids if i in id_to_track]
    random.shuffle(selected)  # randomise order before adding to Swinsian

    if not selected:
        print("⚠️  No matching tracks found in library to add.")
        return 0

    print(f"🎵 Creating playlist '{playlist_name}' with {len(selected)} tracks…", flush=True)

    # Create playlist via File menu (make new playlist not supported via AppleScript)
    safe_name = playlist_name.replace("\\", "\\\\").replace('"', '\\"')
    run_applescript(f'''
tell application "Swinsian" to activate
delay 0.5
tell application "System Events"
    tell process "Swinsian"
        click menu item "New Playlist" of menu "File" of menu bar 1
        delay 0.5
        keystroke "{safe_name}"
        key code 36
    end tell
end tell''')

    # Add tracks in small batches using Swinsian's native `add tracks {} to` command
    BATCH   = 50
    added   = 0
    batches = math.ceil(len(selected) / BATCH)

    for b in range(batches):
        chunk = selected[b * BATCH:(b + 1) * BATCH]
        inner = []
        for t in chunk:
            safe_title  = t["title"].replace("\\", "\\\\").replace('"', '\\"')
            safe_artist = t["artist"].replace("\\", "\\\\").replace('"', '\\"')
            inner.append(f'''
        set found to (every track whose name is "{safe_title}" and artist is "{safe_artist}")
        if (count of found) > 0 then add tracks {{item 1 of found}} to normal playlist "{safe_name}"''')

        batch_script = 'tell application "Swinsian"\n' + "\n".join(inner) + '\nend tell'
        run_applescript(batch_script)
        added += len(chunk)
        print(f"   Added {min(added, len(selected))}/{len(selected)} tracks…", flush=True)

    return len(selected)


def main():
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        print("🎧 Swinsian AI Playlist Agent")
        print("─" * 40)
        prompt = input("What kind of playlist would you like?\n> ").strip()
        if not prompt:
            print("No prompt given. Exiting.")
            sys.exit(1)

    print(f"\n✨ Prompt: \"{prompt}\"")
    print()

    if not is_swinsian_running():
        print("❌ Swinsian doesn't appear to be running. Please open Swinsian and try again.")
        sys.exit(1)

    try:
        tracks = get_library_tracks()
    except RuntimeError as e:
        print(f"❌ Could not read Swinsian library: {e}")
        sys.exit(1)

    if not tracks:
        print("❌ Your Swinsian library appears to be empty.")
        sys.exit(1)

    print(f"   Found {len(tracks):,} tracks in your library.")

    try:
        playlist_name, track_ids, rationale = ask_claude_for_playlist(prompt, tracks)
    except Exception as e:
        print(f"❌ Claude API error: {e}")
        sys.exit(1)

    if not track_ids:
        print("❌ Claude returned no tracks. Try rephrasing your prompt.")
        sys.exit(1)

    print(f"   Curator's note: {rationale}")
    print()

    try:
        count = create_swinsian_playlist(playlist_name, track_ids, tracks)
    except RuntimeError as e:
        print(f"❌ Error creating playlist in Swinsian: {e}")
        sys.exit(1)

    print()
    print(f"✅ Playlist \"{playlist_name}\" created with {count} tracks!")
    print("   Open Swinsian to find it in your playlists. Enjoy! 🎶")


if __name__ == "__main__":
    main()