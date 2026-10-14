"""What the remote looks like to the projector: HID reports, keys and the wake advert."""

NAME = "Tarantino Remote"
APPEARANCE = 0x03C1  # keyboard, as the projector's own remote reports itself

REPORT_CONSUMER = 1
REPORT_PROGRAMMABLE = 2

REPORT_MAP = bytes([
    # Report 1: one 16-bit Consumer Control usage (array): media and navigation keys.
    0x05, 0x0C,        # Usage Page (Consumer)
    0x09, 0x01,        # Usage (Consumer Control)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID 1
    0x15, 0x00,        #   Logical Min 0
    0x26, 0xFF, 0x03,  #   Logical Max 0x3FF
    0x19, 0x00,        #   Usage Min 0
    0x2A, 0xFF, 0x03,  #   Usage Max 0x3FF
    0x75, 0x10,        #   Report Size 16
    0x95, 0x01,        #   Report Count 1
    0x81, 0x00,        #   Input (Data, Array, Abs)
    0xC0,              # End Collection
    # Report 2: four programmable buttons, one bit each. Linux maps them to
    # KEY_MACRO1..4 and Android to MACRO_1..4; MACRO_1 is the shortcut key whose app
    # is chosen in the projector's remote settings.
    0x05, 0x0C,        # Usage Page (Consumer)
    0x09, 0x01,        # Usage (Consumer Control)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID 2
    0x09, 0x03,        #   Usage (Programmable Buttons)
    0xA1, 0x04,        #   Collection (Named Array)
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Min 1
    0x29, 0x04,        #     Usage Max 4
    0x15, 0x00,        #     Logical Min 0
    0x25, 0x01,        #     Logical Max 1
    0x75, 0x01,        #     Report Size 1
    0x95, 0x04,        #     Report Count 4
    0x81, 0x02,        #     Input (Data, Var, Abs)
    0x95, 0x04,        #     Report Count 4
    0x81, 0x01,        #     Input (Const): padding
    0xC0,              #   End Collection
    0xC0,              # End Collection
])  # fmt: skip

CONSUMER_KEYS = {
    "power": 0x030, "menu": 0x040, "ok": 0x041, "up": 0x042, "down": 0x043, "left": 0x044,
    "right": 0x045, "playpause": 0x0CD, "mute": 0x0E2, "volup": 0x0E9, "voldown": 0x0EA,
    "home": 0x223, "back": 0x224,
}  # fmt: skip
PROGRAMMABLE_KEYS = {"star": 0x01}  # the shortcut key (MACRO_1)

KEYS = sorted([*CONSUMER_KEYS, *PROGRAMMABLE_KEYS])


def key_reports(name: str) -> tuple[int, bytes, bytes]:
    """(report id, press, release) for a key name; KeyError for unknown keys."""
    if name in PROGRAMMABLE_KEYS:
        return REPORT_PROGRAMMABLE, bytes([PROGRAMMABLE_KEYS[name]]), b"\x00"
    return REPORT_CONSUMER, CONSUMER_KEYS[name].to_bytes(2, "little"), b"\x00\x00"


# The projector's Bluetooth chip stays powered in standby and wakes the system when it
# sees an advert with this manufacturer data: a free byte, its own Bluetooth address
# (least significant byte first), padding and a fixed vendor signature. Any paired
# remote may send it; a plain reconnect advert does not wake the projector.
WAKE_COMPANY_ID = 0x0046
WAKE_SIGNATURE = bytes.fromhex("ffffff3043524b544d")


def wake_payload(projector_address: str) -> bytes:
    """Manufacturer data that wakes the projector with this Bluetooth address."""
    address = bytes.fromhex(projector_address.replace(":", ""))
    if len(address) != 6:
        raise ValueError(f"Not a Bluetooth address: {projector_address}")
    return b"\x00" + address[::-1] + WAKE_SIGNATURE
