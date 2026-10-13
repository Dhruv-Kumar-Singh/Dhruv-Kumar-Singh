#!/usr/bin/env python3
"""Regenerates ALL dynamic profile SVGs from live GitHub data.

Outputs (inside assets/ sibling to this script):
  stats-card.svg    · rich GitHub stats (commits, stars, PRs, issues, followers)
  streak.svg        · current/longest streak + total contributions
  activity-graph.svg· full-year 52-week contribution heatmap
  trophies.svg      · achievement trophies (Bronze→SSS tier)
  tech-stack.svg    · animated icon grid (auto-detected from repos)
  languages.svg     · animated language bars (bytes across repos)
  stats.svg         · simple stat cards (for backward compat)
  social-*.svg      · animated social icons (bounce + glow on hover)

README.md: <!--OSS:START-->...<!--OSS:END--> block updated.

Env: GH_USER (default below), GITHUB_TOKEN (required for GraphQL endpoints).
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

USER   = os.environ.get("GH_USER", "Dhruv-Kumar-Singh")
TOKEN  = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
ROOT   = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
MAX_REPOS = 40
DEVICON   = "https://raw.githubusercontent.com/devicons/devicon/master/icons/"

# ---------------------------------------------------------------------------
# Icon catalog
# ---------------------------------------------------------------------------
CATALOG = {
    "javascript":  ("JavaScript",   "Languages",         "javascript",  False),
    "typescript":  ("TypeScript",   "Languages",         "typescript",  False),
    "python":      ("Python",       "Languages",         "python",      False),
    "java":        ("Java",         "Languages",         "java",        False),
    "go":          ("Go",           "Languages",         "go",          False),
    "c":           ("C",            "Languages",         "c",           False),
    "cplusplus":   ("C++",          "Languages",         "cplusplus",   False),
    "rust":        ("Rust",         "Languages",         "rust",        True),
    "php":         ("PHP",          "Languages",         "php",         False),
    "kotlin":      ("Kotlin",       "Languages",         "kotlin",      False),
    "dart":        ("Dart",         "Languages",         "dart",        False),
    "bash":        ("Bash",         "Languages",         "bash",        False),
    "react":       ("React",        "Frontend",          "react",       False),
    "nextjs":      ("Next.js",      "Frontend",          "nextjs",      False),
    "html5":       ("HTML5",        "Frontend",          "html5",       False),
    "css3":        ("CSS3",         "Frontend",          "css3",        False),
    "tailwindcss": ("Tailwind",     "Frontend",          "tailwindcss", False),
    "bootstrap":   ("Bootstrap",    "Frontend",          "bootstrap",   False),
    "vitejs":      ("Vite",         "Frontend",          "vitejs",      False),
    "nodejs":      ("Node.js",      "Backend",           "nodejs",      False),
    "express":     ("Express",      "Backend",           "express",     True),
    "django":      ("Django",       "Backend",           "django",      True),
    "flask":       ("Flask",        "Backend",           "flask",       True),
    "fastapi":     ("FastAPI",      "Backend",           "fastapi",     False),
    "socketio":    ("Socket.io",    "Backend",           "socketio",    True),
    "graphql":     ("GraphQL",      "Backend",           "graphql",     False),
    "numpy":       ("NumPy",        "Data Science & ML", "numpy",       False),
    "pandas":      ("Pandas",       "Data Science & ML", "pandas",      True),
    "scikitlearn": ("Scikit-Learn", "Data Science & ML", "scikitlearn", False),
    "matplotlib":  ("Matplotlib",   "Data Science & ML", "matplotlib",  False),
    "seaborn":     ("Seaborn",      "Data Science & ML", "seaborn",     False),
    "tensorflow":  ("TensorFlow",   "Data Science & ML", "tensorflow",  False),
    "pytorch":     ("PyTorch",      "Data Science & ML", "pytorch",     False),
    "jupyter":     ("Jupyter",      "Data Science & ML", "jupyter",     False),
    "mysql":       ("MySQL",        "Database",          "mysql",       False),
    "postgresql":  ("PostgreSQL",   "Database",          "postgresql",  False),
    "mongodb":     ("MongoDB",      "Database",          "mongodb",     False),
    "redis":       ("Redis",        "Database",          "redis",       False),
    "firebase":    ("Firebase",     "Database",          "firebase",    False),
    "prisma":      ("Prisma",       "Database",          "prisma",      True),
    "googlecloud": ("Google Cloud", "DevOps & Cloud",    "googlecloud", False),
    "docker":      ("Docker",       "DevOps & Cloud",    "docker",      False),
    "kubernetes":  ("Kubernetes",   "DevOps & Cloud",    "kubernetes",  False),
    "linux":       ("Linux",        "DevOps & Cloud",    "linux",       False),
    "git":         ("Git",          "Tools",             "git",         False),
    "github":      ("GitHub",       "Tools",             "github",      True),
    "vscode":      ("VS Code",      "Tools",             "vscode",      False),
    "figma":       ("Figma",        "Tools",             "figma",       False),
    "postman":     ("Postman",      "Tools",             "postman",     False),
}
CATEGORIES = [
    "Languages", "Frontend", "Backend",
    "Data Science & ML", "Database", "DevOps & Cloud", "Tools",
]
PINNED = [
    "javascript", "typescript", "python", "java", "go",
    "react", "nextjs", "html5", "css3", "tailwindcss", "bootstrap", "vitejs",
    "nodejs", "express", "django", "flask",
    "numpy", "pandas", "scikitlearn", "matplotlib", "seaborn",
    "mysql", "postgresql", "mongodb", "redis",
    "googlecloud", "git", "vscode", "figma", "postman",
]
LANG_TO_SLUG = {
    "JavaScript": "javascript", "TypeScript": "typescript", "Python": "python",
    "Java": "java", "Go": "go", "C": "c", "C++": "cplusplus", "Rust": "rust",
    "PHP": "php", "Kotlin": "kotlin", "Dart": "dart", "HTML": "html5",
    "CSS": "css3", "Shell": "bash", "Dockerfile": "docker",
    "Jupyter Notebook": "jupyter",
}
NPM_MAP = {
    "react": "react", "next": "nextjs", "express": "express",
    "tailwindcss": "tailwindcss", "vite": "vitejs", "bootstrap": "bootstrap",
    "mongoose": "mongodb", "mongodb": "mongodb", "mysql": "mysql",
    "mysql2": "mysql", "pg": "postgresql", "redis": "redis",
    "ioredis": "redis", "typescript": "typescript", "firebase": "firebase",
    "@prisma/client": "prisma", "socket.io": "socketio", "graphql": "graphql",
}
PY_MAP = {
    "django": "django", "flask": "flask", "fastapi": "fastapi",
    "pandas": "pandas", "numpy": "numpy", "scikit-learn": "scikitlearn",
    "sklearn": "scikitlearn", "matplotlib": "matplotlib", "seaborn": "seaborn",
    "tensorflow": "tensorflow", "torch": "pytorch", "psycopg2": "postgresql",
    "psycopg2-binary": "postgresql", "pymongo": "mongodb", "redis": "redis",
    "mysql-connector-python": "mysql", "pymysql": "mysql",
}
TOPIC_ALIAS = {
    "reactjs": "react", "node": "nodejs", "node-js": "nodejs",
    "golang": "go", "next-js": "nextjs", "mongo": "mongodb",
    "postgres": "postgresql", "k8s": "kubernetes", "tailwind": "tailwindcss",
    "sklearn": "scikitlearn", "machine-learning": None, "vite": "vitejs",
}
LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Python": "#3572A5",
    "Java": "#b07219", "Go": "#00ADD8", "HTML": "#e34c26", "CSS": "#563d7c",
    "Shell": "#89e051", "C++": "#f34b7d", "C": "#aaaaaa",
    "Jupyter Notebook": "#DA5B0B", "Rust": "#dea584", "PHP": "#4F5D95",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Dockerfile": "#384d54",
    "SCSS": "#c6538c",
}

# ---------------------------------------------------------------------------
# HTTP / GraphQL helpers
# ---------------------------------------------------------------------------

def http(url: str, binary: bool = False):
    headers = {"User-Agent": "profile-readme-updater", "Accept": "application/vnd.github+json"}
    if TOKEN and url.startswith("https://api.github.com"):
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as r:
            data = r.read()
            return data if binary else data.decode("utf-8", "replace")
    except Exception:
        return None


def api(path: str):
    raw = http("https://api.github.com" + path)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


GQL_CONTRIBUTIONS = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
    pullRequests(states: MERGED) { totalCount }
    issues(states: CLOSED) { totalCount }
  }
}
"""


