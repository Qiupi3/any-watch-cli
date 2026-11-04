# any-watch-cli 🎬

Universal, ultra-lightweight terminal streaming suite for **Movies, Western TV, Anime, and Asian Dramas (KDrama & CDrama)**.

Built purely for **streaming playback** (no downloader bloat for video). Written in modern, dependency-minimal Python for **macOS**, **Linux**, **Windows**, and **Android (Termux)**.

---

## ⚡ Installation

### Option 1: Global CLI Tool (Recommended with `uv`)

If you want the `any-watch` commands available everywhere in your terminal:

```bash
uv tool install ./release/any_watch-1.0.0.0-py3-none-any.whl --find-links ./release/
```

> **Why `uv tool install`?**
> `uv pip install` installs into the local `.venv` folder, whereas `uv tool install` installs binaries directly into your `~/.local/bin/` so you can run `any-watch` from any folder.

#### Force reinstall / repair (only if needed)

Use this when an update did not take effect, a command still runs an old version,
or the installed tool looks broken. It is **not** part of the normal install —
run it only if you actually need it:

```bash
# uv: drop cached wheels, then reinstall over the existing install
uv cache clean any-watch-core any-watch-flix any-watch-anime any-watch-drama any-watch
uv tool install --force --reinstall ./release/any_watch-1.0.0.0-py3-none-any.whl --find-links ./release/

# pip equivalent
pip install --force-reinstall --no-cache-dir ./release/*.whl
```

Check what you are running afterwards with `any-watch -v`.

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

* `release/any_watch_core-1.0.0.0-py3-none-any.whl`
* `release/any_watch_flix-1.0.0.0-py3-none-any.whl`
* `release/any_watch_anime-1.0.0.0-py3-none-any.whl`
* `release/any_watch_drama-1.0.0.0-py3-none-any.whl`
* `release/any_watch-1.0.0.0-py3-none-any.whl`

---

## 📦 Independent Modular Packages

Each module can be installed and used **independently**:

| Package Wheel | Standalone Command | What it Streams |
|---|---|---|
| `any_watch_core` | *(engine)* | Shared player, config, catalog, extraction, & selection UI |
| `any_watch_flix` | `any-watch-flix` | Movies & Western TV — FlixHQ, LK21, IDLIX |
| `any_watch_anime` | `any-watch-anime` | Anime — HiAnime, AnoBoy, Oploverz, OtakuDesu, Samehadaku |
| `any_watch_drama` | `any-watch-drama` | KDrama/CDrama — KissKH, NaraShika, Nontongo, DramaSerial, Drakorindo |
| `any_watch` | `any-watch` | Master CLI across all categories |

---

## 🗂️ Provider Catalog

### 🍿 Flix — Movies & Western TV

| Site | Max quality | Active domains | Format | Notes |
|---|---|---|---|---|
| **FlixHQ** | 1080p | `flixhqz.net` | Softsub | Global movies & TV |
| **LK21** | 1080p | `tv12.lk21official.cc`, `lk21.de` | Hardsub | Indonesian movie index; JSON search + playcdn |
| **IDLIX** | 1080p | `idlixmovie.com`, `idlix.lat`, `idlix.com`, `idlix.link` | Softsub (.vtt) | Series API + proxied HLS with `.vtt` tracks |

### 🎌 Anime — Sub Indo

| Site | Max quality | Active domains | Format | Notes |
|---|---|---|---|---|
| **HiAnime** | 1080p | `hianime.at` | Softsub + Hardsub | Encrypted embed payload |
| **AnoBoy** | 720p | `anoboy.quest`, `anoboy.live` | Hardsub | Blogger / StreamWish players |
| **Oploverz** | 1080p | `oploverz.ch`, `oploverz.co.in`, `link.oploverz.ltd` | Hardsub | Paginated episode lists |
| **OtakuDesu** | 720p | `otakudesu.blog`, `otakudesu.cloud`, `otakudesu.camera`, `otakudesu.best` | Hardsub + Softsub | Two-step WordPress AJAX player; validates mirrors |
| **Samehadaku** | 1080p | `samehadaku.li`, `samehadaku.site`, `v2.samehadaku.how` | Hardsub + Softsub | VenoAnime-style theme |

### 📺 Drama — KDrama & CDrama

| Site | Max quality | Active domains | Format | Notes |
|---|---|---|---|---|
| **KissKH** | 1080p | `kisskh.co` | Softsub (.srt) | REST API + per-episode `kkey`; DoH fallback |
| **NaraShika** | 720p | `narashika.top`, `narashika.vip` | Softsub (.srt) + Hardsub | GMR theme; falls back to Nontongo for dead hosts |
| **Nontongo** | 1080p | `nontongo.site` | Hardsub | Encrypted `window.__PX` player → HLS |
| **DramaSerial** | 720p | `dramaserial.movie`, `tv1.dramaserial.movie` | Hardsub | GMR theme; falls back to Nontongo when its CDN dies |
| **Drakorindo** | 720p | `drakorindo.autos`, `drakorindo.win` | Hardsub + `.srt` | Some posts are download-only; Nontongo fallback |

> `Max quality` is the best resolution the site normally serves; the picker
> shows it next to each site. Mirror domains rotate. If a site fails, try
> another mirror or another provider.
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
| `--list-sites` | `--list-sites` | Print sites, mirror domains, formats, and max quality | `--list-sites` |
| `-v` | `--version` | Show the installed version | `-v` |
| `--check-update` | `--check-update` | Check the published version and exit | `--check-update` |
| `--update` | `--update` | Check and install the newer version | `any-watch --update` |

Subcommands: `any-watch flix`, `any-watch anime`, `any-watch drama`.

---

## 🔄 Versioning & Updates

Versions have four numbers — `MAJOR.CATEGORY.AREA.SITE`:

| Part | Meaning | Example |
|---|---|---|
| 1st | Major version / architecture change | `2.0.0.0` |
| 2nd | Major domain change — every category breaks without the update | `1.1.0.0` |
| 3rd | One category's domains all changed (e.g. all anime sites) | `1.0.1.0` |
| 4th | One or two domains changed, or another minor change | `1.0.0.0` |

On every run the CLI checks `version.json` (at most once per day, cached in
`~/.config/any-watch/update-check.json`) and prints a reminder when a newer
version is out. If you are at an interactive prompt it also asks
`Update now? [Y/n]` and runs the matching installer (`uv tool install --force`,
falling back to `pip install --upgrade`).

```bash
any-watch --check-update   # only check, print the reminder and exit
any-watch --update         # check and install the newer version
```

Disable the automatic check with `"check_updates": false` in
`~/.config/any-watch/config.json` or `export ANY_WATCH_NO_UPDATE_CHECK=1`.

---

## ⚙️ Configuration (`config.json`)

Settings are stored at `~/.config/any-watch/config.json`:

```json
{
  "player": "mpv",
  "quality": "auto",
  "sub_language": "eng",
  "stream_provider": "auto",
  "check_updates": true,
  "update_url": "",
  "wheel_index": ""
}
```

Defaults: **MPV** player, **English** (`eng`) softsub preference, and automatic
update checks once a day.

* `"sub_language": "eng"` sets the default softsub preference (`eng` or `ind`).
  `--sub ind` overrides it for one run.
* `"player": "iina"` makes IINA the default player on macOS.
* `"check_updates": false` disables the version check (same as
  `ANY_WATCH_NO_UPDATE_CHECK=1`).
* `"update_url": "https://…/version.json"` points the checker at another manifest.
* `"wheel_index": "https://…/release/"` installs updates from a wheel index.

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
* Some anime mirrors (googlevideo / mp4upload) hand out **IP-bound** links: they
  only play from the IP that generated them. When `Launching player` is followed
  by a 403 or a player error, pick another mirror or another anime site.
