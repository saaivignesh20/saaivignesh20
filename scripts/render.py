"""Render the profile's live parts.

Writes the header and stats cards (light and dark SVGs) into --out, and rewrites the
"recently shipped" list between the shipped markers in README.md: open-source work from
GitHub's GraphQL API, closed-source releases from the products' public version pages.
Standard library only. Needs GITHUB_TOKEN (the workflow's own token is enough).
"""

import argparse
import datetime as dt
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = "saaivignesh20"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"
THEMES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "fg": "#e6edf3", "muted": "#8b949e",
             "accent": "#a78bfa", "bar": "#7c5ce0"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "fg": "#1f2328", "muted": "#59636e",
              "accent": "#6d3dd9", "bar": "#6d3dd9"},
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionYears
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
      commitContributionsByRepository(maxRepositories: 25) {
        repository {
          name nameWithOwner url description isArchived isFork isPrivate owner { login }
          latestRelease { tagName url }
          defaultBranchRef { target { ... on Commit {
            history(first: 30) { nodes { messageHeadline committedDate url author { user { login } } } }
          } } }
        }
      }
    }
  }
}"""
UA = {"User-Agent": "saaivignesh20-profile (+https://github.com/saaivignesh20/saaivignesh20)"}
ASSETS = "https://raw.githubusercontent.com/saaivignesh20/saaivignesh20/main/assets"
OPEN = f'<img src="{ASSETS}/code.svg" alt="open source" title="Open source" width="16" height="16">'
CLOSED = f'<img src="{ASSETS}/lock.svg" alt="closed source" title="Closed source" width="16" height="16">'
SHIPPED_OPEN = 4


def graphql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def all_time_total(years):
    fields = " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z")'
        " { contributionCalendar { totalContributions } }"
        for y in years
    )
    data = graphql(f"query($login: String!) {{ user(login: $login) {{ {fields} }} }}", {"login": LOGIN})
    return sum(v["contributionCalendar"]["totalContributions"] for v in data["user"].values())


def streaks(counts):
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today is not over yet
        i -= 1
    current = 0
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


# The Deep Variance mark (triangle with a node graph), sampled from the brand PNG to 28x22 cells; 0-7 is ink coverage.
DV_MARK = [
    "0000000000000330000000000000",
    "0000000000002772000000000000",
    "0000000000005766000000000000",
    "0000000000037327300000000000",
    "0000000000166005600000000000",
    "0000000000472001303630000000",
    "0000000001750000017771000000",
    "0000000005710000006760000000",
    "0000000027300000016410000000",
    "0000000066000000052000000000",
    "0000000472266200350020000000",
    "0000001750577656610361000000",
    "0000005710477313500175000000",
    "0000027400621000530047200000",
    "0000056003400000161016600000",
    "0000373016000000067503730000",
    "0000662673000000177710560000",
    "0004724774000000057500174000",
    "0017403773000000001000047200",
    "0057100220000000000000017600",
    "0276444444441000144555556730",
    "0266666667750000466666666620",
]


def header_svg(theme):
    """Name card with a denoising grid: noise resolves into the Deep Variance mark over 8 sampler steps."""
    t = THEMES[theme]
    w, h = 1280, 300
    rows, cols, cell, gap = len(DV_MARK), len(DV_MARK[0]), 8, 2
    gx = w - 56 - cols * (cell + gap) + gap
    gy = (h - rows * (cell + gap) - 24) // 2
    rng = random.Random(20)

    def target(r, c):
        v = int(DV_MARK[r][c])
        return 1.0 if v >= 4 else 0.45 if v >= 2 else 0.0

    steps = 8
    alpha_bar = [math.cos((k / steps) * math.pi / 2) ** 2 for k in range(steps, -1, -1)]
    key_times = ";".join(f"{k / 10:.1f}" for k in range(steps + 1)) + ";1"
    cells = []
    for r in range(rows):
        for c in range(cols):
            x0 = target(r, c)
            vals = []
            for a in alpha_bar:
                v = math.sqrt(a) * x0 + math.sqrt(1 - a) * rng.gauss(0.35, 0.3)
                vals.append(min(1.0, max(0.0, v)))
            vals.append(vals[-1])
            ops = ";".join(f"{0.07 + 0.93 * v:.2f}" for v in vals)
            color = t["accent"]
            cells.append(
                f'<rect x="{gx + c * (cell + gap)}" y="{gy + r * (cell + gap)}" width="{cell}" height="{cell}" rx="1.5" '
                f'fill="{color}"><animate attributeName="fill-opacity" values="{ops}" keyTimes="{key_times}" '
                f'dur="7s" repeatCount="indefinite"/></rect>'
            )
    label_y = gy + rows * (cell + gap) + 18
    labels = []
    for k in range(steps + 1):
        shown = ";".join("1" if j == k or (k == steps and j > steps) else "0" for j in range(steps + 2))
        text = "pure noise" if k == 0 else f"denoising step {k} of {steps}"
        labels.append(
            f'<text x="{gx}" y="{label_y}" opacity="0">{text}<animate attributeName="opacity" values="{shown}" '
            f'keyTimes="{key_times}" calcMode="discrete" dur="7s" repeatCount="indefinite"/></text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Saai Vignesh Premanand, CTO and co-founder of Deep Variance. Building efficient diffusion inference.">
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
<g font-family="{SANS}">
<text x="56" y="92" fill="{t['accent']}" font-family="{MONO}" font-size="15" letter-spacing="2.5">CTO AND CO-FOUNDER, DEEP VARIANCE</text>
<text x="54" y="152" fill="{t['fg']}" font-size="50" font-weight="700">Saai Vignesh Premanand</text>
<text x="56" y="196" fill="{t['muted']}" font-size="24">Building efficient diffusion inference.</text>
<text x="56" y="244" fill="{t['muted']}" font-family="{MONO}" font-size="15">DV4  |  Piku  |  Overdrift</text>
</g>
<g>{''.join(cells)}</g>
<g font-family="{MONO}" font-size="13" fill="{t['muted']}">{''.join(labels)}</g>
</svg>"""


