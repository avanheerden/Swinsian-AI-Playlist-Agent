# 🎧 Swinsian AI Playlist Agent

Generate playlists in Swinsian from natural language prompts using Claude AI. The agent reads your Swinsian library, sends a sample of your tracks to Claude, and creates a playlist directly inside Swinsian.

---

## Two ways to use it

| | UI app | CLI script |
|---|---|---|
| **File** | `swinsian_agent_ui.py` | `swinsian_agent.py` |
| **Best for** | Most users | Power users / automation |
| **How to run** | Double-click or `python swinsian_agent_ui.py` | Terminal command |
| **API key storage** | Saved to macOS keychain | Environment variable |

---

## Requirements

- macOS with [Swinsian](https://swinsian.com) installed and open
- Python 3.10 or later
- An [Anthropic API key](https://console.anthropic.com)

---

## Installation

### 1. Install dependencies

**For the UI app:**
```bash
pip install anthropic keyring
```

**For the CLI script only:**
```bash
pip install anthropic
```

### 2. Set your Anthropic API key

Get your key from [console.anthropic.com](https://console.anthropic.com) → API Keys.

**UI app:** enter it in the API Key field and click Save — it will be stored in your macOS keychain and remembered across sessions.

**CLI script:** paste this into Terminal (replacing the placeholder), which saves it permanently:
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### 3. Grant Terminal permission to control Swinsian

The first time you run either script, macOS will ask if Terminal can control Swinsian. Click **OK**. If you miss it, go to **System Settings → Privacy & Security → Automation** and enable Swinsian for Terminal.

---

## UI App

Run it from Terminal:
```bash
python swinsian_agent_ui.py
```

Or make it double-clickable by saving it with a `.command` extension and making it executable:
```bash
cp swinsian_agent_ui.py swinsian_agent_ui.command
chmod +x swinsian_agent_ui.command
```

The UI gives you:
- **API key field** — saved securely to your macOS keychain
- **Prompt field** — describe the playlist you want
- **Number of songs** — how many tracks to include
- **Randomise checkbox** — shuffle the playlist order before adding to Swinsian
- **Swinsian status indicator** — green when Swinsian is running, red when not
- **Live activity log** — see progress as the library is read and playlist is built

---

## CLI Script

Make sure Swinsian is open, then run from Terminal:

**With your prompt inline:**
```bash
python swinsian_agent.py "build me a playlist of 100 songs that rock and surprise"
```

**Interactive mode:**
```bash
python swinsian_agent.py
```

The script will prompt you to type your request.

**Example prompts:**
```bash
python swinsian_agent.py "50 melancholic songs for a rainy Sunday afternoon"
python swinsian_agent.py "upbeat workout mix, 45 minutes, mix of decades"
python swinsian_agent.py "late night jazz and soul, slow and atmospheric"
python swinsian_agent.py "classic rock deep cuts, nothing too obvious"
python swinsian_agent.py "eclectic dinner party mix — sophisticated but fun"
python swinsian_agent.py "songs that build from quiet to euphoric"
```

---

## How it handles large libraries

The Anthropic API has a token limit per request, so the agent uses a tiered strategy:

| Library size | What gets sent to Claude |
|---|---|
| Up to 1,500 tracks | Full metadata: title, artist, album, genre, year, rating, play count |
| 1,500 – 4,000 tracks | Compact catalog: title and artist only |
| Over 4,000 tracks | A sample of 4,000 tracks: your 2,000 most-played + 2,000 random |

For large libraries, re-running the same prompt will produce a different playlist each time because the random portion of the sample changes. Tracks are shuffled before being added to Swinsian so the playlist order is randomised from the start (if the randomise option is enabled).

---

## Cost

The agent uses Claude Haiku, Anthropic's fastest and most affordable model. Each playlist generation costs roughly **$0.04–0.05**, or about 20–25 playlists per dollar.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Swinsian not detected` | Open Swinsian, the status indicator will update within 5 seconds |
| `AppleScript error` | Go to System Settings → Privacy & Security → Automation and enable Swinsian for Terminal |
| `Claude API error: 429 rate limit` | Wait a minute and try again |
| `Claude API error: 400 prompt too long` | Reduce `MAX_TRACKS_COMPACT` at the top of the script |
| Playlist created but empty | Check your Swinsian library is fully loaded |
| API key not saving | Install keyring (`pip install keyring`) or use the environment variable method instead |
