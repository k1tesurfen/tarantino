# Tarantino — Implementation Plan (V1)

Status: **draft, awaiting approval**

This plan records every decision from the planning Q&A, describes the V1 architecture, and splits V1 into milestones that can each be tested on the mini-PC.

---

## 0. Public repository rules

This repository is public. These rules apply to code, docs, commit messages, tests and fixtures:

- **Never commit** tokens, API keys, passwords, IP addresses, hostnames, usernames, email addresses or exported configuration files.
- **Commits come only from the user's own git identity.** No AI co-author trailers or "generated with" lines in commits or PRs.
- **Generic names only:** *mini-PC*, *NAS*, *projector*, *VHS recorder*, *Home Assistant*. Don't use hardware brands or models in code. `tarantino` is the tool's name and is public.
- **Where values live instead:**
  - Secrets go in `.env`, which is gitignored. Only `deploy/env.example` with placeholders is committed.
  - Device addresses (projector, Home Assistant URL, etc.) are **admin settings in the DB**, never in code.
- **Theme default names in code:** the modern theme is **"apLex"** and the retro theme is **"Red Apple Cinema"**. The user renames them in admin.
- **Test fixtures:** use fake data only, such as RFID UIDs like `FAKE0001` and `192.0.2.x`/`example.local` addresses (documentation ranges).
- **Guard rails, added in M0:**
  - A local, **gitignored** `CLAUDE.md` holding these rules plus the real environment values needed while implementing. It already exists.
  - A committed pre-commit hook (`scripts/check-public.sh`) that blocks:
    - private IPv4 ranges outside the documentation ranges
    - things that look like tokens or keys
    - any word from a **local, gitignored** denylist file (`.private-words`) holding real hostnames and usernames

---

## 1. Environment facts (verified 2026-10-10)

The specific addresses and names are kept out of the repo on purpose.

| Item | Value |
|---|---|
| Mini-PC | Debian 13 (trixie), Python 3.13, Docker installed, static IP. **Not installed yet:** Node, adb, avahi. Port 80 is free |
| Jellyfin | **12.1.0**, bare metal, on the mini-PC at `localhost:8096`. The OpenAPI spec confirms `/Sessions`, `/Sessions/{id}/Playing`, `/Shows/NextUp` and `/Shows/{id}/Episodes` exist |
| NAS | NFSv3 exports for movies and series, mounted on the mini-PC by systemd automount with `soft` mounts |
| Projector | Android TV with the Jellyfin **Android TV** app (`org.jellyfin.androidtv`) and its built-in player. Audio comes from the projector speakers. It stays on the network in standby. Network ADB can be enabled |
| Home Assistant | VM on the mini-PC. URL and token still to be supplied |

---

## 2. Decisions

### Playback
- **Players:** Tarantino controls the Jellyfin Android TV app through the Jellyfin Sessions API.
- **Projector control** (revised after testing in M2): in network standby the projector drops ADB and ping and only keeps Chromecast and the Android TV Remote service reachable. So:
  - **Chromecast** wakes the projector from standby, by launching the Default Media Receiver.
  - The **Android TV Remote protocol (v2)** reads power state and the current app and launches Jellyfin. It needs a one-time pairing from the admin page.
  - **ADB** is only a fallback, used when it happens to be available. Wireless debugging on this projector's firmware disables itself.
  - The Jellyfin Android TV app declares **no deep links**, and the remote protocol can only open links. Tarantino therefore opens Jellyfin's Play Store page and presses OK on its focused "Open" button, which takes about 5 s. A pending app update would break this, and the show then fails with a clear hint.
  - Verified on the real device: from standby to a playing film takes about 20 s. The projector's optics start later than Android, so the wake and launch steps are never visible.
- **Conflicts:** a new start request always replaces whatever is playing.
- **Movies:** always start from the beginning, even if partially watched.
- **Series:** play the next-up episode (resume it if it was partially watched) and queue the following episodes so they autoplay.
- **Jellyfin user:** only your own user counts. "Liked" means Jellyfin's ❤️ favourite flag.

### Programme
- **Rooms:** configurable. The default is **10 rooms for 10 cassettes**: rooms 1–6 show movies, rooms 7–10 show series.
- **Movie rooms:** each room is defined by **filter rules** plus a **weighted random** pick. The V1 presets are *Unwatched (any)*, *Unwatched Horror* and *Favourites (watched + ❤️)*. A generic filter editor lets you build any other theme.
- **Series rooms:** always 4. Shows are picked at random with no filters, from series that are **not fully watched**.
  - A series becomes **sticky** once it has been **started via Tarantino** from a series room. It then stays in **the same room/cassette** every day until finished. Series you half-watched elsewhere are just normal candidates.
  - A series counts as **finished** when it has no unplayed episodes left. If a new season is added later, the series becomes a candidate again.
  - If all 4 rooms hold sticky series, no new series appears. The admin site has a **drop series** button to free a room.
