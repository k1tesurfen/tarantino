"""The mini-PC as a Bluetooth LE remote for the projector.

A separate daemon (`tarantino-btremote`) presents a HID-over-GATT remote that the
projector pairs with like any accessory. It wakes the projector from standby with a
wake advert and sends keys, among them the projector's programmable shortcut key
(set to open Jellyfin). The web app talks to it over a Unix socket (`client.py`), so
redeploying the web app does not drop the projector's connection to the remote.
"""
