import os
import logging
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from google.cloud import speech_v1
from google.cloud import storage, translate_v2 as translate
from google.cloud import translate_v2 as translate
import tempfile
from pymongo import MongoClient
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to the service account key JSON file
SERVICE_ACCOUNT_KEY_FILE = "service-account-key.json"

# Initialize clients using the service account key
try:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_KEY_FILE,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    speech_client = speech_v1.SpeechClient(credentials=credentials)
except Exception as e:
    logger.error(f"Error initializing clients: {e}")
    raise


with open("config.json", "r") as config_file:
    config = json.load(config_file)

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", config["MONGO_URI"])

DB_NAME = os.getenv("DB_NAME", "tubeai")
COLLECTION_NAME = "SubtitledVideos"



try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    collection = db[COLLECTION_NAME]
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    mongo_client = None

def process_transcription_results(response):
    """
    Process the transcription response to extract segments with start and end times.
    :param response: The response from the Speech-to-Text API.
    :return: A list of subtitle segments with start_time, end_time, and text.
    """
    transcript_segments = []
    try:
        for result in response.results:
            for alternative in result.alternatives:
                words = alternative.words
                if not words:
                    continue

                # Group words into segments based on timing
                segment = {
                    "start_time": words[0].start_time.total_seconds(),
                    "end_time": words[-1].end_time.total_seconds(),
                    "text": " ".join([word.word for word in words])
                }
                transcript_segments.append(segment)

        return transcript_segments
    except Exception as e:
        logger.error(f"Error processing transcription results: {e}")
        return []
def translate_segments(transcript_segments, source_language, target_language, credentials):
    """
    Translate transcript segments from source language to target language.
    """
    # If source and target languages are the same, no translation needed
    if source_language == target_language:
        logger.info("Source and target languages are the same. Skipping translation.")
        for segment in transcript_segments:
            segment["translated_text"] = segment["text"]
        return transcript_segments

    try:
        logger.info(f"Translating from {source_language} to {target_language}")
        translate_client = translate.Client(credentials=credentials)

        # Batch translate all segments at once for better efficiency
        texts_to_translate = [segment["text"] for segment in transcript_segments]
        translations = translate_client.translate(
            texts_to_translate,
            target_language=target_language,
            source_language=source_language
        )

        # Add translated text to segments
        for segment, translation in zip(transcript_segments, translations):
            segment["translated_text"] = translation["translatedText"]

        logger.info(f"Successfully translated {len(transcript_segments)} segments")
        return transcript_segments

    except Exception as e:
        logger.error(f"Translation failed: {str(e)}")
        # Fallback to original text if translation fails
        for segment in transcript_segments:
            segment["translated_text"] = segment["text"]
        return transcript_segments
    


def fetch_transcription_results(operation_id):
    """
    Fetch the transcription results for a given operation ID.
    :param operation_id: The operation ID of the long-running recognition task.
    :return: Processed transcript segments.
    """
    try:
        operation = speech_client.get_operation(name=operation_id)
        if not operation.done:
            logger.info("Transcription operation is still in progress.")
            return None

        response = speech_v1.LongRunningRecognizeResponse()
        response.ParseFromString(operation.response.value)

        # Process the transcription results
        transcript_segments = process_transcription_results(response)
        return transcript_segments
    except Exception as e:
        logger.error(f"Error fetching transcription results: {e}")
        return None
    
