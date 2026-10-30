#!/usr/bin/env python3
"""
The Haunted Repo: a ghost that reads your git history and tells you who haunts the code.
Runs 100% locally: git + Ollama (any open-weight model). No cloud, no API keys.

Usage:
    ollama pull gemma3
    python haunted_repo.py /path/to/repo --model gemma3 --out haunting.html
"""
import argparse, html, json, re, subprocess, time, urllib.request
from collections import defaultdict
from pathlib import Path

NOW = time.time()
YEAR = 365 * 86400

def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    return r.stdout.strip()

# ---------- 1. find the ghosts ----------
def find_ghosts(repo):
    ghosts = []

    # Forgotten files: last touched long ago
    last = {}
    for block in git(repo, "log", "--name-only", "--format=@%at|%an").split("@")[1:]:
        head, *files = block.splitlines()
        ts, author = head.split("|", 1)
        for f in filter(None, files):
            last.setdefault(f, (int(ts), author))
    tracked = set(git(repo, "ls-files").splitlines())
    for f, (ts, author) in last.items():
        age = (NOW - ts) / YEAR
        if f in tracked and age > 1:
            ghosts.append(dict(kind="Forgotten file", where=f, curse=min(10, int(age * 2) + 2),
                facts=f"Untouched for {age:.1f} years. Last author: {author}."))

    # Unfinished promises: TODO / FIXME / HACK / don't touch
    pat = r"(TODO|FIXME|HACK|XXX|don'?t touch|do not touch|here be dragons)"
    for line in git(repo, "grep", "-nIiE", pat).splitlines()[:60]:
        m = re.match(r"(.+?):(\d+):(.*)", line)
        if m:
            f, n, text = m.groups()
            ghosts.append(dict(kind="Unfinished promise", where=f"{f}:{n}", curse=4,
                facts=f"A comment left behind: \"{text.strip()[:140]}\""))

    # Deleted files: the dead
    dead = git(repo, "log", "--diff-filter=D", "--name-only", "--format=@%an|%ar").split("@")[1:]
    for block in dead[:25]:
        head, *files = block.splitlines()
        author, when = head.split("|", 1)
        for f in [x for x in files if x][:1]:
            ghosts.append(dict(kind="Deleted file", where=f, curse=5,
                facts=f"Deleted by {author}, {when}. It no longer exists, but it was here."))

    # Abandoned branches
    for line in git(repo, "for-each-ref", "refs/heads", "--format=%(refname:short)|%(committerdate:unix)|%(authorname)").splitlines():
        b, ts, author = line.split("|")
        age = (NOW - int(ts)) / YEAR
        if age > 0.25:
            ghosts.append(dict(kind="Abandoned branch", where=b, curse=min(10, int(age * 4) + 3),
                facts=f"Branch never merged or touched in {age:.1f} years. Last author: {author}."))
    return sorted(ghosts, key=lambda g: -g["curse"])

# ---------- 2. let the local model narrate ----------
SYSTEM = ("You are the ghost of a long-dead sysadmin who haunts this codebase. Write ONE short haunting "
          "(2-3 sentences) about the finding below. Be spooky AND funny: dry humor, developer in-jokes, "
          "theatrical dread. Use only the facts given. No markdown, no preamble.")

def narrate(g, model):
    prompt = f"{SYSTEM}\n\nType: {g['kind']}\nWhere: {g['where']}\nFacts: {g['facts']}"
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                             "options": {"temperature": 0.9}}).encode(),
            headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=120))["response"].strip()
    except Exception:
        return f"{g['facts']} The ghost is silent tonight (Ollama is not running), but it is watching."

