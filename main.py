from client.fmtrack_client import FMTrackClient
from services.pipeline_processor import PipelineProcessor


def main():

    client = FMTrackClient()

    try:

        processor = PipelineProcessor(
            client
        )

        processor.process(
            input_file="output/partitions/part_01_2026-06-03_2026-06-15.xlsx",
            output_file="output/trackpoints_part_01.xlsx",
        )

    finally:

        client.close()


if __name__ == "__main__":
    main()