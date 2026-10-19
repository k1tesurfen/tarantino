# Operating tarantino

How to run, check, back up and troubleshoot tarantino on the mini-PC. Installation is in the [README](../README.md#installation-mini-pc-debian-13).

## Where things live

| What | Where |
|---|---|
| Checkout and virtualenv | `/opt/tarantino`, `/opt/tarantino/.venv` (owned by the deploy user) |
| Data: database, signing key, Android TV remote pairing, backups | `/var/lib/tarantino` (owned by the `tarantino` service user) |
| Bluetooth remote pairing | BlueZ, `/var/lib/bluetooth` (root) |
| Secrets | `/etc/tarantino/tarantino.env` (see [`deploy/env.example`](../deploy/env.example)) |
| Services | `tarantino.service` (web app on `127.0.0.1:8000`, behind the host's reverse proxy on port 80), `tarantino-mdns.service` (`tarantino.local` alias), `tarantino-btremote.service` (Bluetooth remote for the projector) |

Everything else (rooms, cassettes, device addresses, theme names) is configured in the admin website and stored in the database.

## Day to day

```sh
/opt/tarantino/deploy/update.sh                    # backup, git pull, build, restart, health check
sudo systemctl status tarantino.service
sudo systemctl restart tarantino.service
```

The CLI talks to the running server. The deploy user can run admin commands without a password, because it is in the `tarantino` group and can read the signing key:

```sh
tarantino health
tarantino cassettes                               # rooms and their cassettes
tarantino learn 3                                 # arm learn mode, then insert the real cassette
tarantino learn 3 --uid FAKE0003                  # bind a made-up UID (testing without the recorder)
tarantino play 3                                  # insert room 3's cassette via the real VHS endpoint
tarantino learn franchise                         # learn the franchise cassette (also with --uid)
tarantino play franchise                          # insert the franchise cassette
tarantino vhs insert 04A1B2C3                     # insert any UID, exactly as the recorder would
tarantino vhs eject
tarantino backup
tarantino config export my.tarantino.json
tarantino config import my.tarantino.json
```

`tarantino` is `/opt/tarantino/.venv/bin/tarantino`. Add the directory to your `PATH` or create a symlink. From another machine, pass `--url http://tarantino.local --password …`.

## Logs

tarantino logs to the systemd journal, with a syslog priority on every line:

```sh
sudo journalctl -u tarantino.service -f            # follow
sudo journalctl -u tarantino.service -b            # since the last boot
sudo journalctl -u tarantino.service -p warning    # warnings and errors only
```

Set `TARANTINO_LOG_LEVEL=DEBUG` in the env file and restart the service for more detail.

The Bluetooth remote logs to its own unit: `sudo journalctl -u tarantino-btremote.service -f`.

Each show also keeps a step log (resolve → projector → session → play). It's on the admin dashboard, and every cassette insert is in the recorder log on the admin cassettes page.

## The VHS recorder API

There is no login, so it only works on the LAN.

| Request | Effect |
|---|---|
| `POST /api/vhs/insert {"uid": "04A1B2C3"}` | Starts what the cassette's room offers today (during a franchise marathon: the next part). The franchise cassette starts the next part of the franchise started most recently today. In learn mode it binds the cassette instead and nothing plays. Unknown cassettes are logged and ignored. |
| `POST /api/vhs/eject {"uid": "04A1B2C3"}` | Only logged. The film keeps playing. `uid` is optional. |

UIDs are normalised: case, spaces, `:` and `-` don't matter. The response is the logged event, and its `outcome` is `played`, `learned`, `unknown` or `ignored`. If the room can't play (closed today, Jellyfin not configured), the response is `409` with a `detail` message. The reader fires several times per cassette (on insert and on eject), so reads of the cassette that started the latest cassette show are ignored until a different learned cassette is read or the cinema day rolls over. To play the same room twice in a row, use the website.

## Franchises

Movies of a TMDb collection (two or more distinct films in the library) are a franchise and play in order: only the next part can be programmed, in any room whose filters accept it. tarantino keeps its own progress per franchise (admin → *Franchises*), independent of Jellyfin's watched state:

- Starting a part (website or cassette) moves the franchise on. That room then offers **Next: part N+1** for the rest of the cinema day instead of selling out, so a marathon alternates room cassette → franchise cassette → room cassette …
- On later days, each franchise you are in the middle of continues at the daily chance from *Settings* (default 70 %), in a random free auditorium that accepts it.
- Starting the last part finishes the franchise; it rests for 60 days. A franchise with no new part for 180 days starts over at part 1.
- On the *Franchises* page you can rename a franchise, reorder or exclude parts (e.g. a spin-off), switch the order off ("any order"), start over, or pick the next part.

## What happens when…

| Situation | Behaviour |
|---|---|
| **The mini-PC reboots** | tarantino starts with the system. Today's programme, sold-out badges, sticky series and cassettes are in the database, and a missing day is generated on first use. A show that was starting during the restart is marked *failed: interrupted by a restart*. Learn mode is cancelled. |
| **Jellyfin is down or restarting** | The website keeps working from the library cache, with posters already in the browser cache. The library sync retries after 1, 2, 4 and 8 minutes, then every 15 minutes. Starting a film fails with *Jellyfin unreachable*. The admin dashboard shows the Jellyfin card in red. |
| **The projector is off or in standby** | Starting a show wakes it via the Bluetooth remote and opens Jellyfin with the shortcut key. Without a paired Bluetooth remote, or if the projector doesn't answer it, the show wakes it via Cast instead. If it isn't reachable at all (no power), the show fails at the *projector* step with a clear message. |
| **The Bluetooth remote restarts while the projector is on** | The projector shows the remote as disconnected and only reconnects on its next wake. Until then, shows use Cast and the Android TV remote. `update.sh` therefore restarts the Bluetooth remote only when its code changed. |
| **The NAS is down** | The media card shows the mounts as unavailable. Mounts are checked with a timeout, so a hanging NFS server never blocks tarantino. Jellyfin can't play the files. |
| **tarantino itself restarts** | Open cinema pages show a small "reconnecting" note, then reload the programme and pick up a show's result automatically. The admin pages retry every few seconds. |

## Backups

A config export (settings, rooms, cassettes and, by default, sticky series and programme history) is written:

- nightly at 03:30,
- before every `update.sh`,
- before every import.

The last 14 of each kind are kept in `/var/lib/tarantino/backups`. You can restore one from the admin *Backups* page, which shows you what would change first, or with `tarantino config import`. Exports never contain secrets, but they do contain addresses and cassette UIDs, so keep them out of the repository (`*.tarantino.json` is gitignored).

To move to a new machine: install, then import the latest backup. Library titles are matched by their TMDB/IMDb/TVDB IDs if Jellyfin has given them new IDs.

## Bluetooth remote

One-time setup:

1. On the projector: *Settings → Remotes & Accessories → set up remote buttons → shortcut (star) button* → Jellyfin.
2. Admin dashboard → Projector card → *Bluetooth remote* → **Pair**. On the projector: *Remotes & Accessories*, forget an old "Tarantino Remote", then *Add accessory* → "Tarantino Remote".
3. Test with *Shortcut key* (opens Jellyfin) and *Power* → wait about 30 s → *Wake*.

If a pairing hangs on the projector, restart the projector (button on the chassis) and pair again.

## Troubleshooting

| Symptom | Check |
|---|---|
| `tarantino.local` doesn't resolve | `sudo systemctl status tarantino-mdns.service`. Try the mini-PC's IP address. |
| Port 80 doesn't answer, but `curl http://localhost:8000/api/health` works on the mini-PC | The reverse proxy is down. tarantino only listens locally and relies on it. |
| Admin shows "Jellyfin: error" | Is Jellyfin running? Are the API key and user right in the env file? |
| Projector card says *unpaired* | Admin dashboard → pair the projector, then enter the code shown on screen. |
| Bluetooth remote: *service not running* | `sudo systemctl status tarantino-btremote.service`; after the first update with it, run `sudo deploy/install.sh` once. |
| Show step says *Bluetooth failed (… did not connect …)* | The remote was restarted while the projector was on, or the projector lost its pairing. Check *Remotes & Accessories* on the projector; pair again if "Tarantino Remote" is missing. |
| A show fails at *session* | Pick the projector's device on the admin dashboard. Open the Jellyfin app on the projector once by hand. |
| A show fails at *projector* after "Play Store" | The Jellyfin app has an update pending. Update it on the projector. |
| A cassette does nothing | Admin → *Cassettes* → recorder log. *unknown* means it was never learned, so bind it there. |
| Everything is broken after an update | `sudo journalctl -u tarantino.service -n 100`. Restore the `pre-update` backup if the configuration is damaged. |
