#!/usr/bin/env python3
"""
Swinsian AI Playlist Agent — GUI
Run with: python swinsian_ui.py
"""

import subprocess
import json
import re
import math
import random
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import anthropic
import os
import keyring  # optional — gracefully skipped if unavailable

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_TRACKS_FULL    = 1500
MAX_TRACKS_COMPACT = 4000
CLAUDE_MODEL       = "claude-haiku-4-5-20251001"
KEYRING_SERVICE    = "SwinsianAgent"
KEYRING_USER       = "anthropic_api_key"

# ── Colours ────────────────────────────────────────────────────────────────────
BG          = "#1a1a1a"
BG_CARD     = "#242424"
BG_INPUT    = "#2e2e2e"
FG          = "#f0f0f0"
FG_DIM      = "#888888"
ACCENT      = "#c778dd"   # purple, nods to Anthropic
ACCENT_DARK = "#9d5bb5"
GREEN       = "#5cb85c"
RED         = "#e05c5c"
BORDER      = "#3a3a3a"
FONT        = ("SF Pro Display", 13)
FONT_SMALL  = ("SF Pro Display", 11)
FONT_MONO   = ("SF Mono", 11)
FONT_TITLE  = ("SF Pro Display", 20, "bold")
# ───────────────────────────────────────────────────────────────────────────────


def run_applescript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def is_swinsian_running() -> bool:
    try:
        out = run_applescript(
            'tell application "System Events" to return (name of processes) contains "Swinsian"'
        )
        return out.strip().lower() == "true"
    except Exception:
        return False


def get_library_tracks(log) -> list[dict]:
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

    for label, prop in [
        ("names", "name"), ("artists", "artist"), ("albums", "album"),
        ("genres", "genre"), ("years", "year"), ("ratings", "rating"),
        ("play counts", "play count"),
    ]:
        log(f"   Fetching {label}…")

    names   = fetch_property("name")
    artists = fetch_property("artist")
    albums  = fetch_property("album")
    genres  = fetch_property("genre")
    years   = fetch_property("year")
    ratings = fetch_property("rating")
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


def build_full_catalog(tracks):
    return "\n".join(
        f'{t["id"]}|{t["title"]}|{t["artist"]}|{t["album"]}|{t["genre"]}|{t["year"]}|★{t["rating"]}|▶{t["plays"]}'
        for t in tracks
    )


def build_compact_catalog(tracks):
    return "\n".join(f'{t["id"]}|{t["title"]}|{t["artist"]}' for t in tracks)