def stats_svg(theme, metrics, weeks, updated):
    t = THEMES[theme]
    w, h = 1280, 250
    tiles = []
    tile_w = (w - 112) / len(metrics)
    for i, (value, label) in enumerate(metrics):
        x = 56 + i * tile_w
        tiles.append(
            f'<text x="{x:.0f}" y="112" fill="{t["fg"]}" font-size="38" font-weight="700">{escape(value)}</text>'
            f'<text x="{x:.0f}" y="140" fill="{t["muted"]}" font-size="15">{escape(label)}</text>'
        )
    top = max(weeks) or 1
    bar_w = (w - 112) / len(weeks)
    bars = []
    for i, v in enumerate(weeks):
        bh = max(2.0, 56 * v / top) if v else 2.0
        bars.append(
            f'<rect x="{56 + i * bar_w:.1f}" y="{222 - bh:.1f}" width="{bar_w - 3:.1f}" height="{bh:.1f}" rx="1.5" '
            f'fill="{t["bar"]}" fill-opacity="{0.25 if not v else 0.45 + 0.55 * v / top:.2f}"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub activity: {', '.join(f'{v} {l}' for v, l in metrics)}">
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
<g font-family="{SANS}">
<text x="56" y="52" fill="{t['accent']}" font-family="{MONO}" font-size="14" letter-spacing="2">GITHUB ACTIVITY, PUBLIC AND PRIVATE</text>
<text x="{w - 56}" y="52" fill="{t['muted']}" font-family="{MONO}" font-size="13" text-anchor="end">updated {updated}</text>
{''.join(tiles)}
</g>
<g>{''.join(bars)}</g>
</svg>"""


def md_escape(text):
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as resp:
        return resp.read().decode()


def dv4_release():
    v = json.loads(fetch("https://dv4.ai/v1/version"))
    return f"v{v['version']}", int(v["build"])


def piku_release():
    found = re.search(r"Version ([\d.]+) \(build (\d+)\)", fetch("https://piku.dv4.ai/"))
    if not found:
        raise ValueError("piku.dv4.ai shows no version")
    return f"v{found[1]}", int(found[2])


# Closed-source products: name, what it is, how to read the live release.
PRODUCTS = [
    ("DV4", "agentic AI video platform", dv4_release),
    ("Piku", "image generation API", piku_release),
]


def day_of(stamp):
    return dt.date.fromisoformat(stamp[:10])


def closed_picks(state_path, today):
    """One entry per product, dated the day its current release was first seen (state kept in state_path)."""
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    for name, _, read in PRODUCTS:
        try:
            version, build = read()
        except (OSError, ValueError, KeyError) as e:
            print(f"{name}: release not readable, showing the last one seen ({e})", file=sys.stderr)
            continue
        seen = state.get(name)
        if not seen or (seen["version"], seen["build"]) != (version, build):
            state[name] = {"version": version, "build": build, "date": today.isoformat()}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    picks = []
    for name, what, _ in PRODUCTS:
        if name in state:
            r = state[name]
            picks.append((day_of(r["date"]), CLOSED, f"**{name}**", f"`{r['version']}` build {r['build']}, {what}"))
    return picks


def open_picks(contributions):
    """Latest commit by LOGIN (not bots, not merges) in each described, unarchived public repo committed to this year."""
    picks = []
    for item in contributions:
        repo = item["repository"]
        if (repo["isPrivate"] or repo["isFork"] or repo["isArchived"] or repo["name"] == LOGIN
                or not repo["description"] or not repo["defaultBranchRef"]):
            continue
        history = repo["defaultBranchRef"]["target"]["history"]["nodes"]
        commit = next((c for c in history if ((c["author"] or {}).get("user") or {}).get("login") == LOGIN
                       and not c["messageHeadline"].startswith("Merge ")), None)
        if not commit:
            continue
        name = repo["name"] if repo["owner"]["login"] == LOGIN else repo["nameWithOwner"]
        release = repo["latestRelease"]
        tag = f" [`{release['tagName']}`]({release['url']})" if release else ""
        headline = f"[{md_escape(commit['messageHeadline'])}]({commit['url']})"
        picks.append((day_of(commit["committedDate"]), OPEN, f"[**{name}**]({repo['url']})", f"{tag.strip()} {headline}".strip()))
    return sorted(picks, key=lambda p: p[0], reverse=True)[:SHIPPED_OPEN]


def shipped_lines(picks):
    rows = ["| | Project | Shipped | Date |", "|:-:|---|---|---|"]
    for when, icon, project, shipped in sorted(picks, key=lambda p: p[0], reverse=True):
        rows.append(f"| {icon} | {project} | {shipped} | {when:%b} {when.day}, {when.year} |")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--state", default="state/releases.json")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    user = graphql(QUERY, {"login": LOGIN})["user"]
    coll = user["contributionsCollection"]
    cal = coll["contributionCalendar"]
    days = [d["contributionCount"] for wk in cal["weeks"] for d in wk["contributionDays"]]
    weeks = [sum(d["contributionCount"] for d in wk["contributionDays"]) for wk in cal["weeks"]]
    current, longest = streaks(days)
    metrics = [
        (f"{all_time_total(coll['contributionYears']):,}", "contributions, all time"),
        (f"{cal['totalContributions']:,}", "in the last 12 months"),
        (f"{current} days", "current streak"),
        (f"{longest} days", "longest streak (12 months)"),
        (f"{sum(1 for c in days if c)}", "active days (12 months)"),
    ]
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for theme in THEMES:
        (out / f"header-{theme}.svg").write_text(header_svg(theme))
        (out / f"stats-{theme}.svg").write_text(stats_svg(theme, metrics, weeks, updated))

    readme = Path(args.readme)
    text = readme.read_text()
    today = dt.datetime.now(dt.timezone.utc).date()
    picks = open_picks(coll["commitContributionsByRepository"]) + closed_picks(Path(args.state), today)
    block = "\n".join(["<!-- shipped:start -->", *shipped_lines(picks), "<!-- shipped:end -->"])
    new = re.sub(r"<!-- shipped:start -->.*?<!-- shipped:end -->", lambda _: block, text, flags=re.S)
    if new != text:
        readme.write_text(new)
    print(json.dumps({"metrics": metrics, "readme_changed": new != text}))


if __name__ == "__main__":
    main()
