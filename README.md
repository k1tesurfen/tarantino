# tarantino

**Home Cinema Infrastructure**: the brain of a home cinema. It turns an RFID-tagged VHS cassette into a fully choreographed movie night.

> Insert a cassette into a retro VHS recorder → the projector powers on, the screen lowers, the lights dim, and Jellyfin starts playing the film on the projector.

Tarantino also runs an imaginary multiplex. Every day it generates a fresh programme across themed auditoriums for films and a lounge for series. The programme is shown on a website that looks and works like a real cinema's. Each room is bound to a VHS cassette, so cassette "1" plays whatever runs in Auditorium 1 today.

---

## Status

🚧 **Planning phase.** Nothing is implemented yet. See [`plan.md`](plan.md) for the V1 implementation plan.

---

## Hardware & software

| Component | Role | Details |
|---|---|---|
| **NAS** | Media storage | Two NFS exports, `movies` and `series`. Only the mini-PC may mount them. |
| **Mini-PC** | Server | Debian Linux. Runs the Jellyfin server bare-metal and hosts a Home Assistant VM. Runs Tarantino 24/7. |
| **Jellyfin server** | Media library & streaming | Serves 4K uncompressed Blu-ray rips. Source of all metadata, artwork and trailer links. |
| **Home Assistant** (VM on the mini-PC) | Home automation | Lights, and later projector power, AVR, etc. |
| **Projector** | Playback device | Android TV with the Jellyfin Android TV app. Controlled via Jellyfin sessions and network ADB. |
| **Motorized projector screen** (planned) | Screen | Lowered while a USB port on the mini-PC supplies power, raised when power is cut. |
| **VHS recorder** (retro) | Physical movie selector | Houses an ESP32 and an RFID reader. Cassettes carry RFID stickers. |
| **ESP32 + RFID reader** | Cassette detection | Reads a cassette's RFID tag and reports it to Tarantino over the network. |
| **AVR** (future) | Audio | Possibly powered on as part of the show. |

---

## Architecture

```
                 ┌──────────────────────────── mini-PC (Debian) ─────────────────────────────┐
                 │                                                                            │
┌─────────────┐  │  ┌───────────────────────── tarantino core (24/7) ─────────────────────┐   │
│ VHS recorder│──┼─▶│  REST API ─ cassette events, playback, programme, admin             │   │
│ ESP32 + RFID│  │  │  Programme engine ─ daily selection per room                        │   │
└─────────────┘  │  │  Show orchestrator ─ the "start the show" sequence                  │   │
                 │  │  Jellyfin client ─ library, metadata, sessions, remote control      │─┐ │
┌─────────────┐  │  │  Device adapters ─ projector (ADB), screen (USB), Home Assistant    │ │ │
│ Browser(LAN)│──┼─▶│  Web UI ─ cinema site + admin site                                  │ │ │
└─────────────┘  │  └─────────────────────────────────────────────────────────────────────┘ │ │
                 │        │ USB power             │ HTTP                                     │ │
                 │        ▼                       ▼                                          │ │
                 │  ┌──────────┐   ┌──────────────────────────┐   ┌───────────────────┐      │ │
                 │  │ screen   │   │ Home Assistant (VM)      │   │ Jellyfin server   │◀─────┘ │
                 │  └──────────┘   │ lights, AVR, …           │   └─────────┬─────────┘        │
                 │                 └──────────────────────────┘             │ NFS              │
                 └──────────────────────────────────────────────────────────┼──────────────────┘
                                                                            ▼
      ┌──────────────────────────┐  Jellyfin remote control + ADB     ┌──────────┐
      │ Projector                │◀────────────────────────────────── │   NAS    │
      │ Android TV + Jellyfin app│                                    └──────────┘
      └──────────────────────────┘
```

---

## Subsystems

### 1. Tarantino core (mini-PC, always on)
- **REST API**: cassette insert and eject events, playback, programme, admin.
- **Cassette registry**: maps RFID tag UIDs to rooms, with a learning mode.
- **Programme engine**: each day it generates one title per room according to that room's rules. Series stay in their room until finished.
- **Show orchestrator**: the chain reaction triggered by a cassette or the cinema website:
  1. Resolve cassette → room → today's title.
  2. Wake the projector and open the Jellyfin app.
  3. *(V2)* Lower the screen, dim the lights, power on the AVR.
  4. Start playback on the projector's Jellyfin session.
- **Jellyfin integration**: library and metadata (artwork, synopsis, cast, ratings, trailers, watched and favourite state), sessions, remote control.
- **Settings export/import**: the whole admin configuration (secrets excluded) as a file, so a setup survives resets and reinstalls.

### 2. Admin website (LAN, password-protected)
- Status of every subsystem: Jellyfin, projector, NFS, Home Assistant.
- Rooms and their rules, cassettes, theme names, settings.
- Today's programme with overrides (re-roll, swap), and a show log.
- Export and import of the configuration.

### 3. Cinema website (LAN, open)
- Looks and behaves like a real cinema website, with switchable full-layout themes. V1 ships a modern multiplex theme ("apLex") and a retro grindhouse theme ("Red Apple Cinema"). Both names can be changed in admin.
- A new programme every day:
  - Movie auditoriums, e.g. unwatched films, unwatched horror, favourites.
  - A series lounge, where a started series returns every day until it's finished.
- Title pages built from Jellyfin metadata, including trailers.
- Start a film with one click, or through a playful ticket flow.

### 4. Home Assistant plugin (later)
- Projector power, lights-down scene, AVR power, Tarantino state as HA entities.

### 5. VHS reader firmware (later)
- ESP32 and RFID reader inside the VHS recorder. It posts cassette events to the Tarantino REST API.

---

## Roadmap

| Slice | Scope |
|---|---|
| **V1** | Core service, Jellyfin integration, daily programme engine (6 movie rooms and 4 series rooms by default), cinema website with two themes, admin website with subsystem status, playback on the projector (Jellyfin remote control + ADB), VHS cassette API with learning mode and a test CLI, settings export/import. |
| V2 – The Show | Motorized screen, lights and AVR via Home Assistant, end-of-show sequence, pre-show trailers, ESP32 firmware. |
| V3 | Home Assistant plugin. |
| Later | More cinema themes and room presets, statistics, remote access. |

---

## Contributing / public repo rules

This repository is public. **Never commit** tokens, passwords, API keys, IP addresses, hostnames, usernames, or exported configuration files. Secrets live in a local `.env` file (see `deploy/env.example` once it exists). Device-specific values such as IPs live in the admin settings, not in code. Use generic names in code and docs: *mini-PC*, *NAS*, *projector*, *VHS recorder*.

---

## License

See [LICENSE](LICENSE).
