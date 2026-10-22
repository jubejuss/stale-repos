"""Generate data.json: owner's repositories without own (non-Dependabot) commits for over a year."""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
STALE_DAYS = 365
BOT_MESSAGE = re.compile(r"dependabot|^Bump |build\(deps", re.IGNORECASE)

token = os.environ.get("GH_TOKEN")
if not token:
    sys.exit("GH_TOKEN is not set")


def get(path):
    request = urllib.request.Request(API + path, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request) as response:
        return json.load(response), response.headers.get("Link", "")


def get_all(path):
    items = []
    while path:
        page, link = get(path)
        items.extend(page)
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        path = match.group(1).replace(API, "") if match else None
    return items


def last_own_commit(full_name):
    try:
        commits, _ = get(f"/repos/{full_name}/commits?per_page=100")
    except urllib.error.HTTPError as error:
        if error.code == 409:  # empty repository
            return None
        raise
    for commit in commits:
        login = (commit.get("author") or {}).get("login") or ""
        message = commit["commit"]["message"]
        if login.endswith("[bot]") or BOT_MESSAGE.search(message):
            continue
        return commit["commit"]["author"]["date"][:10], message.split("\n")[0][:70]
    return None


today = datetime.date.today()
cutoff = (today - datetime.timedelta(days=STALE_DAYS)).isoformat()
owner = get("/user")[0]["login"]
repos = []

for repo in get_all("/user/repos?affiliation=owner&per_page=100"):
    if repo["archived"] or repo["fork"]:
        continue
    last = last_own_commit(repo["full_name"])
    date, message = last if last else ("", "(tühi repo või ainult botide commit'id)")
    if date and date >= cutoff:
        continue
    repos.append({
        "name": repo["name"],
        "lastCommit": date,
        "message": message,
        "visibility": "private" if repo["private"] else "public",
        "language": repo["language"] or "",
        "created": repo["created_at"][:10],
        "description": (repo["description"] or "").replace("\n", " "),
    })

repos.sort(key=lambda r: (r["lastCommit"], r["name"]))
with open("data.json", "w", encoding="utf-8") as file:
    json.dump({"owner": owner, "generated": today.isoformat(), "repos": repos}, file, ensure_ascii=False, indent=1)
print(f"{len(repos)} stale repositories written to data.json")
