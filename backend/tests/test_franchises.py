"""M9: franchise runs (order rule, progress, continuation chance, same-day marathon)."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from test_programme import NOON, item, room_id, world  # noqa: F401 (fixture)
from tarantino.models import Franchise as FranchiseOverride
from tarantino.models import FranchiseRun, LibraryCollection, ProgrammeEntry, Room
from tarantino.programme import franchises
from tarantino.programme.franchises import build_index, run_state
from tarantino.settings import AppSettings, SettingsStore

SETTINGS = AppSettings()
T = "900"  # TMDb collection id of the test franchise


def part(n: int, year: int, collection: str = T, tmdb: str | None = None, **fields):
    """A franchise movie; `tmdb` defaults to n (give the same value for duplicate copies)."""
    return item(
        n, name=f"Part {n}", year=year, premiere_date=date(year, 6, 1),
        provider_ids={"Tmdb": tmdb or str(n), "TmdbCollection": collection}, **fields,
    )  # fmt: skip


def saga(first: int = 501, years=(1984, 1991, 2003, 2009)):
    return [part(first + i, year) for i, year in enumerate(years)]


def ids(*numbers: int) -> list[str]:
    return [f"{n:032x}" for n in numbers]


def index_of(items, overrides=(), runs=(), names=None, now=NOON):
    return build_index(items, overrides, runs, names or {}, now, SETTINGS)


# -- the franchise index (pure) ----------------------------------------------------


def test_franchises_need_two_distinct_movies_and_are_ordered_by_premiere():
    items = [part(503, 2003), part(501, 1984), part(502, 1991), part(600, 2000, collection="901"), item(1)]
    index = index_of(items)
    assert list(index.franchises) == [T]  # 901 has only one movie: standalone
    franchise = index.franchises[T]
    assert [p.item.id for p in franchise.parts] == ids(501, 502, 503)
    assert franchise.name == "Part 501"  # no Jellyfin collection name: the title of part 1
    assert index.badge(ids(502)[0]) == {"name": "Part 501", "part": 2, "parts": 3, "ordered": True}
    assert index.badge(ids(600)[0]) is None and index.badge(ids(1)[0]) is None


def test_duplicate_copies_are_one_part():
    items = [part(501, 1984), part(502, 1991), part(512, 1991, tmdb="502")]
    franchise = index_of(items).franchises[T]
    assert len(franchise.parts) == 2
    assert franchise.parts[1].item_ids == set(ids(502, 512))
    assert index_of(items).siblings(ids(512)[0]) == set(ids(502, 512))


def test_two_copies_of_one_movie_are_not_a_franchise():
    assert index_of([part(501, 1984), part(511, 1984, tmdb="501")]).franchises == {}


def test_missing_first_part_starts_at_the_earliest_available():
    franchise = index_of(saga()[1:]).franchises[T]
    assert franchise.next_part.item.id == ids(502)[0]


def test_names_come_from_jellyfin_collections_or_the_override():
    names = {T: "The Terminator Collection"}
    assert index_of(saga(), names=names).franchises[T].name == "The Terminator"
    override = FranchiseOverride(collection_id=T, name="Terminator", any_order=False, order=[], excluded=[])
    franchise = index_of(saga(), [override], names=names).franchises[T]
    assert (franchise.name, franchise.default_name) == ("Terminator", "The Terminator")


def test_exclusions_any_order_and_manual_order():
    items = saga()
    excluded = FranchiseOverride(collection_id=T, any_order=False, order=[], excluded=["503"])
    index = index_of(items, [excluded])
    assert [p.key for p in index.franchises[T].parts] == ["501", "502", "504"]
    assert not index.blocked(ids(503)[0]) and index.badge(ids(503)[0]) is None  # a standalone now

    any_order = FranchiseOverride(collection_id=T, any_order=True, order=[], excluded=[])
    index = index_of(items, [any_order])
    assert not any(index.blocked(i) for i in ids(501, 502, 503, 504))
    assert index.badge(ids(502)[0])["part"] is None

    # A manual order; a part added to the library later is slotted in by date.
    manual = FranchiseOverride(collection_id=T, any_order=False, order=["503", "501", "504"], excluded=[])
    franchise = index_of(items, [manual]).franchises[T]
    assert [p.key for p in franchise.parts] == ["503", "501", "502", "504"]


def run(started, advanced=NOON, finished=None):
    return FranchiseRun(collection_id=T, started_parts=started, started_at=advanced,
                        last_advanced_at=advanced, finished_at=finished)  # fmt: skip


def test_run_states():
    keys = ["501", "502", "503", "504"]
    assert run_state(None, keys, NOON, SETTINGS) == ("fresh", 0, None)
    assert run_state(run(["501"]), keys, NOON, SETTINGS) == ("started", 1, None)
    assert run_state(run(["501", "503"]), keys, NOON, SETTINGS) == ("started", 3, None)
    # Stalled for 180 days: over.
    assert run_state(run(["501"], NOON - timedelta(days=180)), keys, NOON, SETTINGS)[0] == "fresh"
    # The finale rests the franchise for 60 days.
    finished = run(keys, finished=NOON - timedelta(days=59))
    assert run_state(finished, keys, NOON, SETTINGS)[:2] == ("resting", None)
    assert run_state(run(keys, finished=NOON - timedelta(days=60)), keys, NOON, SETTINGS)[0] == "fresh"


def test_only_the_next_part_is_eligible():
    index = index_of(saga())
    assert [index.blocked(i) for i in ids(501, 502, 503, 504)] == [False, True, True, True]
    index = index_of(saga(), runs=[run(["501"])])
    assert [index.blocked(i) for i in ids(501, 502, 503, 504)] == [True, False, True, True]
    assert index.continues(ids(502)[0]) and not index.continues(ids(501)[0])
    index = index_of(saga(), runs=[run(["501", "502", "503", "504"], finished=NOON)])
    assert all(index.blocked(i) for i in ids(501, 502, 503, 504))  # resting


def advanced(index, item_number, existing=None, now=NOON):
    franchise = index.franchises[T]
    return franchises.advance(franchise, existing if existing is not None else franchise.run, ids(item_number)[0], now)


def test_advance_jumps_past_and_finishes():
    first = advanced(index_of(saga()), 501)
    assert first.started_parts == ["501"] and first.finished_at is None
    # Out of order: part 3 started (e.g. via an admin swap) -> next is part 4.
    jumped = advanced(index_of(saga(), runs=[first]), 503)
    assert jumped.started_parts == ["501", "503"]
    assert index_of(saga(), runs=[jumped]).franchises[T].next_part.key == "504"
    # Restarting an earlier part changes nothing.
    assert advanced(index_of(saga(), runs=[jumped]), 502) is None
    # The finale finishes the run.
    finale = advanced(index_of(saga(), runs=[jumped]), 504)
    assert finale.finished_at == NOON
    # Duplicate copies advance the same part.
    with_copy = saga() + [part(512, 1991, tmdb="502")]
    assert advanced(index_of(with_copy, runs=[run(["501"])]), 512).started_parts == ["501", "502"]


def test_starting_a_part_while_resting_or_stalled_starts_over():
    resting = run(["501", "502", "503", "504"], finished=NOON)
    again = advanced(index_of(saga(), runs=[resting]), 501, now=NOON + timedelta(days=1))
    assert again.started_parts == ["501"] and again.finished_at is None
    stalled = run(["501", "502"], NOON - timedelta(days=200))
    assert advanced(index_of(saga(), runs=[stalled]), 501).started_parts == ["501"]


# -- the engine ------------------------------------------------------------------------


def only_rooms(w, *numbers):
    with w.session_factory.begin() as session:
        for room in session.scalars(select(Room)):
            room.active = room.number in numbers


def set_chance(w, chance: int):
    SettingsStore(w.session_factory).update({"franchise_continue_chance": chance})


def rooms(w):
    return {r["number"]: r for r in w.programme.day_view()["rooms"]}


def run_of(w):
    with w.session_factory() as session:
        return session.scalar(select(FranchiseRun).where(FranchiseRun.collection_id == T))


def test_no_sequel_is_programmed_before_its_predecessor_started(world):
    world.add(*saga(), *(item(n) for n in range(1, 8)))
    sequels = set(ids(502, 503, 504))
    shown = set()
    for _ in range(40):
        world.programme.ensure_day()
        assert not sequels & set(world.entries().values())
        shown |= set(world.entries().values())
        world.clock.next_day()
    assert ids(501)[0] in shown  # part 1 competes like any other movie


def test_the_order_is_never_relaxed(world):
    """A room whose only matches are sequels closes rather than break the order."""
    only_rooms(world, 4)  # unwatched horror
    world.add(*saga()[:1], *(part(n, y, genres=["Horror"]) for n, y in ((502, 1991), (503, 2003))))
    world.programme.ensure_day()
    assert world.entries() == {4: None}


def test_starting_part_one_offers_the_next_part_the_same_day(world):
    only_rooms(world, 1, 2)
    world.add(*saga(), *(item(n) for n in range(1, 5)))
    world.programme.swap(1, ids(501)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(501)[0])

    room = rooms(world)[1]
    assert room["item"]["id"] == ids(501)[0] and room["next"]["id"] == ids(502)[0]
    assert not room["sold_out"] and room["started"]
    assert room["item"]["franchise"] == {"name": "Part 501", "part": 1, "parts": 4, "ordered": True}

    # The next part starts: the marathon moves on, and the run with it.
    world.programme.mark_playing(room_id(world, 1), ids(502)[0])
    room = rooms(world)[1]
    assert (room["item"]["id"], room["next"]["id"], room["marathon"]) == (ids(502)[0], ids(503)[0], 1)
    assert run_of(world).started_parts == ["501", "502"]

    # Restarting the part that is on (a playback failure) changes nothing.
    world.programme.mark_playing(room_id(world, 1), ids(502)[0])
    assert rooms(world)[1]["next"]["id"] == ids(503)[0]

    for n in (503, 504):
        world.programme.mark_playing(room_id(world, 1), ids(n)[0])
    room = rooms(world)[1]
    assert room["item"]["id"] == ids(504)[0] and room["next"] is None and room["sold_out"]  # finale
    assert run_of(world).finished_at is not None


def test_next_part_must_pass_the_room_filters(world):
    only_rooms(world, 1)  # unwatched
    world.add(saga()[0], part(502, 1991, played=True), *(item(n) for n in range(1, 3)))
    world.programme.swap(1, ids(501)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(501)[0])
    room = rooms(world)[1]
    assert room["next"] is None and room["sold_out"]


def test_the_marathon_stays_in_its_room(world):
    """A reroll of another room never picks the part that a marathon offers."""
    only_rooms(world, 1, 2)
    world.add(*saga(), item(1))
    world.programme.swap(1, ids(501)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(501)[0])
    for _ in range(10):
        world.programme.reroll(2)
        assert world.entries()[2] == ids(1)[0]


def test_marathon_ends_with_the_cinema_day(world):
    only_rooms(world, 1)
    world.add(*saga())
    world.programme.swap(1, ids(501)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(501)[0])
    world.clock.next_day()
    set_chance(world, 0)
    world.programme.ensure_day()
    room = rooms(world)[1]
    assert room["item"]["id"] == ids(502)[0] and room["next"] is None and not room["started"]


def test_a_started_franchise_continues_in_a_room_that_accepts_it(world):
    """Chance 100: the next part is placed before the normal picks, in a room whose filters fit."""
    only_rooms(world, 1, 5)  # 1: unwatched; 5: watched favourites
    world.add(*saga()[:1], part(502, 1991, played=True, favorite=True), *saga()[2:])
    world.add(*(item(n) for n in range(1, 10)), *(item(n, played=True, favorite=True) for n in range(100, 110)))
    world.programme.swap(1, ids(501)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(501)[0])

    set_chance(world, 100)
    world.clock.next_day()
    world.programme.ensure_day()
    assert world.entries()[5] == ids(502)[0]
    assert rooms(world)[5]["source"] == "franchise"


def test_continuation_skips_the_cooldown(world):
    only_rooms(world, 1)
    world.add(*saga(), *(item(n) for n in range(1, 10)))
    with world.session_factory.begin() as session:  # part 2 ran (unstarted) yesterday
        session.add(ProgrammeEntry(cinema_date=world.programme.today() - timedelta(days=1), room_id=room_id(world, 1),
                                   item_id=ids(502)[0], showtimes=[], source="generated", created_at=NOON))  # fmt: skip
        session.add(run(["501"]))
    set_chance(world, 100)
    world.programme.ensure_day()
    assert world.entries()[1] == ids(502)[0]


def test_continuation_chance_is_about_right(world):
    only_rooms(world, 1, 2, 3)
    world.add(*saga(), *(item(n) for n in range(1, 60)))
    set_chance(world, 50)
    hits = 0
    for _ in range(200):
        with world.session_factory.begin() as session:  # keep the run at part 2
            session.execute(delete(FranchiseRun))
            session.add(run(["501"], world.clock()))
        world.programme.ensure_day()
        with world.session_factory() as session:
            sources = {e.item_id: e.source for e in session.scalars(
                select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == world.programme.today()))}  # fmt: skip
        hits += sources.get(ids(502)[0]) == "franchise"
        world.clock.next_day()
    assert 75 <= hits <= 125


def test_duplicate_copies_never_run_twice_on_one_day(world):
    only_rooms(world, 1, 2, 3)
    world.add(part(501, 1984), part(511, 1984, tmdb="501"), part(502, 1991))
    for _ in range(20):
        world.programme.reroll()
        assert not set(ids(501, 511)) <= set(world.entries().values())


def test_playing_either_copy_advances_the_run(world):
    only_rooms(world, 1)
    world.add(part(501, 1984), part(511, 1984, tmdb="501"), part(502, 1991))
    world.programme.swap(1, ids(511)[0])
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), ids(511)[0])
    assert run_of(world).started_parts == ["501"]
    assert rooms(world)[1]["next"]["id"] == ids(502)[0]


def test_franchise_room_follows_the_latest_started_franchise(world):
    only_rooms(world, 1, 2, 3)
    other = [part(n, y, collection="902") for n, y in ((701, 1976), (702, 1979))]
    world.add(*saga(), *other, item(1))
    world.programme.swap(1, ids(701)[0])
    world.programme.swap(2, ids(1)[0])
    world.programme.swap(3, ids(501)[0])
    assert world.programme.franchise_room() is None
    world.programme.mark_playing(room_id(world, 1), ids(701)[0])
    assert world.programme.franchise_room() == (1, "Part 701", ids(702)[0])
    world.clock.now += timedelta(minutes=5)
    world.programme.mark_playing(room_id(world, 2), ids(1)[0])  # a standalone does not count
    world.programme.mark_playing(room_id(world, 3), ids(501)[0])
    assert world.programme.franchise_room() == (3, "Part 501", ids(502)[0])
    world.clock.now += timedelta(minutes=5)
    world.programme.mark_playing(room_id(world, 1), ids(702)[0])  # the finale: nothing next
    assert world.programme.franchise_room() == (1, "Part 701", None)


def test_collection_names_from_the_library_sync(world):
    world.add(*saga())
    with world.session_factory.begin() as session:
        session.add(LibraryCollection(id=T, name="The Terminator Collection", synced_at=NOON))
    assert world.programme.franchise_badge(ids(503)[0])["name"] == "The Terminator"


@pytest.mark.parametrize("chance", [0, 100])
def test_resting_franchise_is_never_programmed(world, chance):
    only_rooms(world, 1, 2)
    world.add(*saga(), item(1), item(2), item(3))
    with world.session_factory.begin() as session:
        session.add(run(["501", "502", "503", "504"], finished=world.clock() - timedelta(days=10)))
    set_chance(world, chance)
    for _ in range(10):
        world.programme.reroll()
        assert not set(ids(501, 502, 503, 504)) & set(world.entries().values())
    world.clock.now = datetime.combine(world.clock.now.date(), NOON.time()) + timedelta(days=60)
    for _ in range(20):
        world.programme.reroll()
        assert not set(ids(502, 503, 504)) & set(world.entries().values())


@pytest.mark.parametrize(("titles", "name"), [
    (["Harry Potter and the Philosopher's Stone", "Harry Potter and the Chamber of Secrets"], "Harry Potter"),
    (["Back to the Future", "Back to the Future Part II", "Back to the Future Part III"], "Back to the Future"),
    (["The Terminator", "Terminator 2: Judgment Day", "Terminator 3: Rise of the Machines", "Terminator Salvation"],
     "Terminator"),
    (["Star Wars", "The Empire Strikes Back", "Star Wars: Episode I - The Phantom Menace",
      "Star Wars: Episode II - Attack of the Clones"], "Star Wars"),
    (["The Lord of the Rings: The Fellowship of the Ring", "The Lord of the Rings: The Two Towers"],
     "The Lord of the Rings"),
    (["28 Days Later", "28 Weeks Later"], None),
    (["The Hunt for Red October", "Patriot Games"], None),
    (["The Thing", "The Fog"], None),
    (["Finding Nemo", "Finding Dory"], None),
    (["Alien", "Aliens", "Alien³", "Alien Resurrection"], "Alien"),
    (["Guardians of the Galaxy", "Guardians of the Galaxy Vol. 2", "Guardians of the Galaxy Vol. 3"],
     "Guardians of the Galaxy"),
    (["Kill Bill: Vol. 1", "Kill Bill: Vol. 2"], "Kill Bill"),
])
def test_guessed_franchise_names(titles, name):
    assert franchises.guess_name(titles) == name


def test_collection_suffix_is_dropped():
    assert franchises.collection_name("The Terminator Collection") == "The Terminator"
    assert franchises.collection_name("Collection") == "Collection"
