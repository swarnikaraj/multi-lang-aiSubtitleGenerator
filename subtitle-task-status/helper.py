import os
from datetime import timedelta
import logging
import subprocess
from google.cloud import storage
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
# Set the path to the binaries



SERVICE_ACCOUNT_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-key.json")


try:
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
except Exception as e:
    logger.error(f"Failed to load service account key: {e}")
    raise



storage_client = storage.Client(credentials=credentials)
speech_client = speech.SpeechClient(credentials=credentials)
translate_client = translate.Client(credentials=credentials)


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
def upload_to_gcs(bucket_name, source_file_path, destination_blob_name):
    """
    Uploads a file to Google Cloud Storage.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_path)
        logger.info(f"File uploaded to gs://{bucket_name}/{destination_blob_name}")
        return f"gs://{bucket_name}/{destination_blob_name}"
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        return None

def upload_subtitles_to_gcp(bucket_name,subtitles, destination_blob_name, credentials):
    """
    Uploads a file to Google Cloud Storage and returns a signed URL for temporary access.
    """
    try:
        
        blob = storage_client.bucket(BUCKET_NAME).blob(destination_blob_name)
        blob.upload_from_string(subtitles, content_type="text/vtt")

        logger.info(f"File uploaded to gs://{bucket_name}/{destination_blob_name}")

        # Generate a signed URL valid for 1 hour
        signed_url = blob.generate_signed_url(
            credentials=credentials,
            expiration=timedelta(hours=1),
            method="GET"
        )
        return signed_url
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        return None
    
def convert_audio_to_wav(input_path, output_path):
    """
    Converts audio to WAV format using FFmpeg.
    """
    try:
        command = [
            "ffmpeg",
            "-i", input_path,
            "-ar", "16000",  # Set sample rate to 16000 Hz
            "-ac", "1",      # Convert to mono
            "-vn",           # Disable video
            output_path
        ]
        logger.info(f"Running FFmpeg command: {' '.join(command)}")
        subprocess.run(command, check=True)
        logger.info(f"Converted audio to WAV: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e}")
        raise RuntimeError("FFmpeg conversion failed.")

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

