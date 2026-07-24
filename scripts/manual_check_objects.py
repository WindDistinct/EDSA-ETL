"""Chequeo manual contra la API real de FM Track. No lo ejecuta pytest."""

from infrastructure.fmtrack_client import FMTrackClient


client = FMTrackClient()

objects = client.get_objects()

print(len(objects))

print(objects["A0P736"])
