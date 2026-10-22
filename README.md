# any-watch-cli 🎬

Universal, ultra-lightweight terminal streaming suite for **Movies, Western TV, Anime, and Asian Dramas (KDrama & CDrama)**.

Written in modern, dependency-minimal Python. Built for **macOS**, **Linux**, **Windows**, and **Android (Termux)**.

---

## ⚡ One-Liner Install

### Quick Install (all modules via wheel)
```bash
pip install https://github.com/any-watch-cli/any-watch-cli/releases/latest/download/any_watch-1.0.0-py3-none-any.whl
```
*(Or install locally from the `release/` directory)*:
```bash
pip install ./release/*.whl
```

### Install with uv (recommended for speed)
```bash
uv tool install ./release/any_watch-1.0.0-py3-none-any.whl --find-links ./release/
```

### Termux (Android)
```bash
pkg update && pkg install python mpv termux-tools
pip install ./release/*.whl
```

---

## 📦 Independent Modular Packages

Each module can be used and installed **independently** with zero bloat:

| Package Wheel | Standalone Command | Source | What it Streams |
|---|---|---|---|
| `any_watch_core` | *(engine)* | Core | Shared player, downloader, config, & selection UI |
| `any_watch_flix` | `any-watch-flix` | FlixHQ | Hollywood Movies & Western TV Shows |
| `any_watch_anime` | `any-watch-anime` | HiAnime | Japanese Anime (Sub/Dub) with auto-decryption |
| `any_watch_drama` | `any-watch-drama` | DramaCool | Korean Dramas (KDrama) & Chinese Dramas (CDrama) |
| `any_watch` | `any-watch` | Universal Pooler | Master search across all providers concurrently |

> **Tip:** If you only watch Anime, you can install just `any_watch_anime` and `any_watch_core` without downloading anything else!

---

## 🚀 Quick Usage

### Master Search (Universal Pooler)
```bash
# Searches across FlixHQ, HiAnime, and DramaCool in parallel
any-watch "Solo Leveling"
any-watch "Queen of Tears"
any-watch "Inception"
```

### Direct Module Usage
```bash
# Movies & TV (FlixHQ)
any-watch-flix "Breaking Bad" -s 1 -e 1-3
any-watch-flix "Interstellar" -a download

# Anime (HiAnime)
any-watch-anime "Frieren" -e 1-5
any-watch-anime "One Piece" -q 1080p

# Asian Dramas (DramaCool)
any-watch-drama "Crash Landing on You" -e 1
any-watch-drama "Hidden Love"
```

---

## 🛠️ CLI Options & Flags

| Flag | Long Option | Description | Example |
|---|---|---|---|
| `-a` | `--action` | Stream immediately (`play`) or save to disk (`download`) | `-a download` |
| `-p` | `--player` | Override video player (`mpv`, `iina`, `vlc`) | `-p iina` |
| `-q` | `--quality` | Desired stream quality | `-q 1080p` |
| `--sub` | `--sub` | Prioritize subtitle language | `--sub indonesian` or `--sub english` |
| `-e` | `--episode` | Select single episode, range, or list | `-e 1`, `-e 1-5`, `-e 1,3,7` |
| `-s` | `--season` | Season number (for multi-season TV) | `-s 2` |
| `--provider` | `--provider` | Filter master pooler (`flix`, `anime`, `drama`) | `--provider anime` |

---

## ⚙️ Configuration (`config.json`)

Settings are stored at `~/.config/any-watch/config.json` (or `%APPDATA%\any-watch\config.json` on Windows):

```json
{
  "player": "mpv",
  "download_dir": "/Users/user/Downloads/any-watch",
  "quality": "auto",
  "sub_language": "english",
  "stream_provider": "auto"
}
```

* Change `"player": "iina"` to make IINA the default player on macOS.
* Set `"sub_language": "indonesian"` to prioritize Indonesian subtitles whenever available.

---

## 📺 Platform Support & Players

| Platform | Recommended Player | Flags / Notes |
|---|---|---|
| **macOS** | `iina` or `mpv` | Seamless soft subtitles and resume playback |
| **Linux / BSD** | `mpv` | Native OSC controls, hardware acceleration |
| **Windows** | `mpv` or `vlc` | Automatically detected in `PATH` |
| **Termux / Android** | **VLC** | Fires native Android Intent directly into VLC Android app |

---

## 🔄 Self-Update

To update to the latest wheel:
```bash
pip install --upgrade --force-reinstall ./release/*.whl
```
