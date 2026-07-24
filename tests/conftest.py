from __future__ import annotations

from domain.models import Vehicle


class FakeFMTrackClient:
    """
    Doble de prueba de FMTrackClient. No hace red.

    coordinate_pages: dict[object_id, list[dict]] -- páginas devueltas en orden
    por cada llamada sucesiva a get_object_coordinates para ese object_id.
    """

    def __init__(
        self,
        objects: dict[str, Vehicle] | None = None,
        coordinate_pages: dict[str, list[dict]] | None = None,
        closest: dict[str, object] | None = None,
    ):
        self._objects = objects or {}
        self._coordinate_pages = coordinate_pages or {}
        self._closest = closest or {}
        self._call_index: dict[str, int] = {}

    def get_objects(self) -> dict[str, Vehicle]:
        return dict(self._objects)

    def get_object_coordinates(
        self,
        *,
        object_id: str,
        from_datetime: str,
        to_datetime: str,
        continuation_token: str | None = None,
        limit: int | None = None,
        include_geozones: bool | None = None,
        include_tire_parameters: bool = False,
    ) -> dict:

        pages = self._coordinate_pages.get(
            object_id,
            [{"items": [], "continuation_token": None}],
        )

        index = self._call_index.get(object_id, 0)

        page = pages[min(index, len(pages) - 1)]

        self._call_index[object_id] = index + 1

        return page

    def get_closest_coordinate(
        self,
        *,
        object_id: str,
        target_datetime: str,
        window_seconds: int = 30,
    ):
        return self._closest.get(object_id)
