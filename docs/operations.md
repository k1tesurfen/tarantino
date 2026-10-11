# Operating tarantino

How to run, check, back up and troubleshoot tarantino on the mini-PC. Installation is in the [README](../README.md#installation-mini-pc-debian-13).

## Where things live

| What | Where |
|---|---|
| Checkout and virtualenv | `/opt/tarantino`, `/opt/tarantino/.venv` (owned by the deploy user) |
| Data: database, signing key, Android TV remote pairing, backups | `/var/lib/tarantino` (owned by the `tarantino` service user) |
| Secrets | `/etc/tarantino/tarantino.env` (see [`deploy/env.example`](../deploy/env.example)) |
| Services | `tarantino.service` (web app on port 80), `tarantino-mdns.service` (`tarantino.local` alias) |

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

Each show also keeps a step log (resolve → projector → session → play). It's on the admin dashboard, and every cassette insert is in the recorder log on the admin cassettes page.

## The VHS recorder API

There is no login, so it only works on the LAN.

| Request | Effect |
|---|---|
| `POST /api/vhs/insert {"uid": "04A1B2C3"}` | Starts today's title of the cassette's room. In learn mode it binds the cassette instead and nothing plays. Unknown cassettes are logged and ignored. |
| `POST /api/vhs/eject {"uid": "04A1B2C3"}` | Only logged. The film keeps playing. `uid` is optional. |

UIDs are normalised: case, spaces, `:` and `-` don't matter. The response is the logged event, and its `outcome` is `played`, `learned`, `unknown` or `ignored`. If the room can't play (closed today, Jellyfin not configured), the response is `409` with a `detail` message. If the same cassette is read again within 10 seconds of starting a show, the second read is ignored, so a show is never restarted by accident.

## What happens when…

| Situation | Behaviour |
|---|---|
| **The mini-PC reboots** | tarantino starts with the system. Today's programme, sold-out badges, sticky series and cassettes are in the database, and a missing day is generated on first use. A show that was starting during the restart is marked *failed: interrupted by a restart*. Learn mode is cancelled. |
| **Jellyfin is down or restarting** | The website keeps working from the library cache, with posters already in the browser cache. The library sync retries after 1, 2, 4 and 8 minutes, then every 15 minutes. Starting a film fails with *Jellyfin unreachable*. The admin dashboard shows the Jellyfin card in red. |
| **The projector is off or in standby** | Starting a show wakes it via Cast and opens Jellyfin. If it isn't reachable at all (no power, Wi-Fi down), the show fails at the *projector* step with a clear message. The remote connection comes back by itself when the projector does. |
| **The NAS is down** | The media card shows the mounts as unavailable. Mounts are checked with a timeout, so a hanging NFS server never blocks tarantino. Jellyfin can't play the files. |
| **tarantino itself restarts** | Open cinema pages show a small "reconnecting" note, then reload the programme and pick up a show's result automatically. The admin pages retry every few seconds. |

## Backups

A config export (settings, rooms, cassettes and, by default, sticky series and programme history) is written:

- nightly at 03:30,
- before every `update.sh`,
- before every import.

The last 14 of each kind are kept in `/var/lib/tarantino/backups`. You can restore one from the admin *Backups* page, which shows you what would change first, or with `tarantino config import`. Exports never contain secrets, but they do contain addresses and cassette UIDs, so keep them out of the repository (`*.tarantino.json` is gitignored).

To move to a new machine: install, then import the latest backup. Library titles are matched by their TMDB/IMDb/TVDB IDs if Jellyfin has given them new IDs.

## Troubleshooting

| Symptom | Check |
|---|---|
| `tarantino.local` doesn't resolve | `sudo systemctl status tarantino-mdns.service`. Try the mini-PC's IP address. |
| Admin shows "Jellyfin: error" | Is Jellyfin running? Are the API key and user right in the env file? |
| Projector card says *unpaired* | Admin dashboard → pair the projector, then enter the code shown on screen. |
| A show fails at *session* | Pick the projector's device on the admin dashboard. Open the Jellyfin app on the projector once by hand. |
| A show fails at *projector* after "Play Store" | The Jellyfin app has an update pending. Update it on the projector. |
| A cassette does nothing | Admin → *Cassettes* → recorder log. *unknown* means it was never learned, so bind it there. |
| Everything is broken after an update | `sudo journalctl -u tarantino.service -n 100`. Restore the `pre-update` backup if the configuration is damaged. |