def ask_claude(api_key: str, prompt: str, num_songs: int, tracks: list[dict], log) -> tuple:
    client = anthropic.Anthropic(api_key=api_key)
    total  = len(tracks)

    if total <= MAX_TRACKS_FULL:
        catalog, desc = build_full_catalog(tracks), "id|title|artist|album|genre|year|rating|plays"
        log(f"   Sending full metadata for {total:,} tracks…")
    elif total <= MAX_TRACKS_COMPACT:
        catalog, desc = build_compact_catalog(tracks), "id|title|artist"
        log(f"   Sending compact catalog for {total:,} tracks…")
    else:
        log(f"   Sampling {MAX_TRACKS_COMPACT:,} from {total:,} tracks…")
        by_plays = sorted(tracks, key=lambda x: int(x["plays"] or 0), reverse=True)
        top  = by_plays[:MAX_TRACKS_COMPACT // 2]
        rest = by_plays[MAX_TRACKS_COMPACT // 2:]
        random.shuffle(rest)
        tracks  = top + rest[:MAX_TRACKS_COMPACT - len(top)]
        catalog, desc = build_compact_catalog(tracks), "id|title|artist"

    system = f"""You are an expert music curator with encyclopedic knowledge of genres, moods, eras, artists, and song characteristics.
You will receive a user's music library and a playlist request.
Your job: select the best tracks from the library to fulfil the request.

Rules:
- Return ONLY a JSON object in this exact format (no markdown, no extra text):
  {{"playlist_name": "...", "ids": [id1, id2, ...], "rationale": "one sentence"}}
- The ids must be integers from the catalog's first column.
- Select exactly {num_songs} tracks if possible, or as close as the library allows.
- Prioritise variety, curation quality, and faithfulness to the request.
- If the library doesn't have enough matching tracks, pick the closest alternatives and note it in the rationale."""

    user_message = f"User request: {prompt}\n\nLibrary catalog ({desc}):\n{catalog}"

    log("   Asking Claude to curate your playlist…")
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
            raise ValueError(f"Unexpected Claude response: {raw}")

    return data.get("playlist_name", "AI Playlist"), data.get("ids", []), data.get("rationale", "")


def create_playlist(playlist_name: str, track_ids: list, all_tracks: list, randomise: bool, log) -> int:
    id_to_track = {t["id"]: t for t in all_tracks}
    selected    = [id_to_track[i] for i in track_ids if i in id_to_track]

    if randomise:
        random.shuffle(selected)

    if not selected:
        log("⚠️  No matching tracks found.")
        return 0

    log(f"   Creating playlist '{playlist_name}' with {len(selected)} tracks…")

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

    BATCH   = 50
    added   = 0
    batches = math.ceil(len(selected) / BATCH)

    for b in range(batches):
        chunk = selected[b * BATCH:(b + 1) * BATCH]
        inner = []
        for t in chunk:
            st = t["title"].replace("\\", "\\\\").replace('"', '\\"')
            sa = t["artist"].replace("\\", "\\\\").replace('"', '\\"')
            inner.append(f'''
        set found to (every track whose name is "{st}" and artist is "{sa}")
        if (count of found) > 0 then add tracks {{item 1 of found}} to normal playlist "{safe_name}"''')
        run_applescript('tell application "Swinsian"\n' + "\n".join(inner) + '\nend tell')
        added += len(chunk)
        log(f"   Added {min(added, len(selected))}/{len(selected)} tracks…")

    return len(selected)


# ── GUI ────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Swinsian AI Playlist Agent")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._setup_styles()
        self._build_ui()
        self._load_api_key()
        self.after(100, self._check_swinsian)

    # ── styles ───────────────────────────────────────────────────────────────

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("default")
        # Small secondary buttons (Save, Show, Hide)
        style.configure("Secondary.TButton",
            font=FONT_SMALL, foreground="#ffffff", background="#555555",
            borderwidth=0, focusthickness=0, padding=(10, 5))
        style.map("Secondary.TButton",
            foreground=[("active", "#ffffff"), ("disabled", "#888888")],
            background=[("active", "#666666"), ("disabled", "#444444")])
        # Large primary generate button
        style.configure("Primary.TButton",
            font=("SF Pro Display", 14, "bold"),
            foreground="#ffffff", background=ACCENT,
            borderwidth=0, focusthickness=0, padding=(20, 10))
        style.map("Primary.TButton",
            foreground=[("active", "#ffffff"), ("disabled", "#cccccc")],
            background=[("active", ACCENT_DARK), ("disabled", ACCENT_DARK)])

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = tk.Frame(self, bg=BG, padx=28, pady=24)
        root.pack(fill="both", expand=True)

        # ── title row
        title_row = tk.Frame(root, bg=BG)
        title_row.pack(fill="x", pady=(0, 20))
        tk.Label(title_row, text="🎧", font=("", 28), bg=BG).pack(side="left")
        tk.Label(title_row, text="  Swinsian AI Playlist Agent",
                 font=FONT_TITLE, fg=FG, bg=BG).pack(side="left")

        self.status_dot = tk.Label(title_row, text="●", font=("", 14),
                                   fg=FG_DIM, bg=BG)
        self.status_dot.pack(side="right", padx=(0, 4))
        self.status_label = tk.Label(title_row, text="Checking Swinsian…",
                                     font=FONT_SMALL, fg=FG_DIM, bg=BG)
        self.status_label.pack(side="right")

        # ── API key
        self._section(root, "Anthropic API Key")
        key_row = tk.Frame(root, bg=BG)
        key_row.pack(fill="x", pady=(4, 14))
        self.api_key_var = tk.StringVar()
        self.key_entry = self._entry(key_row, self.api_key_var, show="•")
        self.key_entry.pack(side="left", fill="x", expand=True)
        self._button(key_row, "Save", self._save_api_key, small=True).pack(side="left", padx=(8, 0))
        self.show_key_btn = self._button(key_row, "Show", self._toggle_key, small=True)
        self.show_key_btn.pack(side="left", padx=(6, 0))

        # ── prompt
        self._section(root, "Playlist Prompt")
        self.prompt_var = tk.StringVar()
        self._entry(root, self.prompt_var,
                    placeholder="e.g. 100 songs that rock and surprise").pack(fill="x", pady=(4, 14))

        # ── num songs + randomise row
        opts_row = tk.Frame(root, bg=BG)
        opts_row.pack(fill="x", pady=(0, 18))

        left = tk.Frame(opts_row, bg=BG)
        left.pack(side="left")
        self._section(left, "Number of Songs")
        self.num_songs_var = tk.StringVar(value="50")
        num_entry = self._entry(left, self.num_songs_var, width=8)
        num_entry.pack(pady=(4, 0))

        right = tk.Frame(opts_row, bg=BG)
        right.pack(side="left", padx=(40, 0))
        self._section(right, "Options")
        self.randomise_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(right, text="Randomise playlist order",
                            variable=self.randomise_var,
                            font=FONT, fg=FG, bg=BG,
                            selectcolor=BG_INPUT,
                            activebackground=BG, activeforeground=FG,
                            highlightthickness=0, bd=0,
                            cursor="hand2")
        cb.pack(anchor="w", pady=(4, 0))

        # ── generate button
        self.gen_btn = ttk.Button(
            root, text="✦  Generate Playlist",
            style="Primary.TButton",
            cursor="hand2", command=self._run
        )
        self.gen_btn.pack(fill="x", pady=(0, 18))

        # ── log
        self._section(root, "Activity Log")
        self.log_box = scrolledtext.ScrolledText(
            root, height=12, font=FONT_MONO,
            bg=BG_CARD, fg=FG, insertbackground=FG,
            relief="flat", bd=0, padx=12, pady=10,
            state="disabled", wrap="word",
            highlightthickness=1, highlightbackground=BORDER
        )
        self.log_box.pack(fill="x", pady=(4, 0))
        self.log_box.tag_config("ok",    foreground=GREEN)
        self.log_box.tag_config("err",   foreground=RED)
        self.log_box.tag_config("dim",   foreground=FG_DIM)
        self.log_box.tag_config("accent",foreground=ACCENT)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text.upper(),
                 font=("SF Pro Display", 10, "bold"),
                 fg=FG_DIM, bg=BG).pack(anchor="w")

    def _entry(self, parent, var, show=None, placeholder=None, width=None):
        kwargs = dict(textvariable=var, font=FONT, fg=FG, bg=BG_INPUT,
                      insertbackground=FG, relief="flat", bd=0,
                      highlightthickness=1, highlightbackground=BORDER,
                      highlightcolor=ACCENT)
        if show:
            kwargs["show"] = show
        if width:
            kwargs["width"] = width
        e = tk.Entry(parent, **kwargs)
        e.config({"disabledbackground": BG_INPUT})
        # padding via internal ipady hack
        e.bind("<FocusIn>",  lambda ev: e.config(highlightbackground=ACCENT))
        e.bind("<FocusOut>", lambda ev: e.config(highlightbackground=BORDER))
        if placeholder and not var.get():
            e.insert(0, placeholder)
            e.config(fg=FG_DIM)
            def on_focus_in(ev):
                if e.get() == placeholder:
                    e.delete(0, "end")
                    e.config(fg=FG)
            def on_focus_out(ev):
                if not e.get():
                    e.insert(0, placeholder)
                    e.config(fg=FG_DIM)
            e.bind("<FocusIn>",  on_focus_in)
            e.bind("<FocusOut>", on_focus_out)
        return e

    def _button(self, parent, text, cmd, small=False):
        return ttk.Button(
            parent, text=text, command=cmd,
            style="Secondary.TButton",
            cursor="hand2"
        )

    def _log(self, msg: str, tag: str = ""):
        def _write():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n", tag)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _write)

    def _set_running(self, running: bool):
        def _update():
            if running:
                self.gen_btn.config(text="⏳  Generating…", state="disabled")
            else:
                self.gen_btn.config(text="✦  Generate Playlist", state="normal")
        self.after(0, _update)

    # ── API key persistence ───────────────────────────────────────────────────

    def _load_api_key(self):
        # Try keyring first, then env var
        try:
            key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if key:
                self.api_key_var.set(key)
                return
        except Exception:
            pass
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            self.api_key_var.set(env_key)

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        if not key:
            return
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
            self._log("✓ API key saved to keychain.", "ok")
        except Exception:
            self._log("ℹ API key will be used this session (keyring unavailable).", "dim")

    def _toggle_key(self):
        if self.key_entry.cget("show") == "•":
            self.key_entry.config(show="")
            self.show_key_btn.config(text="Hide")
        else:
            self.key_entry.config(show="•")
            self.show_key_btn.config(text="Show")

    # ── Swinsian status ───────────────────────────────────────────────────────

    def _check_swinsian(self):
        running = is_swinsian_running()
        if running:
            self.status_dot.config(fg=GREEN)
            self.status_label.config(text="Swinsian running", fg=GREEN)
        else:
            self.status_dot.config(fg=RED)
            self.status_label.config(text="Swinsian not detected", fg=RED)
        self.after(5000, self._check_swinsian)

    # ── main run ──────────────────────────────────────────────────────────────

    def _run(self):
        api_key = self.api_key_var.get().strip()
        prompt  = self.prompt_var.get().strip()
        num_str = self.num_songs_var.get().strip()
        randomise = self.randomise_var.get()

        # Validation
        if not api_key or api_key.startswith("sk-ant-") is False and len(api_key) < 10:
            self._log("❌ Please enter a valid Anthropic API key.", "err"); return
        if not prompt or prompt == "e.g. 100 songs that rock and surprise":
            self._log("❌ Please enter a playlist prompt.", "err"); return
        try:
            num_songs = int(num_str)
            assert 1 <= num_songs <= 500
        except Exception:
            self._log("❌ Number of songs must be between 1 and 500.", "err"); return
        if not is_swinsian_running():
            self._log("❌ Swinsian isn't running. Please open it and try again.", "err"); return

        # Clear log and run in background thread
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self._set_running(True)
        threading.Thread(target=self._worker,
                         args=(api_key, prompt, num_songs, randomise),
                         daemon=True).start()

    def _worker(self, api_key, prompt, num_songs, randomise):
        try:
            self._log(f'✨ Prompt: "{prompt}"', "accent")
            self._log(f'   Songs: {num_songs}  |  Randomise: {"yes" if randomise else "no"}', "dim")
            self._log("")

            self._log("📚 Reading your Swinsian library…")
            tracks = get_library_tracks(self._log)
            self._log(f"   Found {len(tracks):,} tracks.", "dim")
            self._log("")

            self._log("🤖 Asking Claude to curate…")
            name, ids, rationale = ask_claude(api_key, prompt, num_songs, tracks, self._log)
            self._log(f'   Playlist name: "{name}"', "dim")
            self._log(f"   Rationale: {rationale}", "dim")
            self._log("")

            self._log("🎵 Building playlist in Swinsian…")
            count = create_playlist(name, ids, tracks, randomise, self._log)
            self._log("")
            self._log(f'✅ Done! "{name}" created with {count} tracks. Enjoy! 🎶', "ok")

        except Exception as e:
            self._log(f"❌ Error: {e}", "err")
        finally:
            self._set_running(False)


if __name__ == "__main__":
    app = App()
    app.mainloop()