def process_video(BUCKET_NAME, task_id, operation_id, video_id, source_language, target_language):
    try:
        logger.info(f"Processing video with operation ID: {operation_id}")

        # Get operation status and result
        operation_result = get_operation_result(operation_id)

        if operation_result is None:
            return {
                "status": "error",
                "message": "Failed to get operation result"
            }

        logger.info(f"Operation result: {json.dumps(operation_result, indent=2)}")

        if not operation_result.get("done", False):
            return {
                "status": "in_progress",
                "message": "Transcription still in progress"
            }

        if "error" in operation_result:
            return {
                "status": "error",
                "message": str(operation_result["error"])
            }

        response = operation_result.get("response", {})
        results = response.get("results", [])

        if not results:
            return {
                "status": "error",
                "message": "No transcription results found"
            }

        # Process results into segments
        transcript_segments = []
        for result in results:
            if "transcript" not in result:
                continue

            words = result.get("words", [])
            if words:
                start_time = float(words[0]["start_time"])
                end_time = float(words[-1]["end_time"])
            else:
                start_time = 0
                end_time = 5

            segment = {
                "text": result["transcript"],
                "start_time": start_time,
                "end_time": end_time,
                "confidence": result.get("confidence", 0.0)
            }
            transcript_segments.append(segment)

        if not transcript_segments:
            return {
                "status": "error",
                "message": "Failed to process transcript segments"
            }

        # Translate if needed
        translated_segments = translate_segments(
            transcript_segments,
            source_language,
            target_language,
            credentials
        )
        print(transcript_segments,"i am transcript segment")
        # Generate VTT content
        vtt_content = generate_vtt_content(translated_segments)
        if not vtt_content:
            raise Exception("Failed to generate VTT content")

        # Save VTT file
        filename = f"subtitles/{video_id}_{source_language}_{target_language}.vtt"
        signed_url = save_vtt_file(vtt_content, filename, BUCKET_NAME,credentials)

        if not signed_url:
            return {
                "status": "error",
                "message": "Failed to upload subtitles"
            }
        collection.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "completed",
                    "downloadUrl": signed_url,
                    "completed_at": datetime.now()
                }
            }
        )
        return {
            "status": "completed",
            "message": "Subtitles generated successfully",
            "downloadUrl": signed_url
        }

    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": str(e)
        }




def generate_vtt_content(transcript_segments):
    """
    Generate VTT content from transcript segments with proper UTF-8 encoding.
    :param transcript_segments: List of subtitle segments with start_time, end_time, and text.
    :return: VTT content as a string.
    """
    try:
        vtt_content = "WEBVTT\n\n"

        for idx, segment in enumerate(transcript_segments, 1):
            start_time = format_time_vtt(segment["start_time"])
            end_time = format_time_vtt(segment["end_time"])
            # Use translated_text instead of text
            text = segment.get("translated_text", segment["text"])

            # Add the subtitle block
            vtt_content += f"{idx}\n"
            vtt_content += f"{start_time} --> {end_time}\n"
            vtt_content += f"{text}\n\n"

        return vtt_content
    except Exception as e:
        logger.error(f"Error generating VTT content: {e}")
        return None

def save_vtt_file(vtt_content, filename, bucket_name,credentials):
    """
    Save VTT content to a file in GCS with proper encoding.
    """
    try:
        # Create a temporary file with proper encoding
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as temp_file:
            temp_file.write(vtt_content)
            temp_file_path = temp_file.name

        # Upload the file to GCS with content type and encoding
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)

        # Upload with proper content type
        blob.upload_from_filename(
            temp_file_path,
            content_type='text/vtt; charset=utf-8'
        )

        # Clean up the temporary file
        os.unlink(temp_file_path)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET"
        )
        return signed_url

        
    except Exception as e:
        logger.error(f"Error saving VTT file: {str(e)}")
        return False

def format_time_vtt(seconds):
    """
    Format time in seconds to VTT timestamp format (HH:MM:SS.mmm).
    :param seconds: Time in seconds (float).
    :return: Formatted time string.
    """
    try:
        milliseconds = int((seconds % 1) * 1000)
        seconds = int(seconds)
        minutes = seconds // 60
        hours = minutes // 60
        seconds = seconds % 60
        minutes = minutes % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
    except Exception as e:
        logger.error(f"Error formatting time: {e}")
        return "00:00:00.000"


def upload_subtitles_to_gcp(bucket_name, content, destination_blob_name, credentials):
    """Upload subtitle content to GCS and return signed URL."""
    try:
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        # Upload content
        blob.upload_from_string(content, content_type='text/vtt')

        # Generate signed URL valid for 1 hour
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET"
        )
        return signed_url
    except Exception as e:
        logger.error(f"Error uploading subtitles: {e}")
        return None



def parse_binary_response(binary_response):
    """Parse the binary response to extract words"""
    try:
        # Convert binary response to string and split by \032 (which separates words)
        response_str = str(binary_response)
        parts = response_str.split('\\032')

        # Extract words (they appear after \032)
        words = []
        current_word = ""

        for part in parts:
            # Look for actual word content (usually appears after the last \)
            if part:
                segments = part.split('\\')
                if segments:
                    # Get the last segment which usually contains the word
                    potential_word = segments[-1]
                    # Clean up the word
                    if potential_word and potential_word.strip() and not potential_word.startswith('n') and not all(c.isdigit() or c in '\t\n' for c in potential_word):
                        # Remove any remaining control characters or numbers
                        cleaned_word = ''.join(c for c in potential_word if c.isalpha() or c in ' .,!?\'\"')
                        if cleaned_word:
                            current_word += " " + cleaned_word

        # Clean up the final transcript
        transcript = current_word.strip()

        return {
            "transcript": transcript,
            "confidence": 1.0  # Since we don't have confidence scores in this format
        }
    except Exception as e:
        logger.error(f"Error parsing binary response: {e}")
        return None

def test_operation_content(operation_id):
    """Test function to verify operation content"""
    try:
        logger.info(f"Testing operation: {operation_id}")
        operation = speech_client.transport.operations_client.get_operation(operation_id)

        if not operation:
            logger.error("Operation not found")
            return None

        logger.info(f"Operation done status: {operation.done}")

        if not operation.done:
            return {"status": "in_progress"}

        if not hasattr(operation, 'response') or not operation.response:
            logger.error("No response in operation")
            return None

        # Get the raw response
        raw_response = str(operation.response)
        logger.info("Raw response received")

        # Parse the binary response
        parsed_result = parse_binary_response(raw_response)

        if parsed_result:
            response_data = {
                "status": "completed",
                "results": [parsed_result]
            }

            # Print detailed information
            print("\nTranscription Results:")
            print(f"Transcript: {parsed_result['transcript']}")
            print(f"Confidence: {parsed_result['confidence']:.2f}")

            return response_data
        else:
            logger.error("Failed to parse response")
            return None

    except Exception as e:
        logger.error(f"Error testing operation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def get_operation_result(operation_id):
    """Get the result of a Speech-to-Text operation"""
    try:
        logger.info(f"Fetching operation: {operation_id}")
        operation = speech_client.transport.operations_client.get_operation(operation_id)

        if not operation:
            logger.error("Operation not found")
            return None

        if not operation.done:
            return {"done": False}

        if not hasattr(operation, 'response') or not operation.response:
            logger.error("No response in operation")
            return None

        # Parse the binary response
        parsed_result = parse_binary_response(str(operation.response))

        if parsed_result:
            return {
                "done": True,
                "response": {
                    "results": [parsed_result]
                }
            }
        else:
            return {
                "done": True,
                "error": "Failed to parse response"
            }

    except Exception as e:
        logger.error(f"Error getting operation result: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

if __name__ == "__main__":
    BUCKET_NAME = "tube_genius"
    task_id = "hihiikhk"
    operation_id = "491924632790785746"
    video_id = "aircAruvnKk"
    source_language = "en"
    target_language = "hi"

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("\nTesting Speech-to-Text Operation")
    print("================================")

    # Test the operation content first
    operation_content = test_operation_content(operation_id)

    if operation_content and operation_content.get("results"):
        print("\nOperation content found. Proceeding with processing...")

        # Process the video if operation content is valid
        result = process_video(
            BUCKET_NAME,
            task_id,
            operation_id,
            video_id,
            source_language,
            target_language
        )

        print("\nFinal Result:")
        print(json.dumps(result, indent=2))
    else:
        print("\nFailed to get operation content")
        exit(1)