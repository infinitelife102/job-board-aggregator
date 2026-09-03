# Keeping this fork up to date

There are two different updates. You do **not** need Git for job listings.

| What you want | What to run | Git? |
|---------------|-------------|------|
| Latest published jobs | `python filter_jobs.py` in this folder | No |
| Latest **code / company lists** from upstream | The sync steps below | Yes |

Upstream is the original repo: [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator).

This tool already downloads listings from the public [job-board-data](https://feashliaa.github.io/job-board-data/) site. A daily `git pull` is not required for that.

## Daily: filter published jobs

```bash
cd filter_jobs
pip install -r requirements.txt   # first time only
python filter_jobs.py
```

See [README.md](README.md) for options.

## When upstream code changed

Do this only if you want the original project's file updates on `feat/filter-jobs`. Skip it if you only need new job listings.

This branch is a **file snapshot** on top of the small fork history. Do **not** merge or rebase `main` into `feat/filter-jobs` — that would try to upload the full ~6GB Git history.

Copy current files from local `main` instead:

```bash
# 1. Update local main from upstream (history stays local)
git fetch upstream
git checkout main
git merge upstream/main

# 2. Copy upstream's current files onto this branch (no history)
git checkout feat/filter-jobs
git checkout main -- .
git add -A
git reset -- .venv
git status
git commit -m "Sync files from upstream"
git push
```

`git checkout main -- .` overwrites tracked files with whatever is on `main` right now. The `filter_jobs/` folder is not in upstream, so it stays as-is.

## Do not run

These upload the full local history (~6GB) to the fork:

```bash
git push --force origin main
git push origin feat/export-job-urls
```
