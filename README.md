# any-watch-cli 🎬

Universal, ultra-lightweight terminal streaming suite for **Movies, Western TV, Anime, and Asian Dramas (KDrama & CDrama)**.

Built purely for **streaming playback** (no bloatware, zero download dependencies). Written in modern, dependency-minimal Python for **macOS**, **Linux**, **Windows**, and **Android (Termux)**.

---

## ⚡ Installation

### Option 1: Global CLI Tool (Recommended with `uv`)

If you want the `any-watch` commands available everywhere in your terminal:

```bash
uv tool install ./release/any_watch-1.0.0-py3-none-any.whl --find-links ./release/
```

> **Why `uv tool install`?**  
> `uv pip install` installs into the local `.venv` folder, whereas `uv tool install` installs binaries directly into your global `~/.local/bin/` so you can run `any-watch` from any folder.

#### Standard `pip`:
```bash
pip install ./release/*.whl
```

#### Android (Termux):
```bash
pkg update && pkg install python mpv termux-tools
pip install ./release/*.whl
```

---

### Option 2: Clone & Run Locally

```bash
# 1. Clone repository
git clone https://github.com/any-watch-cli/any-watch-cli.git
cd any-watch-cli

# 2. Run directly via uv without activating:
uv run any-watch "Solo Leveling"

# Or activate virtualenv:
source .venv/bin/activate
any-watch "Inception"
```

---

### Option 3: Build the Wheels Locally Yourself

You can compile all 5 standalone wheel files from scratch using the included build script:

```bash
# 1. Clone the repository
git clone https://github.com/any-watch-cli/any-watch-cli.git
cd any-watch-cli

# 2. Run the build script
./scripts/build.sh
```

This compiles all modules using `hatch` and places the fresh `.whl` files into `release/`:
* `release/any_watch_core-1.0.0-py3-none-any.whl`
* `release/any_watch_flix-1.0.0-py3-none-any.whl`
* `release/any_watch_anime-1.0.0-py3-none-any.whl`
* `release/any_watch_drama-1.0.0-py3-none-any.whl`
* `release/any_watch-1.0.0-py3-none-any.whl`

---

## 📦 Independent Modular Packages

Each module can be installed and used **independently** with zero bloat:

| Package Wheel | Standalone Command | Source | What it Streams |
|---|---|---|---|
| `any_watch_core` | *(engine)* | Core | Shared player, config, & selection UI |
| `any_watch_flix` | `any-watch-flix` | FlixHQ | Hollywood Movies & Western TV Shows |
| `any_watch_anime` | `any-watch-anime` | HiAnime | Japanese Anime (Sub/Dub) with auto-decryption |
| `any_watch_drama` | `any-watch-drama` | DramaCool | Korean Dramas (KDrama) & Chinese Dramas (CDrama) |
| `any_watch` | `any-watch` | Universal Pooler | Master search across all providers concurrently |

---

## 🚀 Quick Usage

### Master Search (Universal Pooler)
```bash
# Searches across FlixHQ, HiAnime, and DramaCool in parallel
any-watch "Solo Leveling"
any-watch "Queen of Tears"
any-watch "Inception"
```

### Choose Between English & Indonesian Subtitles (`--sub`)
Both softsub tracks are loaded into your video player simultaneously!
```bash
# Prefer Indonesian subtitles as default
any-watch "Queen of Tears" --sub ind

# Prefer English subtitles as default
any-watch-flix "Interstellar" --sub eng
```

* In **MPV**: Press `j` to toggle between Indonesian ↔ English ↔ Off at any time!
* In **IINA**: Select your preferred language from the Subtitles menu.
* In **VLC**: Right-click → Subtitle Track.

### Direct Module Usage
```bash
# Movies & TV (FlixHQ)
any-watch-flix "Breaking Bad" -s 1 -e 1-3
any-watch-flix "Inception" --sub ind

# Anime (HiAnime)
any-watch-anime "Frieren" -e 1-5
any-watch-anime "One Piece" -q 1080p

# Asian Dramas (DramaCool)
any-watch-drama "Crash Landing on You" -e 1 --sub ind
any-watch-drama "Hidden Love"
```

---

## 🛠️ CLI Options & Flags

| Flag | Long Option | Description | Example |
|---|---|---|---|
| `-p` | `--player` | Override video player (`mpv`, `iina`, `vlc`) | `-p iina` |
| `--sub` | `--sub` | Preferred subtitle language (`ind` or `eng`) | `--sub ind` |
| `-q` | `--quality` | Desired stream quality | `-q 1080p` |
| `-e` | `--episode` | Select single episode, range, or list | `-e 1`, `-e 1-5`, `-e 1,3,7` |
| `-s` | `--season` | Season number (for multi-season TV) | `-s 2` |
| `--provider` | `--provider` | Filter master pooler (`flix`, `anime`, `drama`) | `--provider anime` |

---

## ⚙️ Configuration (`config.json`)

Settings are stored at `~/.config/any-watch/config.json`:

```json
{
  "player": "mpv",
  "quality": "auto",
  "sub_language": "ind",
  "stream_provider": "auto"
}
```

* Change `"sub_language": "ind"` to always default to Indonesian softsubs.
* Change `"player": "iina"` to make IINA the default player on macOS.

---

## 📺 Platform Support & Players

| Platform | Recommended Player | Flags / Notes |
|---|---|---|
| **macOS** | `iina` or `mpv` | Seamless soft subtitles, multi-track switching |
| **Linux / BSD** | `mpv` | Native OSC controls, hardware acceleration |
| **Windows** | `mpv` or `vlc` | Automatically detected in `PATH` |
| **Termux / Android** | **VLC** | Fires native Android Intent directly into VLC Android app |
