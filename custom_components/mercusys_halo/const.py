"""Constants for the Mercusys Halo integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "mercusys_halo"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

DEFAULT_TIMEOUT = 30

# The router itself uses this token when the panel asks for the whole mesh,
# not for one Halo node.
MESH_DEVICE = "default"

PLATFORMS_LOADED = "platforms_loaded"
