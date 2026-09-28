"""
Geocoding for parent-entered locations.

Backed by the built-in New England city table for now. Replace
`geocode_location` with a real geocoder (with caching) when we open a region
the table does not cover; nothing else needs to change.
"""

from __future__ import annotations

import math

from campfinder.seed.cities import parse_location_string


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_location(location_str: str) -> tuple[float, float] | None:
    """'City, ST' to (lat, lng), or None when unknown."""
    return parse_location_string(location_str)
