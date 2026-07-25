import math
from dataclasses import dataclass

from app.discovery.geo import distance_meters, offset_point

NEARBY_SEARCH_MAX_INCLUDED_TYPES = 50


@dataclass(frozen=True, slots=True)
class GridCellSpec:
    cell_id: str
    center_latitude: float
    center_longitude: float
    radius_meters: float


def build_grid(
    *,
    center_latitude: float,
    center_longitude: float,
    region_radius_meters: float,
    cell_radius_meters: float,
) -> tuple[GridCellSpec, ...]:
    """Cover a region's search circle with a square grid of circumscribed circles.

    A square of side s = cell_radius_meters * sqrt(2) is fully covered by a
    circle of radius cell_radius_meters centered on it, and squares of side s
    tile the plane with no gaps -- so tiling the region with such squares and
    giving each one its circumscribed circle guarantees full coverage.
    """
    side = cell_radius_meters * math.sqrt(2)
    half_diagonal = side * math.sqrt(2) / 2
    steps = math.ceil(region_radius_meters / side - 0.5)
    prune_distance = region_radius_meters + half_diagonal

    cells = []
    for row in range(-steps, steps + 1):
        for col in range(-steps, steps + 1):
            cell_latitude, cell_longitude = offset_point(
                latitude=center_latitude,
                longitude=center_longitude,
                north_meters=row * side,
                east_meters=col * side,
            )
            if (
                distance_meters(
                    origin_latitude=center_latitude,
                    origin_longitude=center_longitude,
                    destination_latitude=cell_latitude,
                    destination_longitude=cell_longitude,
                )
                > prune_distance
            ):
                continue
            cells.append(
                GridCellSpec(
                    cell_id=f"r{row}c{col}",
                    center_latitude=cell_latitude,
                    center_longitude=cell_longitude,
                    radius_meters=cell_radius_meters,
                )
            )
    return tuple(cells)


def chunk_types(
    included_types: tuple[str, ...],
    *,
    max_size: int = NEARBY_SEARCH_MAX_INCLUDED_TYPES,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(included_types[index : index + max_size])
        for index in range(0, len(included_types), max_size)
    )
