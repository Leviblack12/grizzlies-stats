"""
After data.json exists, build links.md: one row per player with their widget
URL and a paste-ready iframe embed. Run AFTER run.py, passing the Pages base.

  python make_links.py https://USERNAME.github.io/grizzlies-stats
"""
import json
import sys

base = sys.argv[1].rstrip("/")
data = json.load(open("data.json"))

rows = []
for p in data:
    url = f"{base}/widget.html?id={p['player_id']}"
    iframe = f'<iframe src="{url}" width="250" height="240" style="border:0" loading="lazy"></iframe>'
    rows.append((p.get("team", ""), str(p.get("number", "")), p["name"], url, iframe))

rows.sort(key=lambda r: (r[0], r[1].zfill(3)))

with open("links.md", "w") as f:
    f.write("# Player widget links\n\n")
    f.write("Paste the **Widget URL** into each player's `statsUrl` column, "
            "or drop the **Embed code** straight into a Wix HTML element on their profile.\n\n")
    f.write("| Team | # | Player | Widget URL | Embed code |\n")
    f.write("|---|---|---|---|---|\n")
    for t, n, nm, url, ifr in rows:
        f.write(f"| {t} | {n} | {nm} | `{url}` | `{ifr}` |\n")

print(f"wrote links.md ({len(rows)} players)")