def graphql(query: str, variables: dict) -> dict | None:
    if not TOKEN:
        print("GITHUB_TOKEN not set – skipping GraphQL (stats/streak/graph/trophies).", file=sys.stderr)
        return None
    payload = json.dumps({"query": query, "variables": variables}).encode()
    headers = {
        "User-Agent": "profile-readme-updater",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    try:
        req = Request("https://api.github.com/graphql", data=payload, headers=headers)
        with urlopen(req, timeout=30) as r:
            result = json.loads(r.read().decode())
            if "errors" in result:
                print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
            return result.get("data", {}).get("user")
    except Exception as e:
        print(f"GraphQL exception: {e}", file=sys.stderr)
        return None


def fetch_public_fallback_data() -> dict | None:
    user_info = api(f"/users/{USER}") or {}
    name = user_info.get("name") or USER
    followers = user_info.get("followers", 0)

    raw = http(f"https://github-contributions-api.jogruber.de/v4/{USER}?y=last")
    weeks = []
    total_contribs = 0
    if raw:
        try:
            cdata = json.loads(raw)
            total_contribs = cdata.get("total", {}).get("lastYear", 0)
            items = cdata.get("contributions", [])
            cur_week = []
            for item in items:
                cur_week.append({
                    "contributionCount": item.get("count", 0),
                    "date": item.get("date", ""),
                })
                if len(cur_week) == 7:
                    weeks.append({"contributionDays": cur_week})
                    cur_week = []
            if cur_week:
                weeks.append({"contributionDays": cur_week})
        except Exception as e:
            print(f"Fallback contributions parsing failed: {e}", file=sys.stderr)

    return {
        "name": name,
        "followers": {"totalCount": followers},
        "contributionsCollection": {
            "totalCommitContributions": total_contribs,
            "totalPullRequestContributions": 0,
            "totalIssueContributions": 0,
            "contributionCalendar": {
                "totalContributions": total_contribs,
                "weeks": weeks,
            },
        },
        "pullRequests": {"totalCount": 0},
        "issues": {"totalCount": 0},
    }


def fetch_contribution_data() -> dict | None:
    now        = datetime.now(timezone.utc)
    year_ago   = now - timedelta(days=365)
    data = graphql(GQL_CONTRIBUTIONS, {
        "login": USER,
        "from":  year_ago.strftime("%Y-%m-%dT00:00:00Z"),
        "to":    now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if data:
        return data
    print("Using public fallback endpoint for contribution calendar and stats.", file=sys.stderr)
    return fetch_public_fallback_data()


# ---------------------------------------------------------------------------
# Data collection (repos / PRs)
# ---------------------------------------------------------------------------

def fetch_repos() -> list[dict]:
    out: list[dict] = []
    for page in range(1, 4):
        chunk = api(f"/users/{USER}/repos?per_page=100&type=owner&sort=pushed&page={page}")
        if not chunk:
            break
        out += chunk
        if len(chunk) < 100:
            break
    return [r for r in out if not r.get("fork") and not r.get("archived")]


def repo_signals(repo: dict) -> tuple[set[str], dict]:
    name  = repo["name"]
    slugs: set[str] = set()
    langs = api(f"/repos/{USER}/{name}/languages") or {}
    for lang in langs:
        if lang in LANG_TO_SLUG:
            slugs.add(LANG_TO_SLUG[lang])
    for topic in repo.get("topics") or []:
        t = TOPIC_ALIAS.get(topic, topic)
        if t in CATALOG:
            slugs.add(t)
    base = f"https://raw.githubusercontent.com/{USER}/{name}/HEAD/"
    for sub in ("", "client/", "frontend/", "server/", "backend/", "web/"):
        txt = http(base + sub + "package.json")
        if not txt:
            continue
        try:
            pkg = json.loads(txt)
        except ValueError:
            continue
        slugs.add("nodejs")
        for dep in {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}:
            if dep in NPM_MAP:
                slugs.add(NPM_MAP[dep])
    for sub in ("", "backend/", "server/", "api/"):
        txt = http(base + sub + "requirements.txt")
        if not txt:
            continue
        for line in txt.lower().splitlines():
            pkg = re.split(r"[=<>~!\[;@ ]", line.strip())[0]
            if pkg in PY_MAP:
                slugs.add(PY_MAP[pkg])
    return slugs, langs


def merged_prs() -> tuple[int, list[dict]]:
    q    = f"author:{USER}+type:pr+is:merged+-user:{USER}"
    data = api(f"/search/issues?q={q}&sort=updated&order=desc&per_page=30") or {}
    return data.get("total_count", 0), data.get("items", [])


def open_prs_count() -> int:
    data = api(f"/search/issues?q=author:{USER}+type:pr+is:open+-user:{USER}&per_page=1") or {}
    return data.get("total_count", 0)


def contributed_repo_slugs(full_names: list[str]) -> Counter:
    c: Counter = Counter()
    for full in full_names[:10]:
        info = api(f"/repos/{full}") or {}
        for topic in info.get("topics") or []:
            t = TOPIC_ALIAS.get(topic, topic)
            if t in CATALOG:
                c[t] += 1
        langs = api(f"/repos/{full}/languages") or {}
        for lang in sorted(langs, key=langs.get, reverse=True)[:3]:
            if lang in LANG_TO_SLUG:
                c[LANG_TO_SLUG[lang]] += 1
    return c


# ---------------------------------------------------------------------------
# Streak helpers
# ---------------------------------------------------------------------------

def calculate_streaks(weeks: list[dict]) -> tuple[int, int, int]:
    """Returns (current_streak, longest_streak, total_contributions)."""
    days: list[tuple[str, int]] = []
    for week in weeks:
        for day in week.get("contributionDays", []):
            days.append((day["date"], day["contributionCount"]))
    days.sort()

    total = sum(c for _, c in days)
    today_str = datetime.now(timezone.utc).date().isoformat()

    # Current streak (skip today if still 0 – day might not be over)
    current = 0
    for date_str, count in reversed(days):
        if date_str > today_str:
            continue
        if count > 0:
            current += 1
        elif date_str == today_str:
            continue   # today hasn't ended
        else:
            break

    # Longest streak
    longest = running = 0
    for _, count in days:
        if count > 0:
            running += 1
            longest  = max(longest, running)
        else:
            running  = 0

    return current, longest, total


# ---------------------------------------------------------------------------
# Contribution colour scale (GitHub dark-mode palette)
# ---------------------------------------------------------------------------

def contrib_color(count: int, max_count: int) -> str:
    if count == 0:
        return "#161b22"
    pct = count / max(max_count, 1)
    if pct <= 0.15:
        return "#0e4429"
    elif pct <= 0.35:
        return "#006d32"
    elif pct <= 0.65:
        return "#26a641"
    else:
        return "#39d353"


# ---------------------------------------------------------------------------
# Trophy tier helper
# ---------------------------------------------------------------------------

TIER_TABLE = [
    (0,    "Unknown",  "#555e6a"),
    (1,    "Bronze",   "#cd7f32"),
    (50,   "Silver",   "#a8b4c0"),
    (150,  "Gold",     "#ffd700"),
    (400,  "Platinum", "#b0e0e6"),
    (900,  "Ruby",     "#ff4466"),
    (2000, "SSS",      "#00ff41"),
]

def trophy_tier(value: int) -> tuple[str, str]:
    name, color = TIER_TABLE[0][1], TIER_TABLE[0][2]
    for min_val, n, c in TIER_TABLE:
        if value >= min_val:
            name, color = n, c
    return name, color


# ---------------------------------------------------------------------------
# Shared SVG constants
# ---------------------------------------------------------------------------

FONT = "font-family:Consolas,\"SFMono-Regular\",\"Liberation Mono\",Menlo,monospace"

BASE_CSS = f"""
*{{{FONT}}}
.panel{{fill:#0d1117;stroke:#00ff41;stroke-opacity:.35}}
.title{{fill:#00ff41;font-size:14px;font-weight:600}}
.cat{{fill:#00ff41;font-size:12.5px;font-weight:600}}
.muted{{fill:#8b949e;font-size:10.5px}}
.lbl{{fill:#8b949e;font-size:10.5px;text-anchor:middle}}
.val{{fill:#e6edf3;font-size:22px;font-weight:700;text-anchor:middle}}
.sub{{fill:#8b949e;font-size:10px;text-anchor:middle}}
.tile{{fill:#161b22;stroke:#30363d}}
.tile.live{{stroke:#00ff41;animation:glow 2.4s ease-in-out infinite alternate}}
.dot{{fill:#00ff41;animation:pulse 1.6s ease-in-out infinite}}
.cursor{{fill:#00ff41;animation:blink 1s steps(1) infinite}}
.enter{{opacity:0;animation:enter .6s ease-out forwards}}
.float{{animation:float 3.2s ease-in-out infinite}}
.white{{filter:brightness(0) invert(1)}}
.big{{fill:#00ff41;font-size:28px;font-weight:700;text-anchor:middle}}
.card{{fill:#161b22;stroke:#00ff41;stroke-opacity:.4;animation:glow 3s ease-in-out infinite alternate}}
.bar-bg{{fill:#161b22}}
.bar-label{{fill:#c9d1d9;font-size:12.5px;font-weight:600}}
.bar-pct{{font-size:11px;font-weight:600}}
.streak-val{{fill:#00ff41;font-size:32px;font-weight:700;text-anchor:middle}}
.streak-lbl{{fill:#8b949e;font-size:11px;text-anchor:middle}}
.streak-sub{{fill:#e6edf3;font-size:10px;text-anchor:middle}}
.stat-val{{fill:#00ff41;font-size:24px;font-weight:700;text-anchor:middle}}
.stat-lbl{{fill:#8b949e;font-size:10px;text-anchor:middle}}
.stat-icon{{font-size:18px;text-anchor:middle}}
.trophy-val{{font-size:20px;font-weight:700;text-anchor:middle}}
.trophy-lbl{{fill:#8b949e;font-size:9.5px;text-anchor:middle}}
.trophy-tier{{font-size:9px;font-weight:600;text-anchor:middle}}
.shimmer{{animation:shimmer 2s ease-in-out infinite}}
@keyframes enter{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
@keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-5px)}}}}
@keyframes glow{{from{{stroke-opacity:.3}}to{{stroke-opacity:1}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
@keyframes shimmer{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}
@keyframes fadein{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes countin{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;opacity:1!important}}}}
"""


def svg_wrap(w: int, h: int, body: str, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(label)}">'
        f'<style>{BASE_CSS}</style>'
        f'<rect class="panel" x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="14"/>'
        f'{body}</svg>'
    )


# ---------------------------------------------------------------------------
# ① Stats Card SVG
# ---------------------------------------------------------------------------

def build_stats_card_svg(gql_user: dict | None, repos: list[dict], total_merged: int) -> str:
    W, H = 800, 180
    PAD  = 28

    cc      = (gql_user or {}).get("contributionsCollection", {})
    commits = cc.get("totalCommitContributions", 0)
    prs_merged = (gql_user or {}).get("pullRequests", {}).get("totalCount") or total_merged
    issues  = (gql_user or {}).get("issues", {}).get("totalCount", 0)
    followers = (gql_user or {}).get("followers", {}).get("totalCount", 0)
    stars   = sum(r.get("stargazers_count", 0) or r.get("stargazerCount", 0) for r in repos)
    n_repos = len([r for r in repos if not r.get("fork") and not r.get("archived")])

    name    = escape((gql_user or {}).get("name") or USER)

    metrics = [
        ("🔥", _fmt(commits),   "Commits (yr)"),
        ("⭐", _fmt(stars),     "Stars"),
        ("🔀", _fmt(prs_merged),"PRs Merged"),
        ("🐛", _fmt(issues),    "Issues Closed"),
        ("👥", _fmt(followers), "Followers"),
        ("📦", _fmt(n_repos),   "Public Repos"),
    ]

    n   = len(metrics)
    cw  = (W - 2*PAD - 12*(n-1)) / n
    cy  = H // 2 + 12

    parts = [
        f'<text class="title" x="{PAD}" y="28">$ gh api /users/{escape(USER)}'
        f'<tspan class="cursor"> ▌</tspan></text>',
        f'<text class="muted" x="{W-PAD}" y="28" text-anchor="end">Updated: '
        f'{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</text>',
        # divider line
        f'<line x1="{PAD}" y1="38" x2="{W-PAD}" y2="38" stroke="#21262d" stroke-width="1"/>',
    ]

    for i, (icon, val, lbl) in enumerate(metrics):
        x   = PAD + i * (cw + 12) + cw / 2
        d   = i * 0.1
        # card bg
        cx0 = PAD + i * (cw + 12)
        parts.append(
            f'<g class="enter" style="animation-delay:{d:.1f}s">'
            f'<rect x="{cx0:.1f}" y="44" width="{cw:.1f}" height="{H-60}" rx="10" '
            f'fill="#161b22" stroke="#21262d"/>'
            f'<text class="stat-icon" x="{x:.1f}" y="{cy-28}">{icon}</text>'
            f'<text class="stat-val" x="{x:.1f}" y="{cy}">{escape(val)}</text>'
            f'<text class="stat-lbl" x="{x:.1f}" y="{cy+16}">{escape(lbl)}</text>'
            f'</g>'
        )

    return svg_wrap(W, H, "".join(parts), f"{USER}'s GitHub Stats")


def _fmt(n: int) -> str:
    if n >= 1_000:
        return f"{n/1000:.1f}k"
    return str(n)


# ---------------------------------------------------------------------------
# ② Streak SVG
# ---------------------------------------------------------------------------

def build_streak_svg(weeks: list[dict]) -> str:
    W, H = 800, 155
    PAD  = 28
    current, longest, total = calculate_streaks(weeks)

    # Date ranges for display
    today       = datetime.now(timezone.utc).date()
    start_label = (today - timedelta(days=current)).strftime("%b %d") if current else "—"
    end_label   = today.strftime("%b %d")

    panels = [
        ("🔥", "Total Contributions", _fmt(total), "This Year"),
        ("📅", "Current Streak",       f"{current} day{'s' if current != 1 else ''}",
         f"{start_label} – {end_label}" if current else "No active streak"),
        ("🏅", "Longest Streak",       f"{longest} day{'s' if longest != 1 else ''}", "All time"),
    ]

    col_w = (W - 2*PAD - 24) / 3
    parts = []

    for i, (icon, label, val, sub) in enumerate(panels):
        x0   = PAD + i * (col_w + 12)
        cx   = x0 + col_w / 2
        d    = i * 0.15
        accent = "#00ff41" if i == 1 and current > 0 else ("#ffd700" if i == 2 else "#6e7681")
        parts.append(
            f'<g class="enter" style="animation-delay:{d:.1f}s">'
            f'<rect x="{x0:.1f}" y="8" width="{col_w:.1f}" height="{H-16}" rx="10" '
            f'fill="#161b22" stroke="{accent}" stroke-opacity=".5"/>'
            f'<text font-size="22" text-anchor="middle" x="{cx:.1f}" y="42">{icon}</text>'
            f'<text font-size="10" fill="#8b949e" text-anchor="middle" x="{cx:.1f}" y="56">'
            f'{escape(label)}</text>'
            f'<text class="streak-val" fill="{accent}" x="{cx:.1f}" y="92">'
            f'{escape(val)}</text>'
            f'<text class="streak-sub" x="{cx:.1f}" y="112">{escape(sub)}</text>'
            f'</g>'
        )

    # Dividers
    for i in (1, 2):
        dx = PAD + i * (col_w + 12) - 6
        parts.append(f'<line x1="{dx:.1f}" y1="20" x2="{dx:.1f}" y2="{H-20}" '
                     f'stroke="#21262d" stroke-width="1"/>')

    return svg_wrap(W, H, "".join(parts), f"{USER}'s GitHub Streak")


# ---------------------------------------------------------------------------
# ③ Activity / Contribution Graph SVG
# ---------------------------------------------------------------------------

def build_activity_graph_svg(weeks: list[dict]) -> str:
    W, H   = 800, 195
    CELL   = 11   # cell size
    GAP    = 3    # gap between cells
    STEP   = CELL + GAP   # 14px per cell
    LEFT   = 44   # space for day labels
    TOP    = 58   # space for title + month labels
    PAD_R  = 10

    # Flatten all days
    all_days: list[dict] = []
    for week in weeks:
        all_days.extend(week.get("contributionDays", []))
    all_days.sort(key=lambda d: d["date"])
    max_count = max((d["contributionCount"] for d in all_days), default=1)
    total_yr  = sum(d["contributionCount"] for d in all_days)

    # Build week grid (pad to exactly 52 weeks displayed)
    displayed_weeks = weeks[-52:] if len(weeks) > 52 else weeks

    parts = [
        f'<text class="title" x="28" y="26">$ git log --graph<tspan class="cursor"> ▌</tspan></text>',
        f'<text class="muted" x="{W-28}" y="26" text-anchor="end">'
        f'{_fmt(total_yr)} contributions in the last year</text>',
        f'<line x1="28" y1="34" x2="{W-28}" y2="34" stroke="#21262d" stroke-width="1"/>',
    ]

    # Day-of-week labels (left axis) — Sun=0…Sat=6
    for row, label in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
        if row % 2 == 1:   # only Mon, Wed, Fri for brevity
            y = TOP + row * STEP + CELL
            parts.append(f'<text fill="#8b949e" font-size="9" text-anchor="end" '
                         f'x="{LEFT-4}" y="{y}">{label}</text>')

    # Month labels (top axis)
    prev_month = None
    for wi, week in enumerate(displayed_weeks):
        if not week.get("contributionDays"):
            continue
        first_date = week["contributionDays"][0]["date"]
        month_abbr = datetime.strptime(first_date, "%Y-%m-%d").strftime("%b")
        if month_abbr != prev_month:
            x = LEFT + wi * STEP
            parts.append(f'<text fill="#8b949e" font-size="9" x="{x}" y="{TOP-6}">'
                         f'{month_abbr}</text>')
            prev_month = month_abbr

    # Cells
    for wi, week in enumerate(displayed_weeks):
        for di, day in enumerate(week.get("contributionDays", [])):
            count = day["contributionCount"]
            color = contrib_color(count, max_count)
            cx    = LEFT + wi * STEP
            cy    = TOP  + di * STEP
            tip   = f"{count} contribution{'s' if count != 1 else ''} on {day['date']}"
            anim_d = (wi * 7 + di) * 0.004
            parts.append(
                f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{color}" style="animation:fadein .8s ease-out {anim_d:.3f}s both">'
                f'<title>{escape(tip)}</title></rect>'
            )

    # Legend
    legend_x = LEFT
    legend_y  = TOP + 7 * STEP + 10
    parts.append(f'<text fill="#8b949e" font-size="9" x="{legend_x}" y="{legend_y+CELL}">Less</text>')
    for i, col in enumerate(["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]):
        lx = legend_x + 36 + i * (CELL + 3)
        parts.append(f'<rect x="{lx}" y="{legend_y}" width="{CELL}" height="{CELL}" '
                     f'rx="2" fill="{col}"/>')
    mx = legend_x + 36 + 5 * (CELL + 3) + 4
    parts.append(f'<text fill="#8b949e" font-size="9" x="{mx}" y="{legend_y+CELL}">More</text>')

    return svg_wrap(W, H, "".join(parts), f"{USER}'s contribution graph")


# ---------------------------------------------------------------------------
# ④ Trophies SVG
# ---------------------------------------------------------------------------

def build_trophies_svg(gql_user: dict | None, repos: list[dict], total_merged: int) -> str:
    cc      = (gql_user or {}).get("contributionsCollection", {})
    commits = cc.get("totalCommitContributions", 0)
    prs     = (gql_user or {}).get("pullRequests", {}).get("totalCount") or total_merged
    issues  = (gql_user or {}).get("issues", {}).get("totalCount", 0)
    followers = (gql_user or {}).get("followers", {}).get("totalCount", 0)
    stars   = sum(r.get("stargazers_count", 0) or r.get("stargazerCount", 0) for r in repos)
    n_repos = len([r for r in repos if not r.get("fork") and not r.get("archived")])

    trophies = [
        ("🔥", commits,   "Commits"),
        ("🔀", prs,       "Pull Req"),
        ("⭐", stars,     "Stars"),
        ("👥", followers, "Followers"),
        ("📦", n_repos,   "Repos"),
        ("🐛", issues,    "Issues"),
    ]

    W    = 800
    PAD  = 28
    TW   = 118   # trophy card width
    TH   = 105   # trophy card height
    COLS = 6
    ROWS = math.ceil(len(trophies) / COLS)
    H    = PAD + 36 + ROWS * (TH + 14) + PAD

    parts = [
        f'<text class="title" x="{PAD}" y="28">$ ls ~/trophies'
        f'<tspan class="cursor"> ▌</tspan></text>',
        f'<line x1="{PAD}" y1="36" x2="{W-PAD}" y2="36" stroke="#21262d" stroke-width="1"/>',
    ]

    total_w = COLS * TW + (COLS-1) * 12
    x_start = (W - total_w) / 2

    for i, (icon, value, label) in enumerate(trophies):
        row, col = divmod(i, COLS)
        x0  = x_start + col * (TW + 12)
        y0  = 44 + row * (TH + 14)
        cx  = x0 + TW / 2
        tier_name, tier_color = trophy_tier(value)
        glow_anim = "shimmer" if tier_name in ("Gold", "Platinum", "Ruby", "SSS") else "none"
        d   = i * 0.1

        # Tier-specific glow border
        border_op = ".7" if tier_name not in ("Unknown",) else ".25"

        parts.append(
            f'<g class="enter" style="animation-delay:{d:.1f}s">'
            # card background
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{TW}" height="{TH}" rx="10" '
            f'fill="#161b22" stroke="{tier_color}" stroke-opacity="{border_op}"/>'
            # icon
            f'<text font-size="26" text-anchor="middle" x="{cx:.1f}" y="{y0+33}">{icon}</text>'
            # value
            f'<text class="trophy-val" fill="{tier_color}" '
            f'style="animation:{glow_anim} 2s ease-in-out infinite" '
            f'x="{cx:.1f}" y="{y0+58}">{escape(_fmt(value))}</text>'
            # label
            f'<text class="trophy-lbl" x="{cx:.1f}" y="{y0+73}">{escape(label)}</text>'
            # tier badge
            f'<rect x="{x0+TW/2-22:.1f}" y="{y0+TH-20:.1f}" width="44" height="15" rx="7" '
            f'fill="{tier_color}" fill-opacity=".18"/>'
            f'<text class="trophy-tier" fill="{tier_color}" '
            f'x="{cx:.1f}" y="{y0+TH-9:.1f}">{escape(tier_name)}</text>'
            f'</g>'
        )

    return svg_wrap(W, H, "".join(parts), f"{USER}'s GitHub Trophies")


# ---------------------------------------------------------------------------
# Existing SVG builders (tech-stack, languages, simple stats, social)
# ---------------------------------------------------------------------------
_icon_cache: dict[str, str | None] = {}


def data_uri(raw: bytes) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode()


def icon_uri(slug: str) -> str | None:
    if slug in _icon_cache:
        return _icon_cache[slug]
    folder = CATALOG[slug][2]
    uri    = None
    for variant in ("original", "plain"):
        raw = http(f"{DEVICON}{folder}/{folder}-{variant}.svg", binary=True)
        if raw and b"<svg" in raw[:2000]:
            uri = data_uri(raw)
            break
    _icon_cache[slug] = uri
    return uri


def tile(slug: str, x: int, y: int, idx: int, repos_using: int) -> str:
    label, _, _, white = CATALOG[slug]
    delay = (idx % 14) * 0.1
    live  = repos_using > 0
    uri   = icon_uri(slug)
    if uri:
        cls   = ' class="white"' if white else ""
        glyph = f'<image href="{uri}" x="{x+12}" y="{y+12}" width="32" height="32"{cls}/>'
    else:
        glyph = (f'<text x="{x+28}" y="{y+33}" text-anchor="middle" class="cat">'
                 f'{escape(label[:2])}</text>')
    dot = f'<circle class="dot" cx="{x+50}" cy="{y+6}" r="3.5"/>' if live else ""
    tip = (f"{label} · {repos_using} repo{'s' if repos_using != 1 else ''}"
           if live else label)
    return (
        f'<g class="enter" style="animation-delay:{delay:.1f}s">'
        f'<g class="float" style="animation-delay:{delay:.1f}s">'
        f'<title>{escape(tip)}</title>'
        f'<rect class="tile{" live" if live else ""}" x="{x}" y="{y}" width="56" height="56" rx="12"/>'
        f'{glyph}{dot}'
        f'<text class="lbl" x="{x+28}" y="{y+72}">{escape(label)}</text>'
        f'</g></g>'
    )


def build_tech_svg(slugs: list[str], scores: Counter) -> str:
    W, PAD, T, GAP, ROW = 800, 28, 56, 18, 56 + 34
    cols  = (W - 2 * PAD + GAP) // (T + GAP)
    parts = [
        f'<text class="title" x="{PAD}" y="34">$ ls ~/stack'
        f'<tspan class="cursor"> ▌</tspan></text>',
        f'<circle class="dot" cx="{W-175}" cy="30" r="3.5"/>'
        f'<text class="muted" x="{W-165}" y="34">used in my repos</text>',
    ]
    y, idx = 62, 0
    for cat in CATEGORIES:
        items = [s for s in slugs if CATALOG[s][1] == cat]
        if not items:
            continue
        parts.append(f'<text class="cat" x="{PAD}" y="{y}">// {escape(cat)}</text>')
        y += 14
        for i, slug in enumerate(items):
            r, c = divmod(i, cols)
            parts.append(tile(slug, PAD + c * (T + GAP), y + r * ROW, idx, scores.get(slug, 0)))
            idx += 1
        y += math.ceil(len(items) / cols) * ROW + 14
    return svg_wrap(W, y + 6, "".join(parts), "Animated tech stack generated from my repositories")


def build_languages_svg(lang_bytes: Counter) -> str:
    W, PAD = 800, 28
    total  = sum(lang_bytes.values()) or 1
    top    = lang_bytes.most_common(8)
    parts  = [
        f'<text class="title" x="{PAD}" y="34">$ cloc ~/repos'
        f'<tspan class="cursor"> ▌</tspan></text>'
    ]
    y = 62
    bar_x, bar_w = 200, 460
    for i, (lang, b) in enumerate(top):
        pct    = b / total * 100
        fill_w = max(4, round(bar_w * pct / 100, 1))
        color  = LANG_COLORS.get(lang, "#00ff41")
        gid    = f"g{i}"
        parts.append(
            f'<defs><linearGradient id="{gid}" x1="0" x2="1" y1="0" y2="0">'
            f'<stop offset="0%" stop-color="{color}"/>'
            f'<stop offset="100%" stop-color="{color}" stop-opacity="0.55"/>'
            f'</linearGradient></defs>'
            f'<g class="enter" style="animation-delay:{i*0.12:.2f}s">'
            f'<text class="bar-label" x="{PAD}" y="{y+13}">{escape(lang)}</text>'
            f'<rect class="bar-bg" x="{bar_x}" y="{y}" width="{bar_w}" height="16" rx="8"/>'
            f'<rect x="{bar_x}" y="{y}" width="0" height="16" rx="8" fill="url(#{gid})">'
            f'<animate attributeName="width" from="0" to="{fill_w}" dur="1.2s" '
            f'begin="{i*0.12:.2f}s" fill="freeze" '
            f'calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></rect>'
            f'<text class="bar-pct" x="{bar_x+bar_w+12}" y="{y+13}" fill="{color}">'
            f'{pct:.1f}%</text></g>'
        )
        y += 32
    return svg_wrap(W, y + 12, "".join(parts), "Most used languages across my repositories")


def build_simple_stats_svg(stats: list[tuple[str, str]]) -> str:
    W, H, PAD, GAP = 800, 130, 20, 16
    n  = len(stats)
    cw = (W - 2 * PAD - GAP * (n - 1)) / n
    parts = []
    for i, (value, label) in enumerate(stats):
        x = PAD + i * (cw + GAP)
        parts.append(
            f'<g class="enter" style="animation-delay:{i*0.15:.2f}s">'
            f'<rect class="card" x="{x:.1f}" y="22" width="{cw:.1f}" height="86" rx="12" '
            f'style="animation-delay:{i*0.4:.1f}s"/>'
            f'<text class="big" x="{x+cw/2:.1f}" y="68">{escape(value)}</text>'
            f'<text class="lbl" x="{x+cw/2:.1f}" y="92">{escape(label)}</text></g>'
        )
    return svg_wrap(W, H, "".join(parts), "GitHub stats")


def build_social_svg(file_name: str, delay: float, accent: str = "#00ff41") -> str | None:
    raw = http(
        f"https://raw.githubusercontent.com/gauravghongde/social-icons/master/SVG/Color/{file_name}",
        binary=True,
    )
    if not raw:
        return None
    css = (
        "@keyframes hop{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-8px) scale(1.1)}}"
        "@keyframes ring{0%,100%{opacity:0;r:22}60%{opacity:1;r:28}}"
        f".i{{animation:hop 2.8s ease-in-out {delay:.1f}s infinite;transform-origin:center}}"
        f".ring{{fill:none;stroke:{accent};stroke-width:2;opacity:0;r:22;cx:32;cy:44}}"
        ".wrap:hover .ring{animation:ring .6s ease-out forwards}"
        ".wrap:hover .i{animation:hop .5s ease-out}"
        "@media (prefers-reduced-motion:reduce){.i{animation:none}.ring{display:none}}"
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 80" width="64" height="80">'
        f'<style>{css}</style>'
        '<g class="wrap">'
        f'<image class="i" href="{data_uri(raw)}" x="8" y="16" width="48" height="48"/>'
        '<circle class="ring"/>'
        '</g></svg>'
    )


# ---------------------------------------------------------------------------
# README OSS block
# ---------------------------------------------------------------------------

def build_oss_markdown(total: int, items: list[dict]) -> str:
    by_repo: Counter = Counter()
    for it in items:
        by_repo[it["repository_url"].split("/repos/")[1]] += 1
    lines = ["#### 🤝 Projects I've contributed to", ""]
    badges = []
    for repo, _ in by_repo.most_common(8):
        badges.append(
            f'<a href="https://github.com/{repo}"><img alt="{repo}" '
            f'src="https://img.shields.io/github/stars/{repo}?style=for-the-badge'
            f'&logo=github&label={repo.replace("-","--")}&color=00ff41&labelColor=0d1117" /></a>'
        )
    if badges:
        lines += ['<p align="center">', "  " + "\n  ".join(badges), "</p>", ""]
    lines += [
        f"#### ✅ Recently merged pull requests ({total} merged in total)",
        "", "| Project | Pull request | Merged |", "|---|---|---|",
    ]
    for it in items[:10]:
        repo   = it["repository_url"].split("/repos/")[1]
        title  = it["title"].replace("|", "\\|")
        title  = title if len(title) <= 70 else title[:67] + "..."
        merged = ((it.get("pull_request") or {}).get("merged_at") or it.get("closed_at") or "")[:10]
        lines.append(f"| [{repo}](https://github.com/{repo}) | [#{it['number']} {title}]({it['html_url']}) | {merged} |")
    if not items:
        lines.append("| _Nothing yet, first PR coming soon_ | | |")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines += ["", f"<sub>Auto-updated {stamp}</sub>"]
    return "\n".join(lines)


def replace_block(text: str, start: str, end: str, content: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    return pattern.sub(lambda _: f"{start}\n{content}\n{end}", text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    repos = fetch_repos()
    if not repos:
        print("No repos returned (rate limit or network). Leaving files untouched.", file=sys.stderr)
        return 1
    ASSETS.mkdir(exist_ok=True)
    scan = repos[:MAX_REPOS]

    scores:     Counter = Counter()
    lang_bytes: Counter = Counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for slugs, langs in pool.map(repo_signals, scan):
            scores.update(slugs)
            lang_bytes.update(langs)

    total_merged, items = merged_prs()
    ext_repos = list(dict.fromkeys(it["repository_url"].split("/repos/")[1] for it in items))
    scores.update(contributed_repo_slugs(ext_repos))

    # GraphQL contribution data (requires token)
    gql_user = fetch_contribution_data()

    # --- generate contribution-based SVGs ---
    if gql_user:
        cal   = gql_user.get("contributionsCollection", {}).get("contributionCalendar", {})
        weeks = cal.get("weeks", [])

        (ASSETS / "stats-card.svg").write_text(
            build_stats_card_svg(gql_user, repos, total_merged), encoding="utf-8")
        (ASSETS / "streak.svg").write_text(
            build_streak_svg(weeks), encoding="utf-8")
        (ASSETS / "activity-graph.svg").write_text(
            build_activity_graph_svg(weeks), encoding="utf-8")
        (ASSETS / "trophies.svg").write_text(
            build_trophies_svg(gql_user, repos, total_merged), encoding="utf-8")
        print("GraphQL OK: stats-card, streak, activity-graph, trophies generated.")
    else:
        print("No GraphQL data – stats-card/streak/activity-graph/trophies skipped.", file=sys.stderr)

    # --- tech stack + language bars ---
    pool_slugs = set(PINNED) | {s for s, v in scores.items() if v > 0 and s in CATALOG}
    ordered = sorted(
        pool_slugs,
        key=lambda s: (-scores.get(s, 0), PINNED.index(s) if s in PINNED else 99),
    )
    (ASSETS / "tech-stack.svg").write_text(build_tech_svg(ordered, scores), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(build_languages_svg(lang_bytes), encoding="utf-8")

    # --- simple stats card (backward compat) ---
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    simple_stats = [
        (str(total_merged),   "merged PRs (OSS)"),
        (str(open_prs_count()), "open PRs"),
        (str(len(repos)),     "public repos"),
        (str(stars),          "stars earned"),
    ]
    (ASSETS / "stats.svg").write_text(build_simple_stats_svg(simple_stats), encoding="utf-8")

    # --- social icons ---
    for fname, out, delay, accent in [
        ("LinkedIN.svg", "linkedin", 0.0,  "#0077b5"),
        ("Twitter.svg",  "twitter",  0.35, "#1d9bf0"),
        ("Gmail.svg",    "gmail",    0.70, "#ea4335"),
    ]:
        svg = build_social_svg(fname, delay, accent)
        if svg:
            (ASSETS / f"social-{out}.svg").write_text(svg, encoding="utf-8")

    # --- README OSS block ---
    if README.exists():
        text = README.read_text(encoding="utf-8")
        text = replace_block(text, "<!--OSS:START-->", "<!--OSS:END-->",
                             build_oss_markdown(total_merged, items))
        README.write_text(text, encoding="utf-8")

    print(
        f"repos={len(repos)} merged_ext={total_merged} icons={len(ordered)} "
        f"detected={sorted(s for s, v in scores.items() if v > 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
