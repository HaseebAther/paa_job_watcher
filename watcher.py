#!/usr/bin/env python3
"""PAA job watcher: logs in, reads every (notice no, job title) on the Profile
page, and notifies (Telegram + desktop) when a new one shows up.

Usage:
  python watcher.py            # run forever
  python watcher.py --once     # single check, then exit
  python watcher.py --inspect  # dump the Profile page HTML to debug_profile.html

Two sources are watched: the logged-in Profile page, and the public
https://paa.gov.pk/media/job-opportunities page (read via the site's content API).
"""
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://apps.paa.gov.pk:2016/"
LOGIN_URL = urljoin(BASE, "default.aspx")
PROFILE_URL = urljoin(BASE, "Applicant/Profile.aspx")

# Public site: a React app whose /media/job-opportunities route is client-side only,
# so we read the same content API the page itself uses.
PUBLIC_PAGE_URL = "https://paa.gov.pk/media/job-opportunities"
PUBLIC_API = "https://paawebadmin.paa.gov.pk/api/v1/Content/GetContentById"
PUBLIC_PAGE_ID = "4953bdd9-4e95-41f9-95c3-88de4f076cc4"  # Umbraco node "Job Opportunities"
PUBLIC_API_KEY = "123456789_API"  # public key embedded in the site's own JS bundle
PUBLIC_MEDIA = "https://paawebadmin.paa.gov.pk"

HERE = Path(__file__).resolve().parent
COOKIE_FILE = HERE / "cookies.json"
SEEN_FILE = HERE / "seen.json"
PUBLIC_SEEN_FILE = HERE / "seen_public.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def load_env():
    env = dict(os.environ)
    f = HERE / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = load_env()
POLL = int(ENV.get("POLL_SECONDS", "60"))


