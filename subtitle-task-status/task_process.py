import logging
import os

import json
from google.oauth2 import service_account
from pymongo import MongoClient
from google.cloud import speech_v1p1beta1 as speech
from helper import generate_subtitles, upload_subtitles_to_gcp
from google.protobuf import json_format
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to the service account key JSON file (use environment variable)
SERVICE_ACCOUNT_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-key.json")

# Initialize clients using the service account key
try:
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
except Exception as e:
    logger.error(f"Failed to load service account key: {e}")
    raise
speech_client = speech.SpeechClient(credentials=credentials)


# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "tubeai")
COLLECTION_NAME = "SubtitledVideos"

# Initialize MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]


def decode_protobuf_response(operation):
    try:
        # Check if the operation is done
        if not operation.done:
            return None

        # Get the response value (serialized protobuf)
        response_value = operation.response.value

        # Debug: Print the response value
        logger.info(f"Response value: {response_value}")

        # Decode the protobuf message
        response = speech.LongRunningRecognizeResponse()
        print(response,"response object")
        
        response.ParseFromString(response_value)  # Decode the serialized protobuf

        # Debug: Print the decoded response
        logger.info(f"Decoded response: {response}")

        return response

    except Exception as e:
        logger.error(f"Error decoding protobuf response: {e}")
        raise

def extract_transcript_with_timestamps(response):
    """
    Extracts transcript with sentence-level timestamps from the decoded response.
    """
    try:
        transcript_with_timestamps = []

        # Iterate through the results
        for result in response.results:
            for alternative in result.alternatives:
                transcript = alternative.transcript
                words = alternative.words

                if words:
                    # Group words into sentences
                    sentence_start_time = words[0].start_time.total_seconds()
                    sentence_end_time = words[-1].end_time.total_seconds()

                    transcript_with_timestamps.append({
                        "text": transcript,
                        "start_time": sentence_start_time,
                        "end_time": sentence_end_time,
                    })

        return transcript_with_timestamps

    except Exception as e:
        logger.error(f"Error extracting transcript: {e}")
        raise

def process_video(BUCKET_NAME,task_id,operation_id,video_id,source_language,target_language):
    """
    Cloud Function to check the status of a task from Pub/Sub.
    Handles CORS for cross-origin requests.
    """
    try:
            
             
        operation = speech_client.transport.operations_client.get_operation(operation_id)
        print("operation entered",operation)
        BUCKET_NAME = "tube_genius"
        if operation.done:
    # Deserialize the response value
            decode_protobuf_response(operation)
            response = decode_protobuf_response(operation)

            if not response:
                return {"error": "Failed to decode transcription response."}

            # Extract transcript with timestamps
            transcript_with_timestamps = extract_transcript_with_timestamps(response)

            if not transcript_with_timestamps:
                return {"error": "Failed to extract transcript."}
            
            # Print or process the transcript with timestamps
            print("Transcript with Timestamps:")
            for entry in transcript_with_timestamps:
                print(f"{entry['text']} (Start: {entry['start_time']}s, End: {entry['end_time']}s)")

            print("Subtitile genration in progress")
            # Generate subtitles
            subtitles = generate_subtitles(transcript_with_timestamps, target_language)
            print("Subtitile genration in completed", subtitles)

            # Upload subtitles to GCS
            destination_blob_name = f"subtitles/{task_id}.vtt"
            
            destination_blob_name = f"subtitles/{video_id}_{source_language}_{target_language}.vtt"
            signed_url = upload_subtitles_to_gcp(BUCKET_NAME, subtitles, destination_blob_name, credentials)

            if not signed_url:
                return {"error": "Failed to upload subtitles to GCS."}

            collection.update_one(
                {"task_id": task_id},
                {"$set": {"status": "completed", "downloadUrl": signed_url}}
            )

            return {"message": "Subtitles generated and uploaded.", "downloadUrl": signed_url}
       
    except Exception as e:
        return {"error": str(e)}
    