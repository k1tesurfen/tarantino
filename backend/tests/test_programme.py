import random
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from tarantino.db import create_db_engine, make_session_factory, migrate
from tarantino.models import LibraryItem, ProgrammeEntry, Room, SeriesAssignment
from tarantino.programme.engine import Programme, ProgrammeError, cinema_date, fake_showtimes
from tarantino.settings import SettingsStore

DAY = date(2026, 10, 10)
NOON = datetime(2026, 10, 10, 12, 0)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def next_day(self) -> None:
        self.now += timedelta(days=1)


def item(n: int, type_: str = "movie", **fields) -> LibraryItem:
    defaults = dict(
        id=f"{n:032x}", type=type_, name=f"{type_} {n}", genres=["Drama"], tags=[], studios=[], people=[],
        provider_ids={}, trailer_urls=[], image_tags={"Primary": f"p{n}"}, played=False, favorite=False,
        play_count=0, runtime_minutes=100, synced_at=NOON, unplayed_count=5 if type_ == "series" else None,
    )  # fmt: skip
    return LibraryItem(**(defaults | fields))


@pytest.fixture
def world(tmp_path):
    engine = create_db_engine(tmp_path / "data")
    migrate(engine)
    session_factory = make_session_factory(engine)
    clock = Clock(NOON)
    programme = Programme(session_factory, SettingsStore(session_factory), random.Random(7), clock)
    programme.ensure_rooms()

    def add(*items: LibraryItem) -> None:
        with session_factory.begin() as session:
            for i in items:
                session.merge(i)

    def entries(day: date = None) -> dict[int, str | None]:
        with session_factory() as session:
            rows = session.execute(
                select(Room.number, ProgrammeEntry.item_id)
                .join(Room, Room.id == ProgrammeEntry.room_id)
                .where(ProgrammeEntry.cinema_date == (day or programme.today()))
            )
            return dict(rows.all())

    class World:
        pass

    w = World()
    w.programme, w.session_factory, w.clock, w.add, w.entries = programme, session_factory, clock, add, entries
    return w


def standard_library(w, movies: int = 30, series: int = 8) -> None:
    w.add(*(item(n, genres=["Horror"] if n % 5 == 0 else ["Drama"]) for n in range(1, movies + 1)))
    w.add(*(item(n, played=True, favorite=True) for n in range(100, 105)))
    w.add(*(item(n, "series") for n in range(200, 200 + series)))


def room_id(w, number: int) -> int:
    with w.session_factory() as session:
        return session.scalar(select(Room.id).where(Room.number == number))


def test_cinema_day_rolls_over_at_the_configured_hour():
    assert cinema_date(datetime(2026, 10, 11, 4, 59), 5) == date(2026, 10, 10)
    assert cinema_date(datetime(2026, 10, 11, 5, 0), 5) == date(2026, 10, 11)
    assert cinema_date(datetime(2026, 10, 11, 0, 30), 0) == date(2026, 10, 11)


def test_fake_showtimes_are_stable_and_spaced_by_runtime():
    times = fake_showtimes(DAY, 3, 150)
    assert times == fake_showtimes(DAY, 3, 150)
    assert 1 <= len(times) <= 3
    minutes = [int(t[:2]) * 60 + int(t[3:]) for t in times]
    assert minutes[0] >= 14 * 60 and minutes[-1] <= 23 * 60 + 30
    assert all(b - a == 180 for a, b in zip(minutes, minutes[1:]))  # 150 + 30, rounded to 15


def test_default_rooms_are_created_once(world):
    world.programme.ensure_rooms()
    with world.session_factory() as session:
        rooms = session.scalars(select(Room).order_by(Room.number)).all()
    assert [r.number for r in rooms] == list(range(1, 11))
    assert [r.kind for r in rooms].count("series") == 4


def test_nothing_is_generated_before_the_library_is_synced(world):
    assert world.programme.ensure_day() == 0
    assert world.entries() == {}


def test_day_is_generated_once_with_rules_respected(world):
    standard_library(world)
    assert world.programme.ensure_day() == 10
    assert world.programme.ensure_day() == 0

    picks = world.entries()
    titles = [i for i in picks.values() if i]
    assert len(titles) == len(set(titles)) == 10  # no title twice on one day

    with world.session_factory() as session:
        by_id = {i.id: i for i in session.scalars(select(LibraryItem))}
    for number in (1, 2, 3, 6):
        assert by_id[picks[number]].type == "movie" and not by_id[picks[number]].played
    horror = by_id[picks[4]]
    assert "Horror" in horror.genres and not horror.played
    repertory = by_id[picks[5]]
    assert repertory.played and repertory.favorite
    assert all(by_id[picks[n]].type == "series" for n in (7, 8, 9, 10))


def test_room_without_matching_titles_is_closed(world):
    world.add(*(item(n) for n in range(1, 20)), *(item(n, "series") for n in range(200, 205)))  # no favourites
    world.programme.ensure_day()
    view = world.programme.day_view()
    repertory = next(r for r in view["rooms"] if r["number"] == 5)
    assert repertory["item"] is None and repertory["showtimes"] == []


def test_cooldown_prevents_repeats_until_the_pool_runs_out(world):
    with world.session_factory.begin() as session:  # only room 3 stays active
        for room in session.scalars(select(Room)):
            room.active = room.number == 3
    world.add(*(item(n) for n in range(1, 4)))

    seen = []
    for _ in range(3):
        world.programme.ensure_day()
        seen.append(world.entries()[3])
        world.clock.next_day()
    assert sorted(seen) == sorted(f"{n:032x}" for n in range(1, 4))  # all different while fresh ones exist

    world.programme.ensure_day()  # all three in cooldown: still shows something instead of closing
    assert world.entries()[3] in seen


def test_reroll_changes_only_the_requested_room(world):
    standard_library(world)
    world.programme.ensure_day()
    before = world.entries()
    world.programme.reroll(2)
    after = world.entries()
    assert after[2] != before[2]
    assert {n: i for n, i in after.items() if n != 2} == {n: i for n, i in before.items() if n != 2}
    assert len(set(after.values())) == 10


def test_reroll_whole_day(world):
    standard_library(world, movies=60)
    world.programme.ensure_day()
    before = world.entries()
    world.programme.reroll()
    after = world.entries()
    assert sum(after[n] != before[n] for n in (1, 2, 3, 6)) >= 3
    assert len(set(after.values())) == 10


def test_swap_overrides_a_room(world):
    standard_library(world)
    world.programme.ensure_day()
    picks = world.entries()
    free_movie = next(f"{n:032x}" for n in range(1, 31) if f"{n:032x}" not in picks.values())

    world.programme.swap(1, free_movie)
    assert world.entries()[1] == free_movie
    assert next(r for r in world.programme.day_view()["rooms"] if r["number"] == 1)["source"] == "override"

    with pytest.raises(ProgrammeError, match="shows movie, not series"):
        world.programme.swap(1, f"{200:032x}")
    with pytest.raises(ProgrammeError, match="already runs in another room"):
        world.programme.swap(2, free_movie)


def test_series_becomes_sticky_when_started_and_stays_in_its_room(world):
    standard_library(world)
    world.programme.ensure_day()
    series_id = world.entries()[8]
    world.programme.mark_playing(room_id(world, 8), series_id)

    for _ in range(5):
        world.clock.next_day()
        world.programme.ensure_day()
        picks = world.entries()
        assert picks[8] == series_id
        assert series_id not in (picks[7], picks[9], picks[10])
    lounge = next(r for r in world.programme.day_view()["rooms"] if r["number"] == 8)
    assert lounge["sticky"] and not lounge["sold_out"]


def test_partially_watched_series_is_not_sticky_unless_started_here(world):
    world.add(*(item(n) for n in range(1, 20)))
    world.add(item(200, "series", unplayed_count=3), *(item(n, "series") for n in range(201, 210)))
    world.programme.ensure_day()
    assert all(not r["sticky"] for r in world.programme.day_view()["rooms"])


def test_finished_series_is_released_and_returns_with_a_new_season(world):
    standard_library(world)
    world.programme.ensure_day()
    series_id = world.entries()[7]
    world.programme.mark_playing(room_id(world, 7), series_id)

    world.add(item(int(series_id, 16), "series", played=True, unplayed_count=0))  # watched to the end
    world.clock.next_day()
    world.programme.ensure_day()
    assert series_id not in world.entries().values()
    with world.session_factory() as session:
        assignment = session.scalar(select(SeriesAssignment))
    assert assignment.finished_at is not None

    # A new season arrives while every other series is finished: it must come back.
    world.add(*(item(n, "series", played=True, unplayed_count=0) for n in range(200, 208)))
    world.add(item(int(series_id, 16), "series", played=False, unplayed_count=10))
    world.clock.next_day()
    world.programme.ensure_day()
    assert series_id in world.entries().values()


def test_drop_series_frees_the_room(world):
    standard_library(world)
    world.programme.ensure_day()
    series_id = world.entries()[9]
    world.programme.mark_playing(room_id(world, 9), series_id)
    world.programme.drop_series(9)
    assert world.entries()[9] != series_id
    with pytest.raises(ProgrammeError, match="no sticky series"):
        world.programme.drop_series(9)


def test_sold_out_only_for_movies_and_only_today(world):
    standard_library(world)
    world.programme.ensure_day()
    picks = world.entries()
    world.programme.mark_playing(room_id(world, 1), picks[1])
    world.programme.mark_playing(room_id(world, 7), picks[7])
    rooms = {r["number"]: r for r in world.programme.day_view()["rooms"]}
    assert rooms[1]["sold_out"] and not rooms[2]["sold_out"]
    assert not rooms[7]["sold_out"]

    world.clock.next_day()
    world.programme.ensure_day()
    assert not any(r["sold_out"] for r in world.programme.day_view()["rooms"])


def test_mark_playing_ignores_a_different_title(world):
    standard_library(world)
    world.programme.ensure_day()
    world.programme.mark_playing(room_id(world, 1), f"{999:032x}")
    assert not any(r["sold_out"] for r in world.programme.day_view()["rooms"])
