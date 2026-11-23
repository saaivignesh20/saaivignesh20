"""Render the profile's live parts from GitHub's GraphQL API.

Writes the header and stats cards (light and dark SVGs) into --out, and rewrites the
"recently shipped" list between the shipped markers in README.md. Standard library only.
Needs GITHUB_TOKEN (the workflow's own token is enough: everything read here is public).
"""

import argparse
import datetime as dt
import json
import math
import os
import random
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = "saaivignesh20"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"
THEMES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "fg": "#e6edf3", "muted": "#8b949e",
             "accent": "#a78bfa", "cell_lo": (109, 61, 217), "cell_hi": (196, 181, 253), "bar": "#7c5ce0"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "fg": "#1f2328", "muted": "#59636e",
              "accent": "#6d3dd9", "cell_lo": (109, 61, 217), "cell_hi": (167, 139, 250), "bar": "#6d3dd9"},
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionYears
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    repositories(first: 10, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name url description isArchived
        latestRelease { tagName url }
        defaultBranchRef { target { ... on Commit {
          history(first: 20) { nodes { messageHeadline committedDate url author { user { login } } } }
        } } }
      }
    }
  }
}"""


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


def mix(lo, hi, t):
    return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(lo, hi))


def header_svg(theme):
    """Name card with a denoising grid: noise resolves into a video frame over 8 sampler steps."""
    t = THEMES[theme]
    w, h = 1280, 300
    cols, rows, cell, gap = 26, 14, 13, 3
    gx, gy = w - 56 - cols * (cell + gap) + gap, 34
    rng = random.Random(20)

    def target(r, c):
        fx, fy = c / (cols - 1), r / (rows - 1)
        frame = 0.06 <= fx <= 0.94 and 0.08 <= fy <= 0.92
        edge = frame and (fx < 0.12 or fx > 0.88 or fy < 0.18 or fy > 0.82)
        px, py = (fx - 0.40) / 0.30, (fy - 0.5) / 0.34  # play triangle pointing right
        tri = 0 <= px <= 1 and abs(py) <= 1 - px
        return 1.0 if tri else 0.55 if edge else 0.12 if frame else 0.0

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
            color = mix(t["cell_lo"], t["cell_hi"], c / (cols - 1))
            cells.append(
                f'<rect x="{gx + c * (cell + gap)}" y="{gy + r * (cell + gap)}" width="{cell}" height="{cell}" rx="2.5" '
                f'fill="{color}"><animate attributeName="fill-opacity" values="{ops}" keyTimes="{key_times}" '
                f'dur="7s" repeatCount="indefinite"/></rect>'
            )
    label_y = gy + rows * (cell + gap) + 22
    labels = []
    for k in range(steps + 1):
        shown = ";".join("1" if j == k or (k == steps and j > steps) else "0" for j in range(steps + 2))
        text = "pure noise" if k == 0 else f"denoising · step {k}/{steps}"
        labels.append(
            f'<text x="{gx}" y="{label_y}" opacity="0">{text}<animate attributeName="opacity" values="{shown}" '
            f'keyTimes="{key_times}" calcMode="discrete" dur="7s" repeatCount="indefinite"/></text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Saai Vignesh Premanand, CTO and co-founder of Deep Variance. Building efficient diffusion inference.">
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
<g font-family="{SANS}">
<text x="56" y="92" fill="{t['accent']}" font-family="{MONO}" font-size="15" letter-spacing="2.5">CTO &amp; CO-FOUNDER · DEEP VARIANCE</text>
<text x="54" y="152" fill="{t['fg']}" font-size="50" font-weight="700">Saai Vignesh Premanand</text>
<text x="56" y="196" fill="{t['muted']}" font-size="24">Building efficient diffusion inference.</text>
<text x="56" y="244" fill="{t['muted']}" font-family="{MONO}" font-size="15">DV4 · Piku · auto-tuning inference stack</text>
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
<text x="56" y="52" fill="{t['accent']}" font-family="{MONO}" font-size="14" letter-spacing="2">GITHUB ACTIVITY · PUBLIC AND PRIVATE CONTRIBUTIONS</text>
<text x="{w - 56}" y="52" fill="{t['muted']}" font-family="{MONO}" font-size="13" text-anchor="end">updated {updated}</text>
{''.join(tiles)}
</g>
<g>{''.join(bars)}</g>
</svg>"""


def md_escape(text):
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def shipped_lines(repos):
    """Latest commit by LOGIN (not bots) in each described, unarchived public repo; newest first."""
    picks = []
    for repo in repos:
        if repo["isArchived"] or repo["name"] == LOGIN or not repo["description"] or not repo["defaultBranchRef"]:
            continue
        history = repo["defaultBranchRef"]["target"]["history"]["nodes"]
        commit = next((c for c in history if ((c["author"] or {}).get("user") or {}).get("login") == LOGIN), None)
        if commit:
            picks.append((commit["committedDate"], repo, commit))
    lines = []
    for when, repo, commit in sorted(picks, key=lambda p: p[0], reverse=True)[:4]:
        day = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).strftime("%b %-d, %Y")
        release = repo["latestRelease"]
        tag = f" · [`{release['tagName']}`]({release['url']})" if release else ""
        lines.append(
            f"- [**{repo['name']}**]({repo['url']}){tag} · [{md_escape(commit['messageHeadline'])}]({commit['url']})"
            f" · {day}"
        )
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--readme", default="README.md")
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
    block = "\n".join(["<!-- shipped:start -->", *shipped_lines(user["repositories"]["nodes"]), "<!-- shipped:end -->"])
    new = re.sub(r"<!-- shipped:start -->.*?<!-- shipped:end -->", lambda _: block, text, flags=re.S)
    if new != text:
        readme.write_text(new)
    print(json.dumps({"metrics": metrics, "readme_changed": new != text}))


if __name__ == "__main__":
    main()