# ---------- notifications ----------
def notify(title, body):
    print(f"[NOTIFY] {title}\n{body}\n", flush=True)
    token, chat = ENV.get("TELEGRAM_BOT_TOKEN"), ENV.get("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat, "text": f"{title}\n\n{body}", "disable_web_page_preview": "true"},
                timeout=15,
            )
        except requests.RequestException as e:
            print("telegram failed:", e, flush=True)
    hook = ENV.get("DISCORD_WEBHOOK_URL")
    if hook:
        try:
            requests.post(hook, json={"content": f"@everyone **{title}**\n{body}"[:1900]}, timeout=15)
        except requests.RequestException as e:
            print("discord failed:", e, flush=True)
    try:
        subprocess.run(["notify-send", "-u", "critical", title, body], timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


# ---------- session ----------
def new_session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    if COOKIE_FILE.exists():
        try:
            s.cookies.update(json.loads(COOKIE_FILE.read_text()))
        except (ValueError, OSError):
            pass
    return s


def save_cookies(s):
    COOKIE_FILE.write_text(json.dumps(s.cookies.get_dict()))
    COOKIE_FILE.chmod(0o600)


def form_fields(form):
    """Collect what a browser would submit for this ASP.NET form."""
    data = {}
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "select":
            opt = el.find("option", selected=True) or el.find("option")
            data[name] = opt.get("value", opt.text) if opt else ""
        elif el.name == "textarea":
            data[name] = el.text
        else:
            t = (el.get("type") or "text").lower()
            if t in ("submit", "button", "image", "file", "reset"):
                continue
            if t in ("checkbox", "radio") and not el.has_attr("checked"):
                continue
            data[name] = el.get("value", "")
    return data


def is_login_page(resp):
    return "TbxLoginId" in resp.text or resp.url.lower().endswith("default.aspx")


def login(s):
    email, pw = ENV.get("PAA_EMAIL"), ENV.get("PAA_PASSWORD")
    if not (email and pw):
        sys.exit("Set PAA_EMAIL and PAA_PASSWORD in .env")
    r = s.get(LOGIN_URL, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    data = form_fields(soup.find("form"))
    data.update({"TbxLoginId": email, "TbxPassword": pw, "BtnLogin": "Sign In"})
    r = s.post(LOGIN_URL, data=data, timeout=30)
    if "TbxLoginId" in r.text:
        err = BeautifulSoup(r.text, "html.parser").find(id="LoginError")
        sys.exit(f"Login failed: {err.get_text(strip=True) if err else 'check email/password'}")
    save_cookies(s)


def get_profile(s):
    r = s.get(PROFILE_URL, timeout=30)
    if is_login_page(r):
        login(s)
        r = s.get(PROFILE_URL, timeout=30)
        if is_login_page(r):
            sys.exit("Still on login page after logging in")
    return r


# ---------- scraping ----------
PLACEHOLDER = re.compile(r"^[\s\-]*(select\b.*|choose\b.*)?[\s\-]*$", re.I)


def real_options(sel):
    out = []
    for o in sel.find_all("option"):
        v, t = o.get("value", ""), o.get_text(" ", strip=True)
        if v.strip() in ("", "0", "-1") or PLACEHOLDER.match(t):
            continue
        out.append((v, t))
    return out


def find_selects(soup):
    sels = soup.find_all("select")
    notice = next((x for x in sels if re.search(r"notice|vacan", x.get("id", ""), re.I)), None)
    title = next((x for x in sels if re.search(r"title|job|post", x.get("id", ""), re.I) and x is not notice), None)
    if not notice and len(sels) >= 2:
        notice, title = sels[0], sels[1]
    return notice, title


def fetch_jobs(s):
    r = get_profile(s)
    soup = BeautifulSoup(r.text, "html.parser")
    notice_sel, title_sel = find_selects(soup)
    if not notice_sel or not title_sel:
        sys.exit("Could not find the two dropdowns. Run with --inspect and check debug_profile.html")

    notice_name = notice_sel["name"]
    current_notice = (notice_sel.find("option", selected=True) or notice_sel.find("option")).get("value")
    jobs = {}  # (notice, title) -> dict

    for nval, ntext in real_options(notice_sel):
        if nval == current_notice and real_options(title_sel):
            titles_soup = soup
        else:
            form = soup.find("form")
            data = form_fields(form)
            data[notice_name] = nval
            data["__EVENTTARGET"] = notice_name
            data["__EVENTARGUMENT"] = ""
            pr = s.post(PROFILE_URL, data=data, timeout=30)
            titles_soup = BeautifulSoup(pr.text, "html.parser")
        _, tsel = find_selects(titles_soup)
        if not tsel:
            continue
        for tval, ttext in real_options(tsel):
            jobs[(ntext, ttext)] = {"notice": ntext, "title": ttext}
    return list(jobs.values())


def fetch_public_jobs():
    """Every notice/opportunity listed on the public Job Opportunities page."""
    r = requests.get(
        PUBLIC_API,
        params={"Id": PUBLIC_PAGE_ID, "ApiKey": PUBLIC_API_KEY},
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json()["data"]["en"]["properties"]["jobItemList"]["items"]
    out = {}
    for it in items:
        c = it["content"]
        p = c["properties"]
        pdfs = [urljoin(PUBLIC_MEDIA, f["url"]) for f in (p.get("pDF") or []) if f.get("url")]
        out[c["id"]] = {
            "id": c["id"],
            "category": (p.get("category") or "").strip(),
            "title": (p.get("jobTitle") or "").strip(),
            "description": (p.get("jobDescription") or "").strip(),
            "published": (p.get("publishDate") or "")[:10],
            "pdf": pdfs[0] if pdfs else PUBLIC_PAGE_URL,
        }
    return out


def check_public():
    current = fetch_public_jobs()
    if not PUBLIC_SEEN_FILE.exists():
        # first run: just record what's already there, don't alert on 200+ old items
        PUBLIC_SEEN_FILE.write_text(json.dumps(sorted(current)))
        notify(
            f"PAA public page watcher started ({len(current)} items currently listed)",
            f"Watching {PUBLIC_PAGE_URL}",
        )
        return
    seen = set(json.loads(PUBLIC_SEEN_FILE.read_text()))
    new = [j for i, j in current.items() if i not in seen]
    for j in new:
        label = "NEW PAA JOB AD" if j["category"] == "Opportunity" else "NEW PAA NOTICE"
        notify(
            label,
            f"{j['title']}\n{j['description']}\nPublished: {j['published']}\n\n{j['pdf']}\nPage: {PUBLIC_PAGE_URL}",
        )
    PUBLIC_SEEN_FILE.write_text(json.dumps(sorted(seen | set(current))))
    print(f"{time.strftime('%H:%M:%S')} public page checked: {len(current)} listed, {len(new)} new", flush=True)


def key(j):
    return f"{j['notice']} | {j['title']}"


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return None


STARTED = {"pinged": False}


def check(s):
    jobs = fetch_jobs(s)
    seen = load_seen()
    current = {key(j): j for j in jobs}
    if seen is None:
        SEEN_FILE.write_text(json.dumps(sorted(current)))
        notify(
            f"PAA watcher started ({len(current)} jobs currently listed)",
            "\n".join(current) or "(none listed)",
        )
        STARTED["pinged"] = True
        return
    if not STARTED["pinged"]:
        STARTED["pinged"] = True
        notify("PAA watcher is running", f"Watching {len(current)} listed job(s). You'll be alerted when a new one appears.")
    new = [j for k, j in current.items() if k not in seen]
    for j in new:
        notify(
            "NEW PAA JOB",
            f"Notice: {j['notice']}\nTitle: {j['title']}\n\nApply: {PROFILE_URL}",
        )
    # keep everything ever seen so a job that disappears and returns isn't re-alerted
    SEEN_FILE.write_text(json.dumps(sorted(seen | set(current))))
    print(f"{time.strftime('%H:%M:%S')} checked: {len(current)} listed, {len(new)} new", flush=True)


def main():
    s = new_session()
    if "--inspect" in sys.argv:
        r = get_profile(s)
        (HERE / "debug_profile.html").write_text(r.text)
        print("wrote debug_profile.html")
        return
    if "--once" in sys.argv:
        check(s)
        check_public()
        return
    errors = 0
    while True:
        failed = None
        for fn in (lambda: check(s), check_public):
            try:
                fn()
            except SystemExit:
                raise
            except Exception as e:  # network blips etc.; one source failing must not stop the other
                failed = e
                print("error:", repr(e), flush=True)
        errors = errors + 1 if failed else 0
        if errors == 5:
            notify("PAA watcher is failing", repr(failed))
        time.sleep(POLL + random.uniform(0, POLL * 0.2))


if __name__ == "__main__":
    main()