- **Schedule:**
  - One title per room per day. The showtimes are **fake** and only there for atmosphere.
  - The cinema day rolls over at **05:00** (configurable).
  - Only **today's** programme is shown.
- **Movie repeats:** a movie can't appear again within **30 days** (configurable) and is never shown in two rooms on the same day.
- **Sold out:** a movie room is marked **sold out** once it has been started via Tarantino that day. The badge is purely visual, so the film can still be played. Series rooms never sell out.
- **Watched during the day:** the programme stays fixed for the day. Watched state only affects the next day's generation.
- **Admin overrides:** re-roll a room, re-roll the whole day, or swap in a specific title.

### Cinema website
- **Language:** English.
- **Desktop-first** (about 80% of use), but still usable on a phone. It won't be used on the projector or a tablet.
- **Theme selector** with **full layouts per theme**. V1 ships two themes:
  - **Modern**, default name **"apLex"**: a multiplex look.
  - **Retro**, default name **"Red Apple Cinema"**: a Tarantino/grindhouse/VHS look.
  - Names are editable per theme in admin. Each visitor's choice is remembered in their browser, and admin sets the default.
- **Series section:** series rooms get their own section ("TV lounge" style), separate from the auditoriums.
- **Trailers:** YouTube embeds built from Jellyfin's `RemoteTrailers` (from TMDB).
- **Starting a film:** both a quick **Play** button and a playful **fake ticket flow** (seat picker → ticket stub → "Start show").
- **Access:** the cinema site is open on the LAN, and anyone on it can start films. The **admin site needs a password**.

