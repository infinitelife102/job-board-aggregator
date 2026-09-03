# filter_jobs — Filter and archive published job data

Download the already-published [job-board-data](https://feashliaa.github.io/job-board-data/) chunks and filter them with the **same rules as the web UI**, then save the results as local files. This does **not** re-run the scraper.

## Quick start

This folder is self-contained. Install its own dependencies, then run the script:

```bash
cd filter_jobs
pip install -r requirements.txt
python filter_jobs.py
```

Running with **no arguments** applies these **default filters**:

| Field | Default |
|------|---------|
| Location | `United States` |
| ATS | All |
| Experience Level | All |
| Date Posted | Previous calendar day in **America/New_York** (`--posted 1`) |
| Remote only | On |
| Hide recruiter-posted jobs | On |
| Keyword preset | `it` (broad IT title include + common non-IT excludes) |

Results are written under a date/time folder:

```
filter_jobs/archive/YYYY-MM-DD/          # date of jobs collected (New York calendar)
├── filters.json   # Applied filters + match count
├── jobs.json      # Full matched job objects
├── urls.txt       # Apply URLs (one per line)
└── jobs.csv       # Spreadsheet-friendly summary
```

With the default `--posted 1`, the folder is **yesterday in America/New_York** (e.g. Beijing 19 Aug afternoon → `archive/2026-08-18`). `--posted 3` uses a range name such as `2026-08-16_to_2026-08-18`. Re-running the same day overwrites that folder. `--posted-window rolling` or `--posted any` still uses a run timestamp (`YYYY-MM-DD_HHMMSS`).

The `archive/` directory is gitignored.

---

## Run from anywhere (standalone)

This folder does **not** depend on the rest of this repo (`scripts/`, `js/`, `data/`, etc.). Copy the whole `filter_jobs/` directory (script + `requirements.txt` + this README) anywhere, install, and run. Job data is downloaded from the public [job-board-data](https://feashliaa.github.io/job-board-data/) site.

```bash
# Windows example
xcopy filter_jobs D:\tools\filter_jobs\ /E /I
cd D:\tools\filter_jobs
pip install -r requirements.txt
python filter_jobs.py
```

```bash
# macOS / Linux example
cp -r filter_jobs ~/tools/filter_jobs
cd ~/tools/filter_jobs
pip install -r requirements.txt
python filter_jobs.py
```

By default, results go next to the script: `<folder-of-filter_jobs.py>/archive/<collected-date>/`. Use `-o` or `--archive-root` to write somewhere else.

You can also invoke it by full path from any working directory:

```bash
python D:\tools\filter_jobs\filter_jobs.py
python ~/tools/filter_jobs/filter_jobs.py
```

---

## How it works

1. Fetch `jobs_manifest.json` for the chunk list  
2. Download and decompress each `jobs_chunk_*.json.gz`  
3. Filter with the same logic as the UI (`js/filters.js`)  
4. Write files under `filter_jobs/archive/<collected-date>/`  

Because this tool does not hit ATS APIs directly, freshness matches the **published snapshot** (typically updated once per day).

---

## Changing the output location

```bash
# Default: filter_jobs/archive/2026-08-18/ (NY yesterday if --posted 1)
python filter_jobs.py

# Save this run to a specific folder
python filter_jobs.py -o D:\jobs\today_us_remote

# Change only the parent of timestamped folders
python filter_jobs.py --archive-root D:\jobs\archive
```

| Option | Description |
|--------|-------------|
| `-o` / `--output-dir` | **Folder** for this run’s files (creates a directory, not a single file) |
| `--archive-root` | Parent directory for dated runs when `-o` is omitted (default: `filter_jobs/archive`) |

---

## Parameters

All options are also listed by `python filter_jobs.py --help`.

### Keyword preset (IT)

There is no industry/IT field in ATS APIs, so this tool uses **title keywords only**.

| Option | Default | Description |
|--------|---------|-------------|
| `--preset it` | **default** | Merge a built-in IT **include** list (software, developer, devops, data, ml, …) and **exclude** list (sales engineer, civil engineer, nurse, …) into `--include` / `--exclude` |
| `--preset none` | — | Do not apply the IT keyword lists |

Extra `--include` / `--exclude` terms are **merged** with the preset (not replaced).

```bash
# Default: IT keywords + US + remote + yesterday in New York
python filter_jobs.py

# Same filters but no IT keyword gate (all titles)
python filter_jobs.py --preset none

# IT preset + your own extras
python filter_jobs.py --include "golang,kotlin" --exclude "manager"
```

The preset lists live in `filter_jobs.py` as `IT_INCLUDE` / `IT_EXCLUDE` — edit those if you need to tune recall vs noise.

### Text / number fields (UI counterparts)

| Option | UI field | Default | Description |
|--------|----------|---------|-------------|
| `--title TEXT` | Job Title | (none) | **Word-boundary** match on title (e.g. `Engineer` may not match `Engineering`) |
| `--company TEXT` | Company | (none) | Word-boundary match on company name |
| `--location TEXT` | Location | `United States` | Word-boundary match. Default also matches `USA`, `US`, `U.S`, `U.S.A` |
| `--any-location` | — | off | Clear the location filter (all locations) |
| `--min-salary N` | Salary | `0` (off) | Keep jobs whose `salary.median` is at least N |
| `--exclude A,B` | Exclude Keywords | (none; + IT preset when `--preset it`) | Drop jobs whose title matches any term (**word-boundary**, comma-separated) |
| `--include A,B` | Include Keywords | (none; + IT preset when `--preset it`) | Keep jobs whose title matches **at least one** term (**word-boundary**, comma-separated) |

Examples:

```bash
python filter_jobs.py --title "Software Engineer" --include senior,staff --exclude intern,junior
python filter_jobs.py --any-location
python filter_jobs.py --min-salary 120000
```

### Selects (UI dropdowns)

| Option | UI field | Default | Allowed values |
|--------|----------|---------|----------------|
| `--ats` | ATS | All (`""`) | `Ashby`, `Bamboohr`, `Greenhouse`, `Lever`, `Workday`, `iCIMS`, `Paylocity` |
| `--skill-level` | Experience Level | All (`""`) | `intern`, `entry`, `mid`, `senior` |
| `--posted` | Date Posted | `1` | `1`, `3`, `7`, `30` — or `any` / `all`. Default **calendar** window: previous N **full days** in `--date-tz` (so `1` = yesterday in New York). Not a rolling 24 hours. |
| `--date-tz` | — | `America/New_York` | IANA timezone for calendar dates. Your PC clock (e.g. Beijing) is ignored for this filter. |
| `--posted-window` | — | `calendar` | `calendar` = previous N days in `--date-tz`; `rolling` = last N×24 hours from now (old UI behavior) |
| `--status` | Status | (none) | `saved`, `applied`, `ignored` — **requires `--apps`** |

Examples:

```bash
python filter_jobs.py --ats Greenhouse --skill-level mid
python filter_jobs.py --posted 7
python filter_jobs.py --posted any
```

When a date filter is active (`1` / `3` / `7` / `30`), jobs missing both `updated_at` and `first_seen` are **excluded** (same as the UI).

**Calendar example (default):** if your computer is Beijing time 19 Aug 14:57, New York is 19 Aug 02:57. `--posted 1` then keeps jobs whose date in New York is **18 Aug** (yesterday there), not “the last 24 hours” and not Beijing’s calendar.

`--posted 3` keeps the previous 3 full New York dates (e.g. 16–18 Aug if NY “today” is 19 Aug). Today in New York is not included until the next NY midnight.

### Checkboxes

| Behavior | UI | Default | How to change |
|----------|-----|---------|---------------|
| Remote only | Remote only | **On** | `--no-remote-only` to turn off |
| Hide recruiters | Hide recruiter-posted jobs | **On** | `--include-recruiters` to turn off |
| Hide applied/ignored | Hide applied/ignored jobs | Off | `--hide-applied` to turn on (needs `--apps`) |

Remote detection (same as UI): location string contains `remote`, or `workplaceType == remote`.

```bash
python filter_jobs.py --no-remote-only
python filter_jobs.py --include-recruiters
```

### Application status (browser localStorage)

After using Saved / Applied / Ignored on the site, in the DevTools console:

```js
copy(localStorage.getItem('job-applications'))
```

Save the clipboard contents as `apps.json`, then:

```bash
python filter_jobs.py --apps apps.json --status saved
python filter_jobs.py --apps apps.json --hide-applied
```

Format: a JSON object keyed by job URL (`{ "https://...": { "status": "applied", "date": "..." }, ... }`).

### Data source

| Option | Default | Description |
|--------|---------|-------------|
| `--chunks-url` | `https://feashliaa.github.io/job-board-data/data/chunks` | Base URL for the manifest and chunks |

Use this if you host or mirror chunks elsewhere.

---

## Examples

```bash
# Defaults: US + remote + yesterday (New York calendar) + hide recruiters + IT keywords
python filter_jobs.py

# Old UI-style rolling 24 hours (not calendar yesterday)
python filter_jobs.py --posted-window rolling --posted 1

# Last 7 days, Greenhouse only (still IT preset)
python filter_jobs.py --posted 7 --ats Greenhouse

# Any location, remote only, no date filter, still IT keywords
python filter_jobs.py --any-location --posted any

# No IT keyword filter
python filter_jobs.py --preset none --posted 3

# Include non-remote and recruiters; last 3 days
python filter_jobs.py --no-remote-only --include-recruiters --posted 3
```

---

## Output files

| File | Purpose |
|------|---------|
| `filters.json` | Run timestamp, data `last_updated`, applied filters, match count |
| `jobs.json` | Array of matching jobs under the `jobs` key |
| `urls.txt` | Apply links only — handy for scripts or bookmarks |
| `jobs.csv` | Columns such as title, company, location, salary_median, ats, skill_level, url |

---

## Requirements

- Python 3.10+ recommended  
- `requests` and `tzdata` (`pip install -r requirements.txt` in this folder)  
- Network access to download public GitHub Pages chunks  
- The rest of this repository is **optional** — see [Run from anywhere](#run-from-anywhere-standalone)

---

## Updating later

Job listings do not need Git. To copy newer **code** from upstream onto `feat/filter-jobs` without uploading the full history, see [SYNC.md](SYNC.md).

## Notes

- This tool **filters and exports**; it does not scrape ATS sites. Use `scripts/scraper.py` for a full scrape.  
- IT selection is **keyword-only** (no department/industry API field). Include/exclude use **word-boundary** matching so `cto` does not match `Director` and `infra` does not match `Mainframe`. Tune `IT_INCLUDE` / `IT_EXCLUDE` or pass extra `--include` / `--exclude`.  
- Location `United States` is a string match, so listings labeled only `USA` / `US` may be missed. Re-run with `--location US` (or similar) if needed.  
- See the repo-root `README.md` for dataset licensing (e.g. CC BY-NC on curated company lists).
