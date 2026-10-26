# any-watch-cli 🎬

Universal, ultra-lightweight terminal streaming suite for **Movies, Western TV, Anime, and Asian Dramas (KDrama & CDrama)**, with an optional **SubDL subtitle downloader**.

Built purely for **streaming playback** (no downloader bloat for video). Written in modern, dependency-minimal Python for **macOS**, **Linux**, **Windows**, and **Android (Termux)**.

---

## ⚡ Installation

### Option 1: Global CLI Tool (Recommended with `uv`)

If you want the `any-watch` commands available everywhere in your terminal:

```bash
uv tool install ./release/any_watch-1.1.0-py3-none-any.whl --find-links ./release/
```

> **Why `uv tool install`?**
> `uv pip install` installs into the local `.venv` folder, whereas `uv tool install` installs binaries directly into your `~/.local/bin/` so you can run `any-watch` from any folder.

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

```bash
# 1. Clone the repository
git clone https://github.com/any-watch-cli/any-watch-cli.git
cd any-watch-cli

# 2. Run the build script
./scripts/build.sh
```

This compiles all modules using `hatch` and places fresh `.whl` files into `release/`:

* `release/any_watch_core-1.1.0-py3-none-any.whl`
* `release/any_watch_flix-1.1.0-py3-none-any.whl`
* `release/any_watch_anime-1.1.0-py3-none-any.whl`
* `release/any_watch_drama-1.1.0-py3-none-any.whl`
* `release/any_watch-1.1.0-py3-none-any.whl`

---

## 📦 Independent Modular Packages

Each module can be installed and used **independently**:

| Package Wheel | Standalone Command | What it Streams |
|---|---|---|
| `any_watch_core` | *(engine)* | Shared player, config, catalog, extraction, & selection UI |
| `any_watch_flix` | `any-watch-flix` | Movies & Western TV — FlixHQ, LK21, IDLIX + SubDL subtitles |
| `any_watch_anime` | `any-watch-anime` | Anime — HiAnime, AnoBoy, Oploverz, OtakuDesu, Samehadaku |
| `any_watch_drama` | `any-watch-drama` | KDrama/CDrama — KissKH, NaraShika, Nontongo, DramaSerial, Drakorindo |
| `any_watch` | `any-watch` | Master CLI across all categories |

---

## 🗂️ Provider Catalog

### 🍿 Flix — Movies & Western TV

| Site | Active domains | Format | Notes |
|---|---|---|---|
| **FlixHQ** | `flixhqz.net` | Softsub | Global movies & TV |
| **LK21** | `tv8.lk21official.my`, `layarkaca21.vip` | Hardsub | Indonesian movie index; domains rotate |
| **IDLIX** | `idlix.lat`, `tv2.idlix.link` | Softsub (.vtt) | DooPlay player with `.vtt` tracks |
| **SubDL** | `subdl.com`, `api.subdl.com` | `.srt` / `.zip` | Subtitle-only; requires a free API key |

### 🎌 Anime — Sub Indo

| Site | Active domains | Format | Notes |
|---|---|---|---|
| **HiAnime** | `hianime.at` | Softsub + Hardsub | Encrypted embed payload |
| **AnoBoy** | `anoboy.quest`, `anoboy.live` | Hardsub | Blogger / StreamWish players |
| **Oploverz** | `oploverz.ch`, `oploverz.co.in`, `link.oploverz.ltd` | Hardsub | Paginated episode lists |
| **OtakuDesu** | `otakudesu.cloud`, `otakudesu.camera`, `otakudesu.best`, `otakudesu.love` | Hardsub + Softsub | Mirror list via WordPress AJAX |
| **Samehadaku** | `v2.samehadaku.how`, `samehadaku.care`, `samehadaku.email` | Hardsub + Softsub | VenoAnime-style theme |

### 📺 Drama — KDrama & CDrama

| Site | Active domains | Format | Notes |
|---|---|---|---|
| **KissKH** | `kisskh.co`, `kisskh.me`, `kisskh.tv` | Softsub (.vtt) | REST metadata API + HLS/subtitle source |
| **NaraShika** | `narashika.top`, `narashika.vip` | Softsub (.srt) + Hardsub | GMR/idmuvi theme; `.srt` links |
| **Nontongo** | `nontongo.site` | Hardsub | Server-rendered player data |
| **DramaSerial** | `dramaserial.movie`, `tv1.dramaserial.movie` | Hardsub | GMR/idmuvi theme; KDrama, CDrama, Lakorn |
| **Drakorindo** | `drakorindo.autos`, `drakorindo.win` | Hardsub + `.srt` | Some posts are download-only |

> Mirror domains rotate. If a site fails, try another mirror or another provider.
> KissKH replaces the retired DramaCool source; `DramaProvider` remains as a compatibility alias.

