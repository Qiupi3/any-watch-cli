# any-watch-drama

Stream Korean (KDrama), Chinese (CDrama), and other Asian dramas in your terminal from **KissKH, NaraShika, Nontongo, DramaSerial, and Drakorindo**.

```bash
any-watch-drama "Queen of Tears"
any-watch-drama "Hidden Love" -e 1-5
any-watch-drama "Crash Landing on You" --sub ind

# Pick a site
any-watch-drama "Squid Game" --site kisskh
any-watch-drama "Squid Game" --site dramaserial
any-watch-drama "Squid Game" --site narashika

# Interactive site picker
any-watch-drama

# List every drama site and mirror
any-watch-drama --list-sites
```

KissKH is the primary API-backed provider and replaces the retired DramaCool source. NaraShika and DramaSerial share a GMR-based scraper, with mirror domains selected automatically.
