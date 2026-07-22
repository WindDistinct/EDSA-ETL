from client.fmtrack_client import FMTrackClient
from services.fixed_range_processor import FixedRangeProcessor


def main():

    client = FMTrackClient()

    try:

        processor = FixedRangeProcessor(
            client
        )

        processor.process(
            input_file="input/Tramas_2026_07_06_2026_07_12.xlsx",
            output_file="output/Tramas_2026_07_06_2026_07_12.xlsx",
            start_date="2026-07-06T19:00:00Z",
            end_date="2026-07-13T03:43:00Z",
        )

    finally:

        client.close()


if __name__ == "__main__":
    main()