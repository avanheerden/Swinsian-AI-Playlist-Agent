# 🎧 Swinsian AI Playlist Agent

Generate playlists in Swinsian from natural language prompts using Claude AI. The agent reads your Swinsian library, sends a sample of your tracks to Claude, and creates a shuffled playlist directly inside Swinsian — all from a single command in Terminal.

---

## Requirements

- macOS with [Swinsian](https://swinsian.com) installed and open
- Python 3.10 or later
- An [Anthropic API key](https://console.anthropic.com)

---

## Installation

### 1. Install the Anthropic Python library

Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter) and run:

```bash
pip install anthropic
```

### 2. Set your Anthropic API key

Get your API key from [console.anthropic.com](https://console.anthropic.com) → API Keys, then run:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

This saves the key permanently so you don't need to re-enter it each session.

### 3. Save the script

Download `swinsian_agent.py` and place it somewhere convenient, e.g. your home folder (`~/swinsian_agent.py`) or a dedicated scripts folder.

### 4. Grant Terminal permission to control Swinsian

The first time you run the script, macOS will show a dialog asking if Terminal can control Swinsian. Click **OK**. If you miss it, go to **System Settings → Privacy & Security → Automation** and enable Swinsian for Terminal.

---

## Usage

Make sure Swinsian is open with your library loaded, then run the script from Terminal.

**With your prompt inline:**
```bash
python ~/swinsian_agent.py "build me a playlist of 100 songs that rock and surprise"
```

**Interactive mode** (the script will ask you for a prompt):
```bash
python ~/swinsian_agent.py
```

The script will:
1. Read your Swinsian library (takes ~30 seconds for large libraries)
2. Send a sample of your tracks to Claude
3. Show you Claude's curator's note explaining its choices
4. Create a shuffled playlist inside Swinsian

---

## Prompt ideas

```bash
python ~/swinsian_agent.py "50 melancholic songs for a rainy Sunday afternoon"
python ~/swinsian_agent.py "upbeat workout mix, 45 minutes, mix of decades"
python ~/swinsian_agent.py "late night jazz and soul, slow and atmospheric"
python ~/swinsian_agent.py "classic rock deep cuts, nothing too obvious"
python ~/swinsian_agent.py "eclectic dinner party mix — sophisticated but fun"
python ~/swinsian_agent.py "songs that build from quiet to euphoric"
python ~/swinsian_agent.py "my most-played artists, but tracks I rarely hear"
```

Be as descriptive as you like — Claude understands mood, era, energy, genre, and occasion.

---

## How it handles large libraries

The Anthropic API has a token limit per request, so the script uses a tiered strategy depending on library size:

| Library size | What gets sent to Claude |
|---|---|
| Up to 1,500 tracks | Full metadata: title, artist, album, genre, year, rating, play count |
| 1,500 – 4,000 tracks | Compact catalog: title and artist only |
| Over 4,000 tracks | A sample of 4,000 tracks: your 2,000 most-played + 2,000 random |

For a 36,000-track library, roughly 4,000 tracks are sent per run. Re-running the script with the same prompt will produce a different playlist because the random portion of the sample changes each time.

Tracks are automatically shuffled before being added to Swinsian, so the playlist order is randomised from the start.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Swinsian doesn't appear to be running` | Open Swinsian, then retry |
| `AppleScript error` | Go to System Settings → Privacy & Security → Automation and enable Swinsian for Terminal |
| `Claude API error: 429 rate limit` | Wait a minute and try again; the request was too large for your API plan's rate limit |
| `Claude API error: 400 prompt too long` | Reduce `MAX_TRACKS_COMPACT` at the top of the script |
| Playlist created but empty | The track search failed — check that your library is fully loaded in Swinsian |
| Script hangs on library read | Normal for large libraries on first run; subsequent reads are faster |
