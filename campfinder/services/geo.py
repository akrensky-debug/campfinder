"""Geographic utilities: distance calculation and city geocoding."""

from __future__ import annotations

import math

from campfinder.seed.cities import parse_location_string


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Compute the great-circle distance between two (lat, lng) points in miles.
    Uses the Haversine formula.
    """
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_location(location_str: str) -> tuple[float, float] | None:
    """
    Convert a human-readable location string to (lat, lng).
    Supports 'City, ST' format using the built-in city lookup table.
    Returns None if the location cannot be resolved.
    """
    return parse_location_string(location_str)


def build_postgis_distance_filter(lat: float, lng: float, radius_miles: float) -> str:
    """
    Return the ST_DWithin predicate fragment for use in raw SQL queries.
    Distance is converted from miles to meters (PostGIS geography uses meters).
    """
    meters = radius_miles * 1609.344
    return (
        f"ST_DWithin(location, ST_MakePoint({lng}, {lat})::geography, {meters})"
    )


def postgis_distance_expr(lat: float, lng: float) -> str:
    """
    Return a SQL expression that computes the distance in meters from a fixed point.
    Divide the result by 1609.344 in the caller to get miles.
    """
    return f"ST_Distance(location, ST_MakePoint({lng}, {lat})::geography)"
