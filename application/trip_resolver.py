from __future__ import annotations

from domain.models import DateRange, TrackPoint, TrackResult, Trip
from domain.rules import filter_ignition_on, format_for_api, to_local_isoformat


class TripResolver:

    def __init__(
        self,
        fmtrack_client,
        require_ignition_on: bool = False,
    ):
        self.fmtrack_client = fmtrack_client
        self.require_ignition_on = require_ignition_on

    def _fetch_points(
        self,
        object_id: str,
        date_range: DateRange,
    ) -> list[TrackPoint]:

        points: list[TrackPoint] = []

        continuation_token = None

        while True:

            response = self.fmtrack_client.get_object_coordinates(
                object_id=object_id,
                from_datetime=format_for_api(date_range.start),
                to_datetime=format_for_api(date_range.end),
                continuation_token=continuation_token,
                limit=1000,
            )

            items = response.get("items") or []

            items = filter_ignition_on(
                items,
                self.require_ignition_on,
            )

            for item in items:

                position = item.get("position", {})

                points.append(
                    TrackPoint(
                        datetime=to_local_isoformat(
                            item["datetime"]
                        ),
                        latitude=position.get("latitude"),
                        longitude=position.get("longitude"),
                        speed=position.get("speed"),
                        ignition_status=item.get("ignition_status"),
                    )
                )

            continuation_token = response.get(
                "continuation_token"
            )

            if continuation_token is None:
                break

        return points

    def resolve(self, trip: Trip) -> TrackResult:

        try:

            points = self._fetch_points(
                object_id=trip.object_id,
                date_range=trip.date_range,
            )

            return TrackResult(
                trip=trip,
                points=points,
            )

        except Exception as ex:

            return TrackResult(
                trip=trip,
                points=[],
                error=str(ex),
            )
