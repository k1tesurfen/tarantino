# Tarantino — Feature Plan: Franchise Runs

Status: **approved 2026-10-12; implemented as M9** (decisions made during implementation: section 5)

Movies that belong to a franchise (Back to the Future, Terminator, Harry Potter, …) should be watched in order. Tarantino keeps its own progress per franchise, independent of Jellyfin's watched state, so franchises can be rewatched again and again. Once a franchise has been started, the following parts are preferred: the same evening via a "Next" option, and on the following days via a daily continuation chance.

This plan records the decisions from the planning Q&A. `plan.md` stays the source of truth for V1. This feature is milestone **M9**.

---

## 1. Facts from the library (checked 2026-10-12)

- The library sync already stores `provider_ids.TmdbCollection` for movies (from Jellyfin's TMDb metadata). About a third of all movies belong to a collection that has 2 or more parts in the library.
- Jellyfin's watched state is nearly empty and is not used for this feature.
- Known data quirks the design must handle:
  - **Missing parts:** e.g. the Jurassic Park collection without *Jurassic Park* itself.
  - **Alternative orders:** Star Wars by release date vs. by episode.
  - **Spin-offs inside a collection:** e.g. *Hobbs & Shaw* in Fast & Furious.
  - **Related films in other collections:** e.g. *Alien: Covenant* (Prometheus collection), *Alien: Romulus*.
  - **Duplicate copies** of the same movie (same TMDb ID).
  - **Collections where order doesn't matter:** e.g. Jackass, Police Story.

---

## 2. Decisions

### Franchises
- **Source:** a franchise is a TMDb collection (`TmdbCollection`) with **at least 2 distinct movies** in the library. Movies without a collection, or alone in theirs, are standalones.
- **Duplicates:** movies with the same TMDb ID count as **one part**. Playing either copy advances the run.
- **Order:** by **premiere date** (falling back to year) by default. In admin, you can **reorder** a franchise or **exclude** a movie (e.g. a spin-off), which then behaves as a standalone.
- **Missing parts:** the order only counts movies in the library. The earliest one available is part 1 (*The Lost World* for Jurassic Park). It never blocks.
- **Name:** the Jellyfin collection (BoxSet) name if Jellyfin has one with that TMDb collection ID, otherwise the title of part 1. It can be **renamed** in admin.
- **"Any order" flag** per franchise: turns the rule off, and its movies behave like standalones.

### The order rule
- **Global and always on** for every movie room. There's no per-room switch; exceptions are set per franchise (the "any order" flag, or excluding a movie).
- Per franchise, **only the next part** (the run's pointer) is eligible in generation. All other parts are blocked.
- **Hard rule:** the order is never relaxed, even if a room's pool runs empty. That room relaxes the cooldown first and closes as today.
- **Room filters always win, including watched/unwatched:** the next part only appears in rooms whose filters it passes. It doesn't matter which room it appears in. Terminator 1 in room 1 can be followed by Terminator 2 in room 2 the next day.
  - An "unwatched" room only offers franchises that are still novel in Jellyfin. Once you have watched them (even partly), they no longer appear there.
  - **Rewatching** happens in rooms whose watched filter is "any" (or "watched"). The existing `watched: any | unwatched | watched` filter covers this, so nothing new is needed.

### Progress (Tarantino-owned)
- Each franchise has a **run** with a pointer to the next part. Jellyfin's watched state is ignored.
- **Advance:** when a part's **show starts via Tarantino** (the same signal as "sold out", `first_started_at`, website or cassette), the pointer moves to the part after it.
- **Out of order:** if a part beyond the pointer is started (e.g. via admin swap), the pointer **jumps past it** (T4 started → next is T5).
- **Finale:** starting the last part finishes the run. The whole franchise then **rests for 60 days** (admin setting `franchise_rest_days`); no part is eligible. After that it is a fresh franchise again, starting at part 1.
- **Stall reset:** if a started run has had no part started for **180 days** (admin setting `franchise_stall_days`), it starts over at part 1.
- **Admin:** reset a run to part 1, or set which part is next.

### Probabilities and cooldowns
- **Part 1 is not special:** it competes like any other movie, with the normal room weights and the normal 30-day movie cooldown.
- **A started run** (pointer past part 1, not resting) gets a **daily continuation chance**: admin setting `franchise_continue_chance`, **0–100 %, default 70**.
  - Before the normal picks, each started run rolls its chance.
  - On a hit, its next part is placed in a **random active movie room whose filters accept it** and that is still free. If no room accepts it, nothing happens that day.
  - **No cap** on how many runs can continue on the same day.
  - The next part of a started run **skips the per-movie cooldown**; the daily chance controls the pacing.
- There is **no per-room franchise weight**. The chance replaces it, because an additive weight would barely register against a pool of hundreds of movies.

### Same-day marathon
- When a franchise part starts in a room, that room **doesn't sell out**. It offers the **next part** for the rest of that cinema day.
  - The started part stays visible and playable (e.g. to restart after a playback failure).
  - The room shows **"Next: Terminator 2"** with its own Play button and ticket flow.
  - Starting the next part advances the run again (→ T3), and so on.
- The next part must pass the **room's filters**. If it doesn't, or the started part was the finale, the room sells out as today.
- The next part ignores the cooldown and today's "used" set. The other rooms never hold it, because only one part per franchise is eligible.
- This only lasts **for that cinema day**. The next day, the continuation chance takes over.

### Cassettes
- **Franchise cassette:** an extra cassette, learned like a room cassette (admin *Cassettes* page / `tarantino learn franchise`). It isn't bound to a room.
- **Binding:** the franchise cassette follows the **franchise movie started most recently today**, from a room cassette or the website. It always plays the **next part** offered by that franchise's room. Example: Rocky started in room 1, later T2 in room 3 → the franchise cassette plays T3. Other started franchises can still be continued via their room cassette or the website's "Next" button.
- **Typical day:** insert a room cassette → part N plays and the franchise cassette is bound to that franchise → franchise cassette → part N+1 → room cassette → part N+2 → … The franchise cassette does nothing until a franchise movie has been started that day.
- **Room cassettes** play what their room currently offers. Once a marathon is running, that is the next part. So a marathon alternates cassettes: room cassette → T1, franchise cassette → T2, room cassette → T3, …
- **No franchise started today:** the franchise cassette does nothing, logged as `ignored` ("no franchise running today").
- **Read guard** (replaces the 10-second repeat window): the recorder only sends inserts, and the reader may fire several times on insert and on eject. **Reads of the cassette that started the latest show are ignored** until a different learned cassette is read, or the cinema day rolls over. To play the same room twice in a row, use the website.
- **Eject** is unchanged: the endpoint and CLI command only log, and no feature depends on it.

### Cinema website
- A franchise badge under the title, e.g. **"Terminator · Part 2 of 6"**, styled per theme (apLex: plain line; Red Apple Cinema: "Chapter II").
- A same-day **"Next"** entry in the room, as described above, in both themes.

### Export / import
- **Config:**
  - The new settings (`franchise_continue_chance`, `franchise_rest_days`, `franchise_stall_days`).
  - Franchise overrides: name, order, exclusions, any-order flag, with movies exported as robust references `{id, name, year, provider_ids}`.
  - The franchise cassette.
- **State:** franchise runs (pointer, last advanced, finished/resting since).
- **Export schema 3**, with a migrator from 2.

---

## 3. Implementation sketch

1. **Model / migration:**
   - `franchise` table: TMDb collection ID, name override, any-order flag, manual order, excluded movies.
   - `franchise_run` table: franchise, next part (TMDb movie ID, so it survives Jellyfin ID changes), last advanced at, finished at.
   - Cassettes: allow a franchise target in addition to a room (room nullable + `role`).
   - Three new settings.
2. **Franchise index** (`programme/franchises.py`): built per generation from `LibraryItem`s and overrides. It resolves each franchise's ordered parts, the next eligible part, run state (fresh / started / resting) and the stall reset. Pure functions, unit-tested.
3. **Engine:**
   - Filter blocked parts out of every movie pool.
   - Run the continuation rolls before the normal room order.
   - Ignore cooldown for continuations.
4. **Advancing:** in `mark_playing`, update the run (including jump-past and finale). Expose the room's "next" part in `entry_for_room` / `day_view`, so the play endpoints and cassettes can start it. Sold out is suppressed while a next part is available.
5. **Cassettes:**
   - Franchise cassette role and learning.
   - The new read guard.
   - Room cassettes play the room's current offering.
   - CLI: `tarantino learn franchise`, `tarantino play franchise`.
6. **Library sync:** optionally fetch BoxSet names (`IncludeItemTypes=BoxSet`) for default franchise names.
7. **Admin:**
   - A *Franchises* page: list with progress and state, rename, reorder, exclude, any-order, reset / set next.
   - The three settings.
   - The franchise cassette on the *Cassettes* page.
8. **Cinema site:** badge and "Next" entry in both themes.
9. **Export / import:** schema 3, preview diff, roundtrip test.

### Tests
- Ordering, duplicates, exclusions, missing first part, any-order.
- Only the next part is eligible. The order is never relaxed.
- Advance on start, jump-past, finale rest, stall reset.
- Continuation roll (seeded), filter compatibility, cooldown bypass.
- Same-day "Next" (filters pass / fail, finale → sold out).
- Franchise cassette: follows the latest started franchise, nothing running → ignored, alternation.
- Read guard: same cassette twice → ignored; a different cassette in between → plays; day rollover resets.
- Export/import roundtrip including runs and overrides.

---

## 4. Milestone

| # | Milestone | Done when |
|---|---|---|
| **M9** | **Franchise runs**: franchise index, order rule, Tarantino-owned progress, continuation chance, same-day "Next", franchise cassette and read guard, admin page, website badge, export schema 3 | On the mini-PC: no sequel appears before its predecessor has been started. Starting part 1 offers "Next: part 2" in that room. The franchise cassette alternating with the room cassette plays a marathon. Repeated reads of the same cassette are ignored. A started franchise continues on following days at about the configured chance |

---

## 5. Decisions made while implementing (for review)

The plan was approved with "decide yourself, write it down". These are the points where the plan was open or where I deviated:

1. **Run storage:** a run stores the list of **started part keys** instead of a single "next part" pointer. Next = the part after the furthest started part in the current order. This makes jump-past, reorders and parts leaving the library behave naturally. A part key is the TMDb movie id (or the Jellyfin id when a movie has none).
2. **Default names:** the Jellyfin collection (BoxSet) name without a trailing " Collection" ("The Terminator Collection" → "The Terminator"). Without a BoxSet, the longest word prefix that at least half of the titles share ("Harry Potter", "Back to the Future", "Star Wars"); a single word only if it is a whole title ("Alien", "Rocky"). Otherwise the title of part 1, as planned. Renamable in admin.
3. **Continuation and normal picks:** the daily roll only happens when a day is generated (rollover, startup), not on an admin re-roll. On a miss, the next part can still be drawn normally like any movie (with the cooldown skipped), so "about 70 %" is a lower bound. Rolls happen in random order; continuation entries are marked `franchise` and show as *continued* on the admin programme page.
4. **What counts as "started via Tarantino":** a show started from a room (website, cassette, admin *Play*) that reaches *playing*. A direct title play from the admin dashboard has no room and doesn't advance a run.
5. **Restarts:** starting a part behind the pointer (e.g. restarting part 1 after part 2 started) changes nothing. Starting any part while the franchise rests, or after a stall, starts a new run.
6. **Marathon room shows the latest part:** after "Next" starts, the room's title becomes that part (with its own "Next" after it). The main Play button restarts that latest part; the "Next" button plays the following one. Room cassettes play the offer, i.e. the next part when there is one.
7. **Marathon stays in its room:** while a franchise has a part started today, a re-roll of another room never picks any of its parts.
8. **Franchise cassette strictness:** it follows only the most recently started franchise movie. If that one has no next part (finale, or the room's filters reject it), the insert is logged as *ignored* with the reason; it doesn't fall back to an older franchise.
9. **Read guard:** the guard is "the cassette that most recently started a show *via a cassette* today". Starts from the website don't release it, so an eject read of a cassette still in the recorder never restarts its room. Unknown cassettes don't release it either; a learned cassette (any outcome) or a learn does.
10. **Duplicates:** whichever copy passes the room's filters is used; once one copy is programmed, the other copies are blocked for that day.
11. **Manual order + new movies:** a part added to the library after the admin reordered a franchise is slotted in right after the part released before it. Reordering back to the premiere-date order clears the override.
12. **Any order / excluded:** any-order franchises still show their name as a badge (no part number). Excluded parts get no badge. A franchise left with fewer than two parts after exclusions has no order rule.
13. **Badges on the website:** apLex shows "Terminator · Part 2 of 6", a gold *Marathon* ribbon and an "Up next here" strip on the card; Red Apple Cinema shows "Chapter II · Terminator" in neon, a *Marathon* tag, a "Held over · the next reel" board under the bill, and "Terminator marathon" on the marquee. Tickets for the next part are at `/tickets/<room>?next=1`.
14. **Deploy day:** the programme that was generated before M9 was deployed stays as it is, so it may still contain sequels. M9's rules apply from the next generated day (or after a re-roll).
