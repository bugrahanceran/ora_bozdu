import math

EARTH_RADIUS_METERS = 6_371_008.8


def distance_meters(
    *,
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    origin_latitude_radians = math.radians(origin_latitude)
    destination_latitude_radians = math.radians(destination_latitude)
    latitude_delta = destination_latitude_radians - origin_latitude_radians
    longitude_delta = math.radians(destination_longitude - origin_longitude)
    haversine = math.sin(latitude_delta / 2) ** 2 + (
        math.cos(origin_latitude_radians)
        * math.cos(destination_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(haversine)))


def offset_point(
    *, latitude: float, longitude: float, north_meters: float, east_meters: float
) -> tuple[float, float]:
    """Local tangent-plane approximation, accurate enough for city-scale grids."""
    latitude_radians = math.radians(latitude)
    new_latitude = latitude + math.degrees(north_meters / EARTH_RADIUS_METERS)
    parallel_radius = EARTH_RADIUS_METERS * math.cos(latitude_radians)
    new_longitude = longitude + math.degrees(east_meters / parallel_radius)
    return new_latitude, new_longitude
