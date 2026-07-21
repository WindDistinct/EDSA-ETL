from client.fmtrack_client import FMTrackClient


client = FMTrackClient()

coord = client.get_closest_coordinate(
    object_id="53625cee-2df2-11f1-833b-af5c1df1550e",
    datetime="2026-06-03T10:12:00Z"
)

print(coord)