### Cassettes / VHS API
- **Endpoint:** `POST /api/vhs/insert {"uid": "..."}`. UIDs that haven't been learned are **ignored** (logged and shown in admin). There is no API token.
- **Learning mode:** in admin you "arm" room N, and the next UID posted to the same endpoint is bound to room N. No playback is triggered.
- **Eject:** `POST /api/vhs/eject` is accepted and logged and does **nothing** else.
- **Test CLI:** a `tarantino` CLI simulates the recorder, e.g. `tarantino vhs insert <uid>`, `tarantino play 3` (sends room 3's learned UID through the real endpoint) and `tarantino learn 3 --uid FAKE0003`.

### Settings export / import (new)
- **Purpose:** a set-up system (rooms, filters, cassettes, theme names, settings) must survive DB resets, reinstalls and development mishaps.
- **Format: JSON.** It roundtrips exactly with the Python standard library, is validated with a pydantic schema, and downloads and uploads easily in the browser. It's also human-readable when pretty-printed.
- **Contents:** everything configurable in admin **except secrets** (secrets stay in `.env`):
  - Envelope: `schema_version`, `tarantino_version`, `exported_at`.
  - `settings`: rollover hour, cooldowns, theme names, default theme, projector address, Jellyfin device ID, Home Assistant URL, …
  - `rooms`: number, name, kind, filters, weights, order, active.
  - `cassettes`: UID → room number.
  - `state` (optional, included by default): sticky series assignments and programme history, so cooldowns and in-progress series survive.
- **Robust references:** every Jellyfin item is exported as `{id, name, year, provider_ids}`. On import, if an item ID no longer exists (for example after a Jellyfin rebuild), it is remapped via TMDB/IMDb ID or name and year.
- **Import:**
  1. Upload in admin, or use `tarantino config import <file>`.
  2. The file is validated, and the admin shows a **preview diff**.
  3. The import replaces the configuration in one transaction.
  4. Older `schema_version`s are migrated forward.
- **Export:** a download button in admin, or `tarantino config export [file]`.
- **Automatic safety net:**
  - `update.sh` writes an export before every update and migration.
  - A nightly export runs with rotation (keep 14), stored in the data directory on the mini-PC, outside the repo.
- **Completeness by construction:** all configuration goes through one settings schema. A test fails if a configuration table or setting isn't covered by the export, and a roundtrip test checks export → wipe → import → identical.
- **Safety:** exported files contain addresses and RFID UIDs, so `*.tarantino.json` and `backups/` are gitignored.

### Tech & operations
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy 2 / SQLite (with Alembic migrations), `httpx` for HTTP, APScheduler for jobs, Typer for the CLI. Dependencies are pinned in `pyproject.toml` and installed into a plain venv (`uv` isn't available on either machine, so it was dropped). I chose this stack because the integrations (Jellyfin, HA, ADB, USB) are easiest in Python.
- **Frontend:** a SvelteKit SPA (`adapter-static`) built into static files and served by FastAPI. Node is installed on the mini-PC for the build.
- **Deployment:**
  - Native **systemd** service, running as a dedicated `tarantino` user, on **port 80** via `CAP_NET_BIND_SERVICE`.
  - Checkout in `/opt/tarantino`, owned by the deploy user. Data in `/var/lib/tarantino`, secrets in `/etc/tarantino/tarantino.env`. A narrow sudo rule lets the deploy user restart the service, so updates need no password.
  - Reachable at **`http://tarantino.local`** through an Avahi alias. The mini-PC keeps its own hostname, and its IP is detected at runtime, not committed.
- **Config:**
  - **Secrets live in `.env`**, which is gitignored: Jellyfin API key, admin password, HA token.
  - **Everything else lives in the DB**, edited through the admin site and exportable.
- **Workflow:**
  1. Develop on the Mac.
  2. **Commit to `main`** and push to GitHub.
  3. `git pull` on the mini-PC over SSH and run `deploy/update.sh`.
  4. Test on the mini-PC.

---

## 3. Architecture (V1)

```
                 browser (desktop/phone)          ESP32 (later) / tarantino CLI
                        │  HTTP :80                        │  POST /api/vhs/*
                        ▼                                  ▼
┌──────────────────────── tarantino (FastAPI, systemd, mini-PC) ──────────────────────┐
│  static SPA  ── /            cinema (themes: modern, retro)                          │
│              ── /admin       admin (password)                                        │
│  API         ── /api/cinema  programme, titles, play, ticket                         │
│              ── /api/admin   rooms, cassettes, overrides, status, settings,          │
│                              config export/import                                    │
│              ── /api/vhs     insert / eject (learn mode)                             │
│              ── /api/events  SSE: show progress, now playing, programme changes      │
│              ── /api/img     Jellyfin image proxy (cached)                           │
│                                                                                      │
│  library sync ──► SQLite cache of movies & series (every 15 min + on demand)         │
│  programme engine ──► daily generation at rollover, overrides, series stickiness     │
│  show orchestrator ──► projector (ADB) → Jellyfin session → PlayNow                  │
│  status monitor ──► Jellyfin, session, projector, NFS, Home Assistant                │
│  backup job ──► nightly config export                                                │
└──────────┬───────────────────────────┬──────────────────────────┬────────────────────┘
           │ HTTP localhost:8096       │ adb tcp :5555            │ HTTP (status only in V1)
           ▼                           ▼                          ▼
      Jellyfin                     Projector                 Home Assistant VM
```

### Repository layout
```
CLAUDE.md                  (gitignored) public-repo rules + private environment values
backend/
  pyproject.toml, alembic/
  tarantino/
    main.py            FastAPI app, static mount, lifespan (scheduler, sync)
    config.py          .env settings (pydantic-settings)
    db.py, models.py   SQLAlchemy models
    jellyfin/          API client, library sync, image proxy
    projector/         ADB wrapper (connect, wake, launch, foreground, screen state)
    programme/         filters, weighting, generator, series stickiness, showtimes
    shows/             orchestrator (state machine + step log), SSE broadcaster
    status/            subsystem health checks
    configio/          export/import schema, versioned migrations, item remapping
    api/               cinema.py, admin.py, vhs.py, events.py, auth.py
    cli.py             `tarantino` CLI (Typer)
  tests/
frontend/
  src/routes/(cinema)/…      theme-aware cinema pages
  src/routes/admin/…         admin pages
  src/lib/themes/modern/…    full layout + components (default name "apLex")
  src/lib/themes/retro/…     full layout + components (default name "Red Apple Cinema")
  src/lib/api/…              typed API client, SSE store
deploy/
  install.sh  build.sh  update.sh  mdns-alias.sh  tarantino.service  tarantino-mdns.service  env.example
scripts/
  check-public.sh            pre-commit guard (see §0)
  check-commit-msg.sh        commit-msg guard: no AI attribution, no private words
  setup-dev.sh               enables .githooks/ for a checkout
.githooks/                   pre-commit, commit-msg
```

### Data model (SQLite)
- `setting` — key/value store: rollover hour, cooldowns, theme names, default theme, projector address, Jellyfin device ID, HA URL, …
- `library_item` — cached Jellyfin movies and series, including:
  - identity and descriptive fields: id, type, name, year, provider IDs, genres, overview, runtime, ratings, trailer URLs, image tags, date added
  - watch state: `played`, `favorite`, `unplayed_count` (series)
- `room` — number, name, kind (`movie` | `series`), filter JSON, weight JSON, sort order, active flag
- `cassette` — RFID UID (normalised as uppercase hex) → room
- `programme_entry` — cinema date, room, item, fake showtimes, `first_started_at` (used for "sold out"), source (`generated` | `override`)
- `series_assignment` — room, series, started/finished/dropped timestamps (stickiness)
- `show` — one play attempt: trigger (web/vhs/admin), room, item, state, step log, error, timestamps
- `vhs_event` — raw insert/eject log, including unknown UIDs

**Configuration** (exported): `setting`, `room`, `cassette`. **State** (exported optionally): `series_assignment`, `programme_entry` history. **Cache and logs** (not exported, rebuildable): `library_item`, `show`, `vhs_event`.

---

## 4. Key mechanics

### Library sync
- Paginated `GET /Items` for `Movie` and `Series` with the user's `UserData` (played, favourite, unplayed count, resume position) and the fields Tarantino needs. This handles a library of over 2,000 items.
- Runs at startup, every 15 minutes, before each programme generation, and when triggered manually from admin.
- The Jellyfin API key and username come from `.env`.

### Programme generation
1. Work out the cinema date: `(now − rollover_hour)`.
2. Generate the day at the rollover via the scheduler, or lazily if that date is missing (for example after downtime).
3. **Movie room:**
   - Start from movies matching the room's filters (genres include/exclude, played, favourite, year range, community/critic rating min, runtime range, tags).
   - Remove movies used in another room today or shown within the cooldown.
   - Pick by weighted random. The configurable boosts are rating, recently added and never shown before.
   - If the pool is empty, ignore the cooldown. If it's still empty, the room is "closed today".
4. **Series room:** keep an active sticky assignment if the series still has unplayed episodes. Otherwise close the assignment as finished and pick a random candidate: not fully watched, not sticky elsewhere, not shown in another series room today.
5. **Fake showtimes:** derived deterministically from date, room and runtime, e.g. 3 slots between 14:00 and 23:30 on 15-minute steps.

### Show orchestrator
This is a cancellable state machine, and a new show cancels the running one.
1. **resolve** — room → today's entry → Jellyfin item(s).
2. **projector** — run `adb connect`. If the screen is off, send `KEYCODE_WAKEUP`. If Jellyfin isn't the foreground app, launch `org.jellyfin.androidtv`.
3. **session** — poll `/Sessions` until the projector's session appears and accepts remote control, with a timeout of about 30 s. The device is identified by a Device ID chosen in admin.
4. **play**:
   - Movie: `POST /Sessions/{id}/Playing?playCommand=PlayNow&itemIds=…&startPositionTicks=0`.
   - Series: `NextUp` → episode list starting from that episode (capped at about 25) → `PlayNow` with the resume position of the first episode.
5. **confirm** — poll the session's `NowPlayingItem`. On success, mark the movie entry sold out and, for a series room, create the sticky assignment.
- Every step is logged to the `show` record and streamed over SSE. The cinema site shows a "show is starting…" overlay, and the admin site shows the full step log.

### Status monitor
Runs every 30 s, plus on demand from the admin dashboard. It checks:
- **Jellyfin:** reachable, version, item counts.
- **Projector session:** present, last activity, now playing.
- **Projector:** ping, ADB connected/authorised, screen on/off, foreground app.
- **NFS:** each mount is triggered and listed **inside a thread with a timeout**, because NFS can hang.
- **Home Assistant:** `GET /api/` with the token.

---

## 5. Milestones

Each milestone ends with a test on the mini-PC and a commit to `main`.

| # | Milestone | Done when |
|---|---|---|
| **M0** ✅ | **Skeleton, guard rails & deploy pipeline**: the `check-public.sh` pre-commit hook, backend/frontend scaffolds, `env.example`, `install.sh` (apt deps: `adb`, `avahi-utils`, `nodejs`/`npm`; `tarantino` user; venv; frontend build; systemd units; sudo rule), `build.sh`, `update.sh`, Avahi alias, `/api/health` | `http://tarantino.local` serves a placeholder page after a fresh install. The hook rejects a test commit containing a private IP |
| **M1** ✅ | **Jellyfin integration**: client, user resolution, library sync into SQLite, image proxy, admin status card | Admin shows Jellyfin 12.1.0, the movie/series counts match Jellyfin, and posters load through the proxy |
| **M2** ✅ | **Projector control & playback**: ADB wrapper, session discovery and device pick in admin, orchestrator, SSE, an admin "test play" button | From admin, a sleeping projector wakes, opens Jellyfin and plays a chosen movie from 0:00. A series episode queue autoplays. A new show replaces a running one |
| **M3** ✅ | **Programme engine**: rooms with filters and weights, presets, daily generation, cooldown, series stickiness, drop series, re-roll/swap, fake showtimes, unit tests on generation rules | 6 movie rooms and 4 series rooms are generated correctly. Tests cover cooldown, no duplicates, stickiness, finished/new-season handling and fallbacks |
| **M4** ✅ | **Admin website + config export/import**: login, dashboard (all status cards, now playing, recent shows), programme page (overrides), rooms editor with filter builder and live pool size, cassettes with learn mode and unknown-UID log, settings (theme names/default, rollover, cooldowns, projector address), **export/import with preview diff, CLI export/import, auto-export in `update.sh` and nightly** | Everything configurable without touching the DB. Export → wipe DB → import restores an identical setup, verified by the roundtrip test and once by hand on the mini-PC |
| **M5** ✅ | **Cinema website — Modern "apLex"**: today's programme, film detail with trailer, series lounge section, quick play and the ticket flow, sold-out badges, now-playing banner, show progress overlay, theme toggle | You can pick and start a film from a desktop browser. Layout works on a phone |
| **M6** ✅ | **Cinema website — Retro "Red Apple Cinema"**: full alternative layout for all cinema pages | You can switch themes and the choice is remembered |
| **M7** | **VHS API & CLI**: insert/eject endpoints, learn mode, `tarantino` CLI | `tarantino learn 3 --uid FAKE0003` followed by `tarantino play 3` starts room 3's film on the projector |
| **M8** | **Hardening**: logging (journald), error states in the UI, restart resilience (lazy generation, resumable state), README/ops docs | Survives a reboot of the mini-PC, Jellyfin restarts and the projector being off, with clear status shown |

Export/import lands in M4, together with the admin pages. Cassette management (learn mode, unknown-UID log) moved from M4 to M7, next to the cassette API. From then on, every configuration you build is backed up before every update.

---

## 6. Setup you'll need to do

These are needed before or during the milestones. Nothing from this list goes into the repo:
1. **M0:** create a local `.private-words` file listing real hostnames and usernames. The pre-commit guard uses it.
2. **M0:** `sudo` on the mini-PC for the first `install.sh` run (apt, systemd, user creation).
3. **M1:** create a Jellyfin API key (Dashboard → API Keys). Put it and your Jellyfin username into `/etc/tarantino/.env` on the mini-PC.
4. **M2:** a DHCP reservation for the projector. Its address is entered in admin settings. Enable *Developer options → Network/ADB debugging* on the projector.
5. **M2:** accept the ADB authorisation prompt on the projector at the first connect.
6. **M4:** choose an admin password (`.env`). Give the Home Assistant URL (admin setting) and a long-lived access token (`.env`).

---

## 7. Risks and things to verify early (M2)

- **Android TV app and remote PlayNow on Jellyfin 12.1:** check that it obeys `startPositionTicks=0` for movies with a resume point. Fallback: reset the item's playback position via the UserData API before sending PlayNow.
- **Remote control on the app's start screens:** check whether the app accepts commands while on its home or login screens. It may need a short delay after launch.
- **Waking the projector:** the projector may ignore `KEYCODE_WAKEUP`. Fallbacks are `KEYCODE_POWER` (toggle, so check screen state first) or HDMI-CEC/HA in V2.
- **ADB stability:** some Android TV builds drop network ADB after a reboot. The status monitor will make this visible.
- **Series queue length:** `itemIds` in the query string, capped at about 25 episodes.
- **NFS checks:** automount plus `soft` mounts mean checks must never block the event loop.
- **Jellyfin item IDs:** they may change after a library rebuild. The export stores provider IDs so items can be remapped.

---

## 8. Out of scope for V1 → roadmap

| Slice | Scope |
|---|---|
| **V2: The Show** | Cast splash screen: show a cinema splash image or intro clip on the projector via the Cast Default Media Receiver. The optics start after Android is ready, so the splash needs a deliberate hold time to be seen. Motorized screen via USB port power. Needs per-port power switching (`uhubctl`) or a switchable hub, to be researched once the screen exists. Lights and AVR via Home Assistant. Projector power-off and lights up at the end of a film. Pre-show (trailers before the feature). ESP32 firmware for the VHS recorder |
| **V3: Home Assistant plugin** | Tarantino entities and services in HA |
| **Later** | More cinema themes, more room presets (decades, director retrospectives, double features, sneak preview), stats/history page, remote access |
