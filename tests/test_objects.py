from client.fmtrack_client import FMTrackClient


client = FMTrackClient()

objects = client.get_objects()

print(len(objects))

print(objects["A0P736"])