---

## 🚀 Quick Usage

### Interactive picker (recommended)

```bash
# No arguments: choose category → site → title → episode
any-watch

# Keep your query but choose category and site first
any-watch --pick "Solo Leveling"
```

### Master search

```bash
# Search every streaming site in parallel
any-watch "Solo Leveling"
any-watch "Queen of Tears"
any-watch "Inception"

# Limit to one category
any-watch --provider anime "Frieren"
any-watch --provider drama "Crash Landing on You"

# Use one specific site
any-watch --site anoboy "Frieren"
any-watch --site idlix "Inception"

# Show every category, site, mirror, and format
any-watch --list-sites
any-watch --list-sites --provider drama
```

### Category commands

```bash
# Movies & TV
any-watch-flix "Breaking Bad" -s 1 -e 1-3
any-watch-flix "Inception" --site idlix --sub ind

# Anime
any-watch-anime "Frieren" -e 1-5
any-watch-anime "One Piece" --site samehadaku -q 1080p

# Asian dramas
any-watch-drama "Crash Landing on You" -e 1 --sub ind
any-watch-drama "Hidden Love" --site kisskh
```

The category binaries also accept `--site`, interactive site selection (just omit the query), and `--list-sites`.

### SubDL subtitle download

SubDL is **subtitle-only** — it downloads a subtitle file instead of opening a stream.

```bash
# Export a free key from https://subdl.com/panel/api
export SUBDL_API_KEY="your-key"

any-watch flix "Interstellar" --site subdl
any-watch flix "Interstellar" --site subdl --sub eng
any-watch-flix "Breaking Bad" --site subdl
```

The subtitle is saved to `download_dir` (default `~/Downloads/any-watch-subtitles`), and the CLI prints the `mpv --sub-file=<path>` command.

---

## 🎬 Subtitles (`--sub`)

Softsub tracks are loaded into the player at once when a provider supplies them:

```bash
any-watch "Queen of Tears" --sub ind
any-watch-flix "Interstellar" --sub eng
```

* **MPV**: press `j` to cycle Indonesian ↔ English ↔ Off.
* **IINA**: select the track from the Subtitles menu.
* **VLC**: right-click → Subtitle Track.

Hardsub-only providers simply ignore `--sub`.

---

## 🛠️ CLI Options & Flags

| Flag | Long Option | Description | Example |
|---|---|---|---|
| `-p` | `--player` | Override video player (`mpv`, `iina`, `vlc`) | `-p iina` |
| `--sub` | `--sub` | Preferred subtitle language (`ind` or `eng`) | `--sub ind` |
| `-q` | `--quality` | Desired stream quality | `-q 1080p` |
| `-e` | `--episode` | Single episode, range, or list | `-e 1`, `-e 1-5`, `-e 1,3,7` |
| `-s` | `--season` | Season number (for multi-season TV) | `-s 2` |
| `--site` | `--site` | Use one provider/site only | `--site otakudesu` |
| `--pick` | `--pick` | Force the category/site picker | `--pick "Frieren"` |
| `--provider` | `--provider` | Limit the master CLI to one category | `--provider anime` |
| `--list-sites` | `--list-sites` | Print sites, mirrors, and formats | `--list-sites` |

Subcommands: `any-watch flix`, `any-watch anime`, `any-watch drama`.

---

## ⚙️ Configuration (`config.json`)

Settings are stored at `~/.config/any-watch/config.json`:

```json
{
  "player": "mpv",
  "quality": "auto",
  "sub_language": "ind",
  "stream_provider": "auto",
  "subdl_api_key": "",
  "download_dir": ""
}
```

* `"sub_language": "ind"` sets the default softsub preference (`ind` or `eng`).
* `"player": "iina"` makes IINA the default player on macOS.
* `"subdl_api_key": "..."` enables SubDL without an environment variable.
* `"download_dir": "/path/to/subtitles"` overrides the default subtitle folder.

`SUBDL_API_KEY` takes precedence over the config value when both are set.

---

## 📺 Platform Support & Players

| Platform | Recommended Player | Flags / Notes |
|---|---|---|
| **macOS** | `iina` or `mpv` | Seamless soft subtitles, multi-track switching |
| **Linux / BSD** | `mpv` | Native OSC controls, hardware acceleration |
| **Windows** | `mpv` or `vlc` | Automatically detected in `PATH` |
| **Termux / Android** | **VLC** | Fires native Android Intent directly into VLC Android app |

---

## ⚠️ Known Limitations

* Streaming sites rotate domains and change markup frequently. Use `--list-sites` and try another mirror/provider when one fails.
* Some providers depend on third-party hosts that may be geo-blocked, deleted, or unreachable.
* Drakorindo posts are sometimes download-only and expose no playable stream.
* SubDL requires a free API key and is not a streaming provider.
