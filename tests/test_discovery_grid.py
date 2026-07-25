import math

from app.discovery.geo import distance_meters, offset_point
from app.discovery.grid import build_grid, chunk_types

CENTER_LATITUDE = 39.979
CENTER_LONGITUDE = 32.636


def _sample_points(
    *, radius_meters: float, count: int = 24
) -> list[tuple[float, float]]:
    points = []
    for index in range(count):
        angle = 2 * math.pi * index / count
        # A mix of interior and near-boundary points.
        distance = radius_meters * (0.2 + 0.75 * (index % 4) / 3)
        latitude, longitude = offset_point(
            latitude=CENTER_LATITUDE,
            longitude=CENTER_LONGITUDE,
            north_meters=distance * math.cos(angle),
            east_meters=distance * math.sin(angle),
        )
        points.append((latitude, longitude))
    return points


def test_build_grid_covers_every_point_within_the_region_circle() -> None:
    region_radius_meters = 1000.0
    cell_radius_meters = 300.0
    cells = build_grid(
        center_latitude=CENTER_LATITUDE,
        center_longitude=CENTER_LONGITUDE,
        region_radius_meters=region_radius_meters,
        cell_radius_meters=cell_radius_meters,
    )

    for latitude, longitude in _sample_points(
        radius_meters=region_radius_meters * 0.95
    ):
        covered = any(
            distance_meters(
                origin_latitude=cell.center_latitude,
                origin_longitude=cell.center_longitude,
                destination_latitude=latitude,
                destination_longitude=longitude,
            )
            <= cell.radius_meters + 1e-6
            for cell in cells
        )
        assert covered, (latitude, longitude)


def test_build_grid_is_deterministic() -> None:
    kwargs = dict(
        center_latitude=CENTER_LATITUDE,
        center_longitude=CENTER_LONGITUDE,
        region_radius_meters=3000.0,
        cell_radius_meters=500.0,
    )

    first = build_grid(**kwargs)
    second = build_grid(**kwargs)

    assert first == second
    assert len({cell.cell_id for cell in first}) == len(first)


def test_build_grid_center_cell_sits_on_the_region_center() -> None:
    cells = build_grid(
        center_latitude=CENTER_LATITUDE,
        center_longitude=CENTER_LONGITUDE,
        region_radius_meters=3000.0,
        cell_radius_meters=500.0,
    )

    center_cell = next(cell for cell in cells if cell.cell_id == "r0c0")
    assert center_cell.center_latitude == CENTER_LATITUDE
    assert center_cell.center_longitude == CENTER_LONGITUDE


def test_chunk_types_respects_max_size() -> None:
    types = tuple(f"type_{index}" for index in range(120))

    batches = chunk_types(types, max_size=50)

    assert [len(batch) for batch in batches] == [50, 50, 20]
    assert tuple(item for batch in batches for item in batch) == types


def test_chunk_types_single_batch_when_under_the_limit() -> None:
    types = ("restaurant", "cafe")

    batches = chunk_types(types, max_size=50)

    assert batches == (("restaurant", "cafe"),)
