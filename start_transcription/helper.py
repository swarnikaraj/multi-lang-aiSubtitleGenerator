import os
import logging
import subprocess
from google.cloud import storage
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()




SERVICE_ACCOUNT_KEY_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account-key.json")


try:
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
except Exception as e:
    logger.error(f"Failed to load service account key: {e}")
    raise



storage_client = storage.Client(credentials=credentials)


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







