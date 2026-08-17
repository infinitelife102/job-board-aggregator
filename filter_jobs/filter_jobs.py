"""
Download public job chunks and filter them with the same options as the web UI.

Does not scrape ATS sites — uses https://feashliaa.github.io/job-board-data/

Default filters (run with no args):
  Location: United States
  ATS: all
  Experience: all
  Date posted: last 24 hours (--posted 1)
  Remote only: on
  Hide recruiter-posted jobs: on
  Keyword preset: it (broad title include + common excludes)

Each run writes under filter_jobs/archive/<YYYY-MM-DD_HHMMSS>/:
  filters.json, jobs.json, urls.txt, jobs.csv

See filter_jobs/README.md for full usage.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

FEATURE_DIR = Path(__file__).resolve().parent
DEFAULT_ARCHIVE_ROOT = FEATURE_DIR / "archive"
DEFAULT_CHUNKS_BASE = (
    "https://feashliaa.github.io/job-board-data/data/chunks"
)

ATS_CHOICES = [
    "Ashby",
    "Bamboohr",
    "Greenhouse",
    "Lever",
    "Workday",
    "iCIMS",
    "Paylocity",
]
SKILL_CHOICES = ["intern", "entry", "mid", "senior"]
STATUS_CHOICES = ["saved", "applied", "ignored"]
POSTED_CHOICES = ["1", "3", "7", "30"]
PRESET_CHOICES = ["it", "none"]

# Title substring lists (same matching as --include / --exclude).
# Broad on purpose: prefer recall; trim false positives via IT_EXCLUDE / --exclude.
IT_INCLUDE = [
    "software",
    "developer",
    "engineer",
    "engineering",
    "programmer",
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "fullstack",
    "full-stack",
    "full stack",
    "devops",
    "sre",
    "site reliability",
    "platform",
    "infrastructure",
    "infra",
    "cloud",
    "kubernetes",
    "data scientist",
    "data science",
    "data engineer",
    "data analytics",
    "machine learning",
    "deep learning",
    "ml engineer",
    "ai engineer",
    "artificial intelligence",
    "llm",
    "nlp",
    "computer vision",
    "cybersecurity",
    "security engineer",
    "application security",
    "infosec",
    "qa engineer",
    "quality assurance",
    "sdet",
    "test automation",
    "mobile engineer",
    "ios",
    "android",
    "react",
    "node.js",
    "golang",
    "rust engineer",
    "java engineer",
    "python engineer",
    "typescript",
    "systems engineer",
    "network engineer",
    "database",
    "dba",
    "etl",
    "analytics engineer",
    "bi engineer",
    "devops engineer",
    "platform engineer",
    "reliability",
    "observability",
    "firmware",
    "embedded software",
    "technical architect",
    "solutions architect",
    "software architect",
    "cto",
    "vp engineering",
    "head of engineering",
    "engineering manager",
    "staff engineer",
    "principal engineer",
]

IT_EXCLUDE = [
    "sales engineer",
    "sales engineering",
    "customer engineer",
    "solutions engineer",
    "solution engineer",
    "business engineer",
    "civil engineer",
    "mechanical engineer",
    "electrical engineer",
    "chemical engineer",
    "structural engineer",
    "biomedical engineer",
    "industrial engineer",
    "manufacturing engineer",
    "process engineer",
    "project engineer",
    "field engineer",
    "facility engineer",
    "hvac",
    "nurse",
    "nursing",
    "physician",
    "therapist",
    "accountant",
    "bookkeeper",
    "attorney",
    "paralegal",
    "realtor",
    "cashier",
    "warehouse",
    "truck driver",
    "cdl",
]


def merge_csv_terms(*groups: str) -> str:
    """Join comma-separated term groups; preserve order, drop duplicates (case-insensitive)."""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        if not group:
            continue
        for term in group.split(","):
            t = term.strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return ",".join(out)


def escape_regex(s: str) -> str:
    return re.sub(r"[.*+?^${}()|[\]\\]", lambda m: "\\" + m.group(0), s)


def word_boundary_re(term: str) -> re.Pattern:
    return re.compile(rf"\b{escape_regex(term)}\b", re.IGNORECASE)


def compile_terms(csv_terms: str) -> list[re.Pattern]:
    return [
        word_boundary_re(t.strip())
        for t in (csv_terms or "").split(",")
        if t.strip()
    ]


def location_text(job: dict) -> str:
    loc = job.get("location")
    if not loc:
        return ""
    if isinstance(loc, dict):
        return (loc.get("name") or "").lower()
    return str(loc).lower()


def load_apps(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit("--apps must be a JSON object keyed by job URL")
    return data


def fetch_all_jobs(base_url: str) -> tuple[list, dict]:
    base = base_url.rstrip("/")
    print(f"Fetching manifest from {base}/jobs_manifest.json …")
    manifest = requests.get(f"{base}/jobs_manifest.json", timeout=60)
    manifest.raise_for_status()
    meta = manifest.json()

    jobs: list = []
    for name in meta.get("chunks", []):
        url = f"{base}/{name}"
        print(f"  Downloading {name} …")
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        chunk = json.loads(gzip.decompress(resp.content))
        jobs.extend(chunk)
        print(f"    +{len(chunk):,} (total {len(jobs):,})")

    return jobs, meta


def matches_job(job: dict, args: argparse.Namespace, apps: dict) -> bool:
    """Mirror js/filters.js filterJobs logic."""
    if args.hide_recruiters and job.get("is_recruiter") is True:
        return False

    url = job.get("url") or ""
    job_status = (apps.get(url) or {}).get("status") or ""

    if args.hide_applied and job_status in ("applied", "ignored"):
        return False
    if args.status and job_status != args.status:
        return False

    title = (job.get("title") or "").lower()
    company = (job.get("company") or job.get("company_slug") or "").lower()
    location = location_text(job)

    min_salary = args.min_salary or 0
    if min_salary > 0:
        salary = job.get("salary") or {}
        median = salary.get("median") if isinstance(salary, dict) else None
        if not median or median < min_salary:
            return False

    if args.remote_only:
        workplace = (job.get("workplaceType") or "").lower()
        is_remote = (
            job.get("remote") is True
            or "remote" in location
            or workplace == "remote"
        )
        if not is_remote:
            return False

    if args.ats:
        if (job.get("ats") or "").lower() != args.ats.lower():
            return False

    if args.skill_level:
        if (job.get("skill_level") or "").lower() != args.skill_level.lower():
            return False

    if args.posted:
        days = int(args.posted)
        raw = job.get("updated_at") or job.get("first_seen")
        if not raw:
            return False
        try:
            t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - t).total_seconds() / 86400
        except ValueError:
            return False
        if age_days > days:
            return False

    exclude_patterns = getattr(args, "exclude_patterns", None) or []
    if exclude_patterns and any(p.search(title) for p in exclude_patterns):
        return False

    include_patterns = getattr(args, "include_patterns", None) or []
    if include_patterns and not any(p.search(title) for p in include_patterns):
        return False

    if args.title and not word_boundary_re(args.title).search(title):
        return False
    if args.company and not word_boundary_re(args.company).search(company):
        return False
    if args.location and not word_boundary_re(args.location).search(location):
        return False

    return True


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Filter published job-board-data chunks using the same filters as the web UI. "
            "Does not scrape ATS sites. Defaults: US + remote + last 24h + hide recruiters "
            "+ IT title keyword preset."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--preset",
        default="it",
        choices=PRESET_CHOICES,
        help="Keyword preset: 'it' = broad IT title include/exclude; 'none' = no preset",
    )
    p.add_argument("--title", default="", help="Job Title (word-boundary match, like UI)")
    p.add_argument("--company", default="", help="Company (word-boundary match)")
    p.add_argument(
        "--location",
        default="United States",
        help="Location (word-boundary match). Default: United States",
    )
    p.add_argument(
        "--any-location",
        action="store_true",
        help="Clear location filter (match all locations)",
    )
    p.add_argument(
        "--min-salary",
        type=int,
        default=0,
        help="Minimum median salary (UI Salary field)",
    )
    p.add_argument(
        "--status",
        default="",
        help=f"Application status (needs --apps): {', '.join(STATUS_CHOICES)}",
    )
    p.add_argument(
        "--ats",
        default="",
        help=f"ATS platform (empty = all): {', '.join(ATS_CHOICES)}",
    )
    p.add_argument(
        "--skill-level",
        default="",
        help=f"Experience level (empty = all): {', '.join(SKILL_CHOICES)}",
    )
    p.add_argument(
        "--posted",
        default="1",
        help="Posted within N days: 1, 3, 7, 30 — or 'any' for no date filter",
    )
    p.add_argument(
        "--exclude",
        default="",
        help="Extra exclude title keywords, comma-separated (merged with preset)",
    )
    p.add_argument(
        "--include",
        default="",
        help="Extra include title keywords, comma-separated (merged with preset)",
    )

    p.add_argument(
        "--hide-recruiters",
        dest="hide_recruiters",
        action="store_true",
        default=True,
        help="Hide recruiter-posted jobs (default: on)",
    )
    p.add_argument(
        "--include-recruiters",
        dest="hide_recruiters",
        action="store_false",
        help="Do not hide recruiter jobs",
    )
    p.add_argument(
        "--remote-only",
        dest="remote_only",
        action="store_true",
        default=True,
        help="Remote only (default: on)",
    )
    p.add_argument(
        "--no-remote-only",
        dest="remote_only",
        action="store_false",
        help="Allow non-remote jobs",
    )
    p.add_argument(
        "--hide-applied",
        action="store_true",
        help="Hide applied/ignored (needs --apps)",
    )

    p.add_argument(
        "--apps",
        default="",
        help=(
            "JSON export of browser localStorage key 'job-applications' "
            "for --status / --hide-applied"
        ),
    )
    p.add_argument(
        "--chunks-url",
        default=DEFAULT_CHUNKS_BASE,
        help="Base URL for jobs_manifest.json and chunks",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        default="",
        help=(
            "Folder for this run's files. "
            f"Default: {DEFAULT_ARCHIVE_ROOT}/<YYYY-MM-DD_HHMMSS>/"
        ),
    )
    p.add_argument(
        "--archive-root",
        default=str(DEFAULT_ARCHIVE_ROOT),
        help="Parent folder for date-stamped runs when -o is omitted",
    )
    return p


def _validate_choice(name: str, value: str, allowed: list[str]) -> None:
    if value and value not in allowed:
        raise SystemExit(f"Invalid --{name}={value!r}; choose one of: {', '.join(allowed)}")


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.any_location:
        args.location = ""
    posted = (args.posted or "").strip().lower()
    if posted in ("", "any", "all"):
        args.posted = ""

    preset = (args.preset or "none").strip().lower()
    args.preset = preset
    if preset == "it":
        args.include = merge_csv_terms(",".join(IT_INCLUDE), args.include)
        args.exclude = merge_csv_terms(",".join(IT_EXCLUDE), args.exclude)
    elif preset != "none":
        raise SystemExit(f"Unknown --preset={preset!r}; choose: {', '.join(PRESET_CHOICES)}")

    args.include_patterns = compile_terms(args.include)
    args.exclude_patterns = compile_terms(args.exclude)
    return args


def filters_dict(args: argparse.Namespace) -> dict:
    return {
        "preset": args.preset or None,
        "title": args.title or None,
        "company": args.company or None,
        "location": args.location or None,
        "min_salary": args.min_salary or None,
        "status": args.status or None,
        "ats": args.ats or None,
        "skill_level": args.skill_level or None,
        "posted": args.posted or None,
        "exclude": args.exclude or None,
        "include": args.include or None,
        "hide_recruiters": args.hide_recruiters,
        "remote_only": args.remote_only,
        "hide_applied": args.hide_applied,
    }


def resolve_out_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return Path(args.archive_root) / stamp


def write_archive(
    out_dir: Path,
    filtered: list,
    meta: dict,
    filters: dict,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    filters_path = out_dir / "filters.json"
    jobs_path = out_dir / "jobs.json"
    urls_path = out_dir / "urls.txt"
    csv_path = out_dir / "jobs.csv"

    with open(filters_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "saved_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "data_last_updated": meta.get("last_updated"),
                "count": len(filtered),
                "filters": filters,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_updated": meta.get("last_updated"),
                "filters": filters,
                "count": len(filtered),
                "jobs": filtered,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    urls = [j.get("url") for j in filtered if j.get("url")]
    with open(urls_path, "w", encoding="utf-8") as f:
        f.write("\n".join(urls))
        if urls:
            f.write("\n")

    fieldnames = [
        "title",
        "company",
        "location",
        "salary_median",
        "ats",
        "skill_level",
        "remote",
        "updated_at",
        "first_seen",
        "url",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in filtered:
            salary = job.get("salary") or {}
            median = salary.get("median") if isinstance(salary, dict) else ""
            loc = job.get("location")
            if isinstance(loc, dict):
                loc = loc.get("name") or ""
            writer.writerow(
                {
                    "title": job.get("title") or "",
                    "company": job.get("company") or "",
                    "location": loc or "",
                    "salary_median": median if median is not None else "",
                    "ats": job.get("ats") or "",
                    "skill_level": job.get("skill_level") or "",
                    "remote": job.get("remote") if "remote" in job else "",
                    "updated_at": job.get("updated_at") or "",
                    "first_seen": job.get("first_seen") or "",
                    "url": job.get("url") or "",
                }
            )

    print(f"Archived {len(filtered):,} jobs under {out_dir.resolve()}")
    print(f"  {filters_path.name}")
    print(f"  {jobs_path.name}")
    print(f"  {urls_path.name}")
    print(f"  {csv_path.name}")


def main() -> int:
    args = normalize_args(build_parser().parse_args())
    _validate_choice("status", args.status, STATUS_CHOICES)
    _validate_choice("ats", args.ats, ATS_CHOICES)
    _validate_choice("skill-level", args.skill_level, SKILL_CHOICES)
    _validate_choice("posted", args.posted, POSTED_CHOICES)
    apps = load_apps(args.apps or None)

    if (args.status or args.hide_applied) and not apps:
        print(
            "Warning: --status / --hide-applied need --apps "
            "(export localStorage 'job-applications'). "
            "Continuing with empty status map.",
            file=sys.stderr,
        )

    print("Active filters:")
    for key, value in filters_dict(args).items():
        print(f"  {key}: {value}")

    jobs, meta = fetch_all_jobs(args.chunks_url)
    print(f"Loaded {len(jobs):,} jobs (last_updated={meta.get('last_updated')})")

    filtered = [j for j in jobs if matches_job(j, args, apps)]
    print(f"Matched {len(filtered):,} jobs")

    out_dir = resolve_out_dir(args)
    write_archive(out_dir, filtered, meta, filters_dict(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
