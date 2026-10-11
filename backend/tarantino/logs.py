"""Logging setup: plain lines on stderr, which systemd forwards to the journal.

Under systemd each line gets a `<N>` syslog priority prefix, so
`journalctl -u tarantino.service -p warning` shows only warnings and errors.
"""

import logging
import os

# syslog priorities: 3 err, 4 warning, 6 info, 7 debug
_PRIORITIES = ((logging.ERROR, 3), (logging.WARNING, 4), (logging.INFO, 6))


class JournalFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        priority = next((p for level, p in _PRIORITIES if record.levelno >= level), 7)
        return f"<{priority}>{super().format(record)}"


def setup_logging(level: str = "INFO") -> None:
    under_systemd = "JOURNAL_STREAM" in os.environ
    handler = logging.StreamHandler()
    if under_systemd:  # the journal adds timestamps itself
        handler.setFormatter(JournalFormatter("%(name)s: %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per Jellyfin request is too noisy
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
