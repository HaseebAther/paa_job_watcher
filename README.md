<!--
title: PAA Jobs Watcher for Telegram and Discord
meta_title: PAA Jobs Alerts for Pakistani Job Applicants
slug: paa-jobs-notice-polling
description: Our bot checks two PAA listing pages every minute and pings your phone the moment a new notice appears.
chosen_keyword: paa jobs
secondary_keywords: []
schema_type: SoftwareApplication
-->

# PAA Jobs Watcher

> A small Python bot that watches the Pakistan Airports Authority's hiring pages and messages you the moment something new is posted.

PAA Jobs Watcher checks the two places where the Pakistan Airports Authority (PAA) publishes hiring news: the logged-in applicant profile and the public [Job Opportunities page](https://paa.gov.pk/media/job-opportunities). About once a minute it compares what is listed against what it has already seen. When a new notice, job ad or vacancy title appears, it sends a message to Telegram, Discord and your desktop. You run it yourself, on your own computer, with your own PAA login. It is an independent tool and is not made or endorsed by the PAA.

## Why checking by hand fails

Hiring notices from a government body rarely arrive by email. They appear on a web page, sometimes with a short window to apply, and the only way to catch one is to keep opening the page. People refresh it between meetings, forget for a few days, then find a closing date that has already passed.

The applicant profile is harder still. Vacancies there sit inside two linked drop-down menus, a notice number and a job title, and the second menu only fills in after you pick a notice from the first. A new title can appear inside an old notice with no visible sign. Looking at the page once tells you nothing about what changed since yesterday.

The watcher removes that chore. It does the clicking and the comparing, remembers every listing it has ever shown you, and speaks up only when something is new.

## What it watches

### The logged-in applicant profile

The watcher signs in with your PAA email and password, opens the Profile page and reads every notice in the first drop-down. For each notice it submits the page's form the way a browser would, so the job-title menu fills in, then records each pair of notice number and job title. That is how it catches a new title under a notice you already knew about.

After the first sign-in it saves your session cookie (a small token the site gives your browser so it knows you are still logged in) in a local file that only your user can read. It signs in again only when the site stops accepting that cookie.

### The public Job Opportunities page

The public page is a React app, meaning it builds itself inside your browser, so a plain download of the page contains no listings. The watcher asks the same content API (the data feed the page itself reads from) for the list instead. Each entry has a category, title, description, publish date and usually a PDF.

Entries in the Opportunity category are labeled as job ads, and everything else is labeled as a notice. The PDF link goes straight into the alert. At the time of writing the page listed more than 200 items, which is why the first run behaves the way it does.

## Core Features

| Feature | What it does |
|---|---|
| Two sources in one cycle | Watching two sites by hand means two bookmarks and twice the forgetting. Every cycle reads the applicant profile and the public page, and if one fails the other still runs. |
| New titles under old notices | A refresh shows the same notice number, so a new vacancy hides inside it. The watcher stores each notice and title pair and alerts on any pair it has not seen. |
| A quiet first run | Getting 200 alerts on day one makes the tool useless. The first run saves everything already listed as a baseline and sends one "started" message per source instead. |
| One alert per listing | A listing that disappears and comes back would normally ring twice. Everything ever seen stays in `seen.json` and `seen_public.json`, so each listing alerts once. |
| Alerts where you already look | Not everyone lives in one app. Telegram, a Discord webhook and a desktop popup are all supported, and you can switch each on or off by filling in or clearing its setting. |
| The details inside the alert | Opening the site just to read a title wastes the first minute. Public alerts carry the title, description, publish date and PDF link, and profile alerts carry the notice, the title and a link to apply. |
| Gentle timing | Hitting a government server exactly every 60 seconds looks like a clock, not a person. The wait is 60 seconds plus a random extra of up to 20 percent, and `POLL_SECONDS` changes the base. |
| A warning when it breaks | Silence could mean nothing is new, or that the tool has stopped working. After five failed rounds in a row it sends a "PAA watcher is failing" alert with the error. |
| Two debug switches | Page layouts change. `--once` runs a single check and exits, and `--inspect` saves the profile page to `debug_profile.html` so you can see what the watcher sees. |

## How a new listing becomes an alert

Each round follows the same five steps for both sources:

1. Fetch the current list from the page or the content API.
2. Give every listing a key: the notice and title text for the profile, the entry's own ID for the public page.
3. Compare those keys with the ones saved from earlier rounds.
4. Send one alert for each key that is not in the saved set.
5. Save the old keys together with the new ones, so nothing is ever forgotten.

This design has one limit worth knowing. If the authority edits the wording of a notice or title, the new wording looks like a new listing and you will get one extra alert. That is a cheap price for never missing a real one.

## Where the alerts arrive

**Telegram** is the best choice for a phone. You create a bot with [BotFather](https://core.telegram.org/bots/features#botfather), message it once, and put its token and your chat ID in the settings file. The watcher then calls the [Telegram Bot API](https://core.telegram.org/bots/api) to send each alert.

**Discord** works through a [webhook](https://discord.com/developers/docs/resources/webhook), which is a private URL that posts into one channel. Every alert starts with `@everyone`, so use a channel that only you or your group can see.

**The desktop popup** uses `notify-send`, the standard notification command on Linux, at critical urgency. If your system does not have it, the watcher skips the popup and keeps going. Every alert is also printed in the terminal.

A public-page alert looks like this:

```text
NEW PAA JOB AD
<title>
<description>
Published: 2026-01-15

<link to the PDF>
Page: https://paa.gov.pk/media/job-opportunities
```

## Who it helps

- **An applicant waiting on one department.** The new vacancy title reaches your phone within about a minute of being added, instead of whenever you next remember to look.
- **Someone gathering documents early.** Public alerts include the PDF link, so you can read the requirements and closing date the same hour the notice goes up.
- **A study group or family sharing one lookout.** Point the Discord webhook at a shared channel and everyone sees the same alert once, with no one checking separately.
- **A person who is rarely at a desk.** Run it on a spare computer that stays on, and let Telegram carry the alert to wherever you are.

## How to Get New Listing Alerts Using PAA Jobs Watcher

**STEP 1 — Download & Set Up the Project**

Download, set up, and install [**PAA Jobs Watcher**](https://github.com/HaseebAther/paa_job_watcher) to get the project running. If you hit any difficulty, [open an issue here](https://github.com/HaseebAther/paa_job_watcher/issues).

**STEP 2 — Add Your Details**

Copy `.env.example` to `.env`. Fill in `PAA_EMAIL` and `PAA_PASSWORD`, then add the Telegram token and chat ID or the Discord webhook URL for phone alerts.

**STEP 3 — Run One Test Check**

Run `python watcher.py --once`. It signs in, reads both pages, saves today's listings as the baseline and sends one "started" message per source.

**STEP 4 — Leave It Running**

Run `python watcher.py`. It repeats every `POLL_SECONDS` (60 by default) and sends the notice details to your chosen channels whenever something new appears.

```bash
pip install requests beautifulsoup4
cp .env.example .env
python watcher.py --once
python watcher.py
```

## What is in the project

```text
paa_job_watcher/
├── watcher.py          # the whole bot, one file
├── .env.example        # settings template
├── .env                # your settings (kept out of git)
├── .gitignore          # keeps secrets and saved state out of git
├── cookies.json        # saved session, created on first sign-in
├── seen.json           # profile listings already alerted
├── seen_public.json    # public listings already alerted
└── debug_profile.html  # only appears after --inspect
```

## Why it is built this way

The bot is one Python file of about 320 lines, so you can read all of it in a sitting and see exactly where your password goes. [Requests](https://requests.readthedocs.io/) holds the session and cookies, which is what keeps you signed in between rounds. [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) reads the profile page and collects every form field a browser would send, which the site's drop-down menus require. Memory lives in plain [JSON](https://docs.python.org/3/library/json.html) files, because a few hundred short text keys do not need a database.

## Things to know before relying on it

- **It needs a valid PAA login.** If sign-in fails, it stops and prints the site's own error message.
- **A redesign can break the profile reader.** It finds the two drop-downs by their IDs. If it cannot, it stops and tells you to run `--inspect`.
- **The public feed uses an access key** that the site's own page hands to every visitor. If PAA changes it, that source will fail and the failure alert will tell you.
- **It only checks while it is running.** A closed laptop is a paused watcher.
- **Your password stays on your machine.** It goes to the PAA sign-in form and nowhere else. Telegram and Discord receive only the alert text.

## FAQ

### Does the watcher apply for vacancies on my behalf?

No. It only reads the listings and tells you about new ones. Applying stays in your hands, and every profile alert includes the link to the page where you do it.

### Will I get hundreds of alerts the first time I run it?

No. The first run saves everything already listed as a baseline and sends a single "started" message for each source. Alerts begin only for listings added after that.

### Does it need to stay on all the time?

It only checks while it is running. If you switch it off for a day, the next run compares against what it saved and alerts you to everything posted while it was off, so a gap delays the alert but does not lose it. A spare computer that stays on gives the fastest alerts.
