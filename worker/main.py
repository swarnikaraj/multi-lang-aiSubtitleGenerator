
import os
import json
import logging
import subprocess
from google.cloud import storage, pubsub_v1
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import translate_v2 as translate
from functions_framework import http
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


with open("config.json", "r") as config_file:
    config = json.load(config_file)

CONSTANTS="constant.json"

SERVICE_ACCOUNT_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-key.json")


try:
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
except Exception as e:
    logger.error(f"Failed to load service account key: {e}")
    raise



storage_client = storage.Client(credentials=credentials)
publisher = pubsub_v1.PublisherClient(credentials=credentials)
speech_client = speech.SpeechClient(credentials=credentials)
translate_client = translate.Client(credentials=credentials)


PROJECT_ID = credentials.project_id 
BUCKET_NAME = config["GCS_BUCKET_NAME"]
PUBSUB_TOPIC = config["PUBSUB_TOPIC"]

def upload_subtitles_to_gcp(subtitles, task_id):
    """
    Upload subtitles to GCS and return the download URL.
    """
    blob = storage_client.bucket(BUCKET_NAME).blob(f"subtitles/{task_id}.vtt")
    blob.upload_from_string(subtitles, content_type="text/vtt")
    return f"https://storage.googleapis.com/{BUCKET_NAME}/subtitles/{task_id}.vtt"

def update_task_status(task_id, status, download_url=None):
    """
    Update the task status publish to Pub/Sub.
    """
    topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
    data = json.dumps({"task_id": task_id, "status": status, "download_url": download_url}).encode()
    publisher.publish(topic_path, data)

def download_video(video_url, url_type):
    """
    Download video from GCS or YouTube.
    """
    video_path = "/tmp/video.mp4"
    if url_type == "gcs":
        subprocess.run(["gsutil", "cp", video_url, video_path], check=True)
    elif url_type == "youtube":
        subprocess.run(["yt-dlp", "-o", video_path, video_url], check=True)
    else:
        raise ValueError("Unsupported URL type")
    return video_path

def extract_audio(video_path):
    """
    Extract audio from video.
    """
    audio_path = "/tmp/audio.wav"
    subprocess.run(["ffmpeg", "-i", video_path, "-q:a", "0", "-map", "a", audio_path, "-y"], check=True)
    return audio_path

def transcribe_audio(audio_path):
    """
    Transcribe audio using Google Speech-to-Text API and return transcript with timestamps.
    """
    with open(audio_path, "rb") as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
        enable_word_time_offsets=True,  # Enable timestamps for each word
    )

    response = speech_client.recognize(config=config, audio=audio)
    transcript_with_timestamps = []
    for result in response.results:
        for alternative in result.alternatives:
            for word_info in alternative.words:
                word = word_info.word
                start_time = word_info.start_time.total_seconds()
                end_time = word_info.end_time.total_seconds()
                transcript_with_timestamps.append({
                    "word": word,
                    "start_time": start_time,
                    "end_time": end_time,
                })
    return transcript_with_timestamps

def translate_text(text, target_language):
    """
    Translate text using Google Translate API.
    """
    result = translate_client.translate(text, target_language=target_language)
    return result["translatedText"]

def generate_subtitles(transcript_with_timestamps, language):
    """
    Generate subtitles in VTT format with synchronization.
    """
    subtitles = "WEBVTT\n\n"
    for i, entry in enumerate(transcript_with_timestamps):
        start_time = format_time(entry["start_time"])
        end_time = format_time(entry["end_time"])
        text = entry["word"]
        if language != "en":
            text = translate_text(text, language)
        subtitles += f"{i + 1}\n{start_time} --> {end_time}\n{text}\n\n"
    return subtitles

def format_time(seconds):
    """
    Convert seconds to WebVTT time format (HH:MM:SS.mmm).
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:06.3f}"

@http
def process_video(request):
    """
    Cloud Function to process videos and generate subtitles.
    """
    headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json"
        }
    try:
        # Parse the request
        request_json = request.get_json()
        task_id = request_json["task_id"]
        video_url = request_json["video_url"]
        user_id = request_json["user_id"]
        language = request_json["language"]
        url_type = request_json["url_type"]

        # Step 1: Download the video
        logger.info(f"Downloading video for task_id: {task_id}")
        video_path = download_video(video_url, url_type)

        # Step 2: Extract audio
        logger.info(f"Extracting audio for task_id: {task_id}")
        audio_path = extract_audio(video_path)

        # Step 3: Transcribe audio with timestamps
        logger.info(f"Transcribing audio for task_id: {task_id}")
        transcript_with_timestamps = transcribe_audio(audio_path)

        # Step 4: Generate subtitles (VTT format) with synchronization
        logger.info(f"Generating subtitles for task_id: {task_id}")
        subtitles = generate_subtitles(transcript_with_timestamps, language)

        # Step 5: Upload subtitles to GCS
        logger.info(f"Uploading subtitles for task_id: {task_id}")
        download_url = upload_subtitles_to_gcp(subtitles, task_id)

        # Step 6: Update task status
        logger.info(f"Updating task status for task_id: {task_id}")
        update_task_status(task_id, "completed", download_url)

        return "Video processing completed", 200,headers

    except Exception as e:
        logger.error(f"Error in process_video: {str(e)}")
        update_task_status(task_id, "failed")
        return f"Error: {str(e)}", 500,headers