"""Cassettes: RFID UIDs bound to rooms (or the franchise run), learn mode and the VHS event log."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from tarantino.events import EventBus
from tarantino.models import Cassette, Room, VhsEvent

log = logging.getLogger(__name__)

LEARN_SECONDS = 120
EVENT_LOG_SIZE = 500
FRANCHISE = "franchise"  # target of the franchise cassette (not bound to a room)

_SEPARATORS = re.compile(r"[\s:\-]")
_UID = re.compile(r"^[0-9A-Z]{2,32}$")


class CassetteError(Exception):
    pass


def normalise_uid(raw: str) -> str:
    """Uppercase without separators, so `04:a1:b2` and `04A1B2` are the same cassette."""
    uid = _SEPARATORS.sub("", raw or "").upper()
    if not _UID.match(uid):
        raise CassetteError("A cassette UID has 2 to 32 letters or digits")
    return uid


@dataclass
class LearnMode:
    room_number: int | None  # None: the franchise cassette
    room_name: str
    expires_at: datetime

    def view(self, now: datetime) -> dict:
        return {
            "target": "room" if self.room_number is not None else FRANCHISE,
            "room": self.room_number,
            "room_name": self.room_name,
            "expires_at": self.expires_at.isoformat(),
            "seconds_left": max(0, round((self.expires_at - now).total_seconds())),
        }


class Cassettes:
    def __init__(self, session_factory: sessionmaker, events: EventBus, clock: Callable[[], datetime] = datetime.now):
        self.session_factory = session_factory
        self.events = events
        self.clock = clock
        self._learn: LearnMode | None = None

    # -- learn mode ---------------------------------------------------------

    def arm(self, room_number: int | None, seconds: int = LEARN_SECONDS) -> dict:
        """Bind the next inserted cassette to a room, or as the franchise cassette (None); no playback."""
        expires_at = self.clock() + timedelta(seconds=seconds)
        if room_number is None:
            self._learn = LearnMode(None, "Franchise cassette", expires_at)
        else:
            with self.session_factory() as session:
                room = session.scalar(select(Room).where(Room.number == room_number))
            if room is None:
                raise CassetteError(f"No room {room_number}")
            self._learn = LearnMode(room.number, room.name, expires_at)
        log.info("Learn mode armed for %s", self._learn.room_name)
        self._publish()
        return self.learn_state()

    def disarm(self) -> None:
        if self._learn:
            self._learn = None
            self._publish()

    def learn_state(self) -> dict | None:
        if self._learn and self._learn.expires_at <= self.clock():
            self._learn = None
        return self._learn.view(self.clock()) if self._learn else None

    def take_learn(self) -> LearnMode | None:
        """The armed learn mode, if any; consumed by the insert it applies to."""
        if self.learn_state() is None:
            return None
        learn, self._learn = self._learn, None
        return learn

    # -- registry -----------------------------------------------------------

    def bind(self, uid: str, room_number: int | None) -> str | None:
        """Bind a UID to a room, or as the franchise cassette (None).

        Returns a note if it was bound elsewhere before.
        """
        with self.session_factory.begin() as session:
            room = None
            if room_number is not None:
                room = session.scalar(select(Room).where(Room.number == room_number))
                if room is None:
                    raise CassetteError(f"No room {room_number}")
            cassette = session.scalar(select(Cassette).where(Cassette.uid == uid))
            note = None
            if cassette and (cassette.room_id != (room.id if room else None)):
                note = "moved from the franchise cassette" if cassette.room_id is None else \
                    f"moved from room {session.get(Room, cassette.room_id).number}"  # fmt: skip
            cassette = cassette or Cassette(uid=uid)
            cassette.target = "room" if room else FRANCHISE
            cassette.room_id, cassette.learned_at = (room.id if room else None), self.clock()
            session.add(cassette)
        target = f"room {room_number}" if room else "the franchise cassette"
        log.info("Cassette %s bound to %s%s", uid, target, f" ({note})" if note else "")
        self._publish()
        return note

    def remove(self, uid: str) -> None:
        with self.session_factory.begin() as session:
            if session.execute(delete(Cassette).where(Cassette.uid == uid)).rowcount == 0:
                raise CassetteError(f"Unknown cassette {uid}")
        self._publish()

    def room_for(self, uid: str) -> int | None:
        with self.session_factory() as session:
            return session.scalar(select(Room.number).join(Cassette, Cassette.room_id == Room.id).where(Cassette.uid == uid))

    def lookup(self, uid: str) -> int | str | None:
        """The room number a cassette is bound to, FRANCHISE, or None if it was never learned."""
        with self.session_factory() as session:
            cassette = session.scalar(select(Cassette).where(Cassette.uid == uid))
            if cassette is None:
                return None
            if cassette.target == FRANCHISE:
                return FRANCHISE
            return session.get(Room, cassette.room_id).number

    def franchise_cassettes(self) -> list[dict]:
        with self.session_factory() as session:
            cassettes = session.scalars(
                select(Cassette).where(Cassette.target == FRANCHISE).order_by(Cassette.learned_at.desc())
            ).all()
        return [{"uid": c.uid, "learned_at": c.learned_at.isoformat()} for c in cassettes]

    def rooms(self) -> list[dict]:
        """Every room with its cassettes (newest first)."""
        with self.session_factory() as session:
            rooms = session.scalars(select(Room).order_by(Room.number)).all()
            cassettes = session.scalars(select(Cassette).order_by(Cassette.learned_at.desc())).all()
        by_room: dict[int | None, list[dict]] = {}
        for c in cassettes:
            by_room.setdefault(c.room_id, []).append({"uid": c.uid, "learned_at": c.learned_at.isoformat()})
        return [
            {"number": r.number, "name": r.name, "kind": r.kind, "active": r.active, "cassettes": by_room.get(r.id, [])}
            for r in rooms
        ]

    # -- event log ----------------------------------------------------------

    def record(
        self,
        action: str,
        uid: str | None,
        outcome: str,
        room_number: int | None = None,
        message: str | None = None,
        show_id: int | None = None,
    ) -> dict:
        with self.session_factory.begin() as session:
            event = VhsEvent(action=action, uid=uid, room_number=room_number, outcome=outcome,
                             message=message, show_id=show_id, created_at=self.clock())  # fmt: skip
            session.add(event)
            session.flush()
            view = _event_view(event)
            cutoff = event.id - EVENT_LOG_SIZE
            if cutoff > 0:
                session.execute(delete(VhsEvent).where(VhsEvent.id <= cutoff))
        log.info("VHS %s %s: %s%s", action, uid or "-", outcome, f" ({message})" if message else "")
        self._publish(view)
        return view

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self.session_factory() as session:
            events = session.scalars(select(VhsEvent).order_by(VhsEvent.id.desc()).limit(limit)).all()
        return [_event_view(e) for e in events]

    def is_guarded(self, uid: str, since: datetime) -> bool:
        """The read guard: the reader fires several times (on insert and on eject), so reads of the
        cassette that started the latest cassette show are ignored until a different learned
        cassette is read, or the cinema day (starting at `since`) rolls over."""
        with self.session_factory() as session:
            latest = session.scalar(
                select(VhsEvent)
                .where(VhsEvent.action == "insert", VhsEvent.outcome == "played", VhsEvent.created_at >= since)
                .order_by(VhsEvent.id.desc())
                .limit(1)
            )
            if latest is None or latest.uid != uid:
                return False
            other = session.scalar(
                select(VhsEvent.id)
                .where(VhsEvent.action == "insert", VhsEvent.id > latest.id, VhsEvent.uid != uid,
                       VhsEvent.outcome != "unknown")
                .limit(1)
            )  # fmt: skip
            return other is None

    def _publish(self, event: dict | None = None) -> None:
        self.events.publish("vhs", {"event": event, "learn": self.learn_state()})


def _event_view(event: VhsEvent) -> dict:
    return {
        "id": event.id,
        "action": event.action,
        "uid": event.uid,
        "room": event.room_number,
        "outcome": event.outcome,
        "message": event.message,
        "show_id": event.show_id,
        "at": event.created_at.isoformat(),
    }
