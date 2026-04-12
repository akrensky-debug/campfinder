"""
Lookup table of Northeast US cities with lat/lng coordinates.
Covers the nine launch states: CT, MA, ME, NH, NJ, NY, PA, RI, VT.
Used for geocoding "City, ST" strings without an external API.
"""

from __future__ import annotations

# Maps (city_lower, state_upper) -> (lat, lng)
CITY_COORDS: dict[tuple[str, str], tuple[float, float]] = {
    # Rhode Island
    ("providence", "RI"): (41.8240, -71.4128),
    ("cranston", "RI"): (41.7798, -71.4373),
    ("warwick", "RI"): (41.7001, -71.4162),
    ("east greenwich", "RI"): (41.6601, -71.4601),
    ("barrington", "RI"): (41.7412, -71.3090),
    ("bristol", "RI"): (41.6771, -71.2673),
    ("newport", "RI"): (41.4901, -71.3128),
    ("pawtucket", "RI"): (41.8787, -71.3827),
    ("woonsocket", "RI"): (42.0026, -71.5148),
    ("north kingstown", "RI"): (41.5540, -71.4579),
    ("south kingstown", "RI"): (41.4510, -71.5301),
    ("westerly", "RI"): (41.3776, -71.8273),
    ("middletown", "RI"): (41.5137, -71.2924),
    # Massachusetts
    ("boston", "MA"): (42.3601, -71.0589),
    ("brookline", "MA"): (42.3318, -71.1212),
    ("newton", "MA"): (42.3370, -71.2092),
    ("cambridge", "MA"): (42.3736, -71.1097),
    ("wellesley", "MA"): (42.2968, -71.2923),
    ("needham", "MA"): (42.2834, -71.2334),
    ("concord", "MA"): (42.4604, -71.3489),
    ("lexington", "MA"): (42.4473, -71.2245),
    ("weston", "MA"): (42.3668, -71.3034),
    ("lincoln", "MA"): (42.4279, -71.3134),
    ("natick", "MA"): (42.2834, -71.3495),
    ("framingham", "MA"): (42.2793, -71.4162),
    ("worcester", "MA"): (42.2626, -71.8023),
    ("springfield", "MA"): (42.1015, -72.5898),
    ("northampton", "MA"): (42.3251, -72.6412),
    ("amherst", "MA"): (42.3732, -72.5199),
    ("gloucester", "MA"): (42.6159, -70.6620),
    ("salem", "MA"): (42.5195, -70.8967),
    ("plymouth", "MA"): (41.9584, -70.6673),
    ("quincy", "MA"): (42.2529, -71.0023),
    ("milton", "MA"): (42.2501, -71.0662),
    ("dedham", "MA"): (42.2418, -71.1662),
    ("norwood", "MA"): (42.1945, -71.1995),
    ("walpole", "MA"): (42.1501, -71.2495),
    ("sharon", "MA"): (42.1237, -71.1773),
    # Connecticut
    ("greenwich", "CT"): (41.0262, -73.6282),
    ("stamford", "CT"): (41.0534, -73.5387),
    ("new haven", "CT"): (41.3082, -72.9251),
    ("hartford", "CT"): (41.7658, -72.6851),
    ("westport", "CT"): (41.1415, -73.3579),
    ("darien", "CT"): (41.0776, -73.4690),
    ("new canaan", "CT"): (41.1468, -73.4951),
    ("wilton", "CT"): (41.1951, -73.4379),
    ("fairfield", "CT"): (41.1418, -73.2637),
    ("trumbull", "CT"): (41.2429, -73.2007),
    ("milford", "CT"): (41.2223, -73.0573),
    ("orange", "CT"): (41.2773, -73.0262),
    ("woodbridge", "CT"): (41.3537, -73.0048),
    ("hamden", "CT"): (41.3959, -72.8968),
    # New York
    ("white plains", "NY"): (41.0340, -73.7629),
    ("scarsdale", "NY"): (40.9898, -73.7846),
    ("rye", "NY"): (40.9809, -73.6829),
    ("great neck", "NY"): (40.8001, -73.7279),
    ("huntington", "NY"): (40.8679, -73.4262),
    ("manhasset", "NY"): (40.7984, -73.6990),
    ("new rochelle", "NY"): (40.9115, -73.7826),
    ("yonkers", "NY"): (40.9312, -73.8988),
    ("mount kisco", "NY"): (41.2023, -73.7237),
    ("chappaqua", "NY"): (41.1595, -73.7651),
    ("bedford", "NY"): (41.2023, -73.6468),
    ("armonk", "NY"): (41.1290, -73.7112),
    ("tarrytown", "NY"): (41.0762, -73.8579),
    ("bronxville", "NY"): (40.9376, -73.8340),
    ("pelham", "NY"): (40.9090, -73.8062),
    ("larchmont", "NY"): (40.9279, -73.7523),
    ("mamaroneck", "NY"): (40.9487, -73.7340),
    ("port washington", "NY"): (40.8276, -73.6990),
    ("garden city", "NY"): (40.7262, -73.6362),
    ("mineola", "NY"): (40.7490, -73.6423),
    ("oyster bay", "NY"): (40.8626, -73.5326),
    # New Jersey
    ("montclair", "NJ"): (40.8262, -74.2090),
    ("summit", "NJ"): (40.7162, -74.3651),
    ("morristown", "NJ"): (40.7968, -74.4812),
    ("ridgewood", "NJ"): (40.9790, -74.1173),
    ("short hills", "NJ"): (40.7412, -74.3262),
    ("chatham", "NJ"): (40.7423, -74.3840),
    ("madison", "NJ"): (40.7590, -74.4162),
    ("basking ridge", "NJ"): (40.7062, -74.5523),
    ("bernards", "NJ"): (40.6840, -74.5590),
    ("westfield", "NJ"): (40.6590, -74.3473),
    ("princeton", "NJ"): (40.3573, -74.6672),
    ("hoboken", "NJ"): (40.7440, -74.0324),
    # New Hampshire
    ("manchester", "NH"): (42.9956, -71.4548),
    ("nashua", "NH"): (42.7654, -71.4676),
    ("concord", "NH"): (43.2081, -71.5376),
    ("portsmouth", "NH"): (43.0718, -70.7626),
    ("exeter", "NH"): (42.9812, -70.9479),
    # Vermont
    ("burlington", "VT"): (44.4759, -73.2121),
    ("stowe", "VT"): (44.4651, -72.6868),
    ("manchester", "VT"): (43.1623, -73.0712),
    # Maine
    ("portland", "ME"): (43.6591, -70.2568),
    ("brunswick", "ME"): (43.9145, -69.9651),
    ("camden", "ME"): (44.2095, -69.0651),
    # Pennsylvania
    ("philadelphia", "PA"): (39.9526, -75.1652),
    ("pittsburgh", "PA"): (40.4406, -79.9959),
    ("wayne", "PA"): (40.0429, -75.3879),
    ("ardmore", "PA"): (40.0051, -75.2895),
    ("haverford", "PA"): (40.0062, -75.3101),
}


def geocode_city(city: str, state: str) -> tuple[float, float] | None:
    """
    Return (lat, lng) for a city/state pair, or None if not found.
    Case-insensitive on city; state should be two-letter upper-case.
    """
    key = (city.strip().lower(), state.strip().upper())
    return CITY_COORDS.get(key)


def parse_location_string(location: str) -> tuple[float, float] | None:
    """
    Parse a 'City, ST' string and return coordinates.
    Returns None if the city is not in the lookup table.
    """
    parts = location.strip().split(",")
    if len(parts) < 2:
        return None
    city = parts[0].strip()
    state = parts[1].strip().upper()[:2]
    return geocode_city(city, state)
