from client.fmtrack_client import FMTrackClient
from services.fixed_range_processor import FixedRangeProcessor
from services.pipeline_processor import PipelineProcessor

def main():

    client = FMTrackClient()

    try:

       pipeline = PipelineProcessor(client)
       
       pipeline.process(
           input_file="input/test.xlsx",
           output_file="output/test2.xlsx"
       )
       
    finally:

        client.close()


if __name__ == "__main__":
    main()