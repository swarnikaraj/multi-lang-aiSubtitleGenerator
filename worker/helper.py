import os
import subprocess

# Set the path to the binaries
FFMPEG_PATH = os.path.join(os.getcwd(), "bin", "ffmpeg")
YT_DLP_PATH = os.path.join(os.getcwd(), "bin", "yt-dlp")


import os
import json
import logging
import subprocess
from google.cloud import storage, pubsub_v1
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account
from helper import extract_audio,download_video
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

FFMPEG_PATH = os.path.join(os.getcwd(), "bin", "ffmpeg")
YT_DLP_PATH = os.path.join(os.getcwd(), "bin", "yt-dlp")

PROJECT_ID = credentials.project_id 
BUCKET_NAME = config["GCS_BUCKET_NAME"]
PUBSUB_TOPIC = config["PUBSUB_TOPIC"]

LANGUAGE_CODE_MAPPING = {
    "en": "en-US",  # English
    "hi": "hi-IN",  # Hindi
    "ta": "ta-IN",  # Tamil
    "te": "te-IN",  # Telugu
    "kn": "kn-IN",  # Kannada
    "ml": "ml-IN",  # Malayalam
    "bn": "bn-IN",  # Bengali
    "gu": "gu-IN",  # Gujarati
    "mr": "mr-IN",  # Marathi
    "pa": "pa-IN",  # Punjabi
    "ur": "ur-PK",  # Urdu (Pakistan)
    "es": "es-ES",  # Spanish
    "ar": "ar-SA",  # Arabic
    "pt": "pt-PT",  # Portuguese
    "ru": "ru-RU",  # Russian
    "ja": "ja-JP",  # Japanese
    "de": "de-DE",  # German
    "fr": "fr-FR",  # French
    "ko": "ko-KR",  # Korean
    "tr": "tr-TR",  # Turkish
}
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


def transcribe_audio(audio_path, source_language="en"):
    with open(audio_path, "rb") as audio_file:
        content = audio_file.read()

    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code=LANGUAGE_CODE_MAPPING.get(source_language, "en-US"),
        enable_automatic_punctuation=True,  # Add punctuation for sentence detection
    )

    response = speech_client.recognize(config=config, audio=audio)
    transcript_with_timestamps = []
    for result in response.results:
        for alternative in result.alternatives:
            transcript_with_timestamps.append({
                "text": alternative.transcript,
                "start_time": alternative.words[0].start_time.total_seconds(),  # Start time of the first word
                "end_time": alternative.words[-1].end_time.total_seconds(),  # End time of the last word
            })
    return transcript_with_timestamps


def translate_text(text, target_language):
    """
    Translate text using Google Translate API.
    """
    result = translate_client.translate(text, target_language=target_language)
    return result["translatedText"]

def generate_subtitles(transcript_with_timestamps, target_language):
    subtitles = "WEBVTT\n\n"
    for i, entry in enumerate(transcript_with_timestamps):
        start_time = format_time(entry["start_time"])
        end_time = format_time(entry["end_time"])
        text = entry["text"]
        if target_language != "en":
            text = translate_text(text, target_language)
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

def extract_audio(video_path):
    """
    Extract audio from video using ffmpeg.
    """
    audio_path = "/tmp/audio.wav"
    subprocess.run([FFMPEG_PATH, "-i", video_path, "-q:a", "0", "-map", "a", audio_path, "-y"], check=True)
    return audio_path

def download_video(video_url, url_type):
    """
    Download video from GCS or YouTube.
    """
    video_path = "/tmp/video.mp4"
    if url_type == "gcs":
        # Use gsutil directly (no need for a binary)
        subprocess.run(["gsutil", "cp", video_url, video_path], check=True)
    elif url_type == "youtube":
        # Use yt-dlp binary
        subprocess.run([YT_DLP_PATH, "-o", video_path, video_url], check=True)
    else:
        raise ValueError("Unsupported URL type")
    return video_path