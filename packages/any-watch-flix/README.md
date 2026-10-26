# any-watch-flix

Stream movies and Western TV shows from **FlixHQ, LK21, and IDLIX**, plus download subtitles from **SubDL**.

```bash
any-watch-flix "Inception"
any-watch-flix "Breaking Bad" -s 1 -e 1-3
any-watch-flix "Interstellar" --sub eng

# Pick a site
any-watch-flix "Inception" --site idlix
any-watch-flix "Interstellar" --site lk21

# List every flix site and mirror
any-watch-flix --list-sites
```

## SubDL subtitles

SubDL is subtitle-only. Get a free key from <https://subdl.com/panel/api>, then:

```bash
export SUBDL_API_KEY="your-key"
any-watch-flix "Interstellar" --site subdl --sub eng
```

The `.srt` (or `.zip` extract) is saved to `~/Downloads/any-watch-subtitles` by default. Override it with `download_dir` in `~/.config/any-watch/config.json`.