# ---------- 3. render the report ----------
CSS = """
:root{--ink:#140b1f;--plum:#25133a;--pumpkin:#ff7b00;--bone:#f1e8d0;--blood:#c2183a;--moss:#8fb37a}
*{box-sizing:border-box}html{background:var(--ink)}
body{margin:0;color:var(--bone);font:18px/1.6 Georgia,'Palatino Linotype',serif;
 background:radial-gradient(ellipse at 50% -10%,#3b1d5e 0,var(--ink) 60%) fixed;
 padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0)}
main{max-width:760px;margin:0 auto;padding:56px 20px 80px}
h1{font:400 clamp(2.4rem,8vw,4.4rem)/1.05 'Creepster','Chiller',Georgia,serif;color:var(--pumpkin);
 letter-spacing:.03em;margin:0 0 8px;text-shadow:0 0 18px rgba(255,123,0,.55);animation:flicker 5s infinite}
@keyframes flicker{0%,18%,22%,62%,64%,100%{opacity:1}20%{opacity:.55}63%{opacity:.7}}
@media (prefers-reduced-motion:reduce){h1{animation:none}}
.sub{color:#b9a9d4;margin:0 0 36px;font-style:italic}
h2{font:400 1.7rem Georgia,serif;color:var(--bone);border-bottom:1px solid #4a2f6e;padding-bottom:6px;margin:44px 0 16px}
.cursed li{margin:0 0 10px;list-style:none;display:flex;gap:12px;align-items:baseline}
.cursed span.f{color:var(--moss);font-family:ui-monospace,Menlo,monospace;font-size:.85em;word-break:break-all}
.meter{flex:none;width:90px;height:8px;background:#3a2358;border-radius:4px;overflow:hidden}
.meter i{display:block;height:100%;background:linear-gradient(90deg,var(--pumpkin),var(--blood))}
article{background:var(--plum);border-left:4px solid var(--pumpkin);padding:16px 20px;margin:0 0 18px;border-radius:2px 10px 10px 2px}
article.Deleted{border-color:var(--blood)}article.Unfinished{border-color:var(--moss)}article.Abandoned{border-color:#8b6bd6}
.tag{font-size:.8rem;color:#b9a9d4}
.where{font:.85rem ui-monospace,Menlo,monospace;color:var(--moss);word-break:break-all;margin:2px 0 8px}
article p{margin:0}
footer{margin-top:56px;color:#8a78a8;font-size:.9rem;text-align:center}
"""

def render(repo_name, ghosts, stories, out):
    top = "".join(f"<li><div class=meter><i style='width:{g['curse']*10}%'></i></div>"
                  f"<span class=f>{html.escape(g['where'])}</span></li>" for g in ghosts[:6])
    cards = "".join(
        f"<article class='{g['kind'].split()[0]}'><div class=tag>{g['kind']} (curse level {g['curse']}/10)</div>"
        f"<div class=where>{html.escape(g['where'])}</div><p>{html.escape(s)}</p></article>"
        for g, s in zip(ghosts, stories))
    doc = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>The Haunting of {html.escape(repo_name)}</title>
<link href="https://fonts.googleapis.com/css2?family=Creepster&display=swap" rel=stylesheet>
<style>{CSS}</style></head><body><main>
<h1>The Haunting of {html.escape(repo_name)}</h1>
<p class=sub>{len(ghosts)} spirits found lingering in this codebase.</p>
<h2>Most cursed</h2><ul class=cursed style="padding:0">{top}</ul>
<h2>The hauntings</h2>{cards}
<footer>Narrated by a local open-weight model. No cloud was consulted. No ghosts were harmed.</footer>
</main></body></html>"""
    Path(out).write_text(doc, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--model", default="gemma3")
    ap.add_argument("--limit", type=int, default=15, help="max hauntings to narrate")
    ap.add_argument("--out", default="haunting.html")
    a = ap.parse_args()
    ghosts = find_ghosts(a.repo)[: a.limit]
    print(f"Found {len(ghosts)} ghosts. Summoning narrator ({a.model})...")
    stories = []
    for i, g in enumerate(ghosts, 1):
        print(f"  [{i}/{len(ghosts)}] {g['kind']}: {g['where']}")
        stories.append(narrate(g, a.model))
    render(Path(a.repo).resolve().name, ghosts, stories, a.out)
    print(f"Done. Open {a.out}")

if __name__ == "__main__":
    main()
