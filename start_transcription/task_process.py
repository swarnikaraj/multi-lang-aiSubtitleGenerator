import json
import os
import logging
import yt_dlp
from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
from helper import convert_audio_to_wav, upload_to_gcs
from pymongo import MongoClient
from google.cloud import speech_v1p1beta1 as speech
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to the service account key JSON file
SERVICE_ACCOUNT_KEY_FILE = "service-account-key.json"

# Initialize clients using the service account key
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
storage_client = storage.Client(credentials=credentials)
speech_client = speech.SpeechClient(credentials=credentials)
# Add the FFmpeg binary to the PATH environment variable
bin_path = os.path.abspath("bin")  # Path to the bin directory containing ffmpeg and ffprobe
os.environ["PATH"] += os.pathsep + bin_path


with open("config.json", "r") as config_file:
    config = json.load(config_file)

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", config["MONGO_URI"])
DB_NAME = os.getenv("DB_NAME", "tubeai")
COLLECTION_NAME = "SubtitledVideos"

# Initialize MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

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

# Custom logger for yt-dlp
class MyLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            logger.debug(msg)
        else:
            self.info(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)

def get_video_id(youtube_url):
    """Extract the video ID from a YouTube URL."""
    try:
        parsed_url = urlparse(youtube_url)
        domain = parsed_url.netloc.lower()
        if 'youtube.com' in domain or 'music.youtube.com' in domain:
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif 'youtu.be' in domain:
            return parsed_url.path[1:]
        else:
            logging.error("Invalid YouTube URL.")
            return None
    except Exception as e:
        logging.error(f"Error parsing URL: {e}")
        return None

def check_subtitle_exists(bucket_name, video_id,source_language,target_language):
    """
    Check if an audio file for the given video ID already exists in the GCS bucket.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob_name = f"subtitles/{video_id}_{source_language}_{target_language}.vtt"
        blob = bucket.blob(blob_name)

        if blob.exists():
            # Generate a signed URL valid for 1 hour
            signed_url = blob.generate_signed_url(
                credentials=credentials,
                expiration=timedelta(hours=1),
                method="GET"
            )
            return signed_url
        return None
    except Exception as e:
        logger.error(f"Error checking for existing audio: {e}")
        return None

def check_audio_exists(bucket_name, video_id,):
    """
    Check if an audio file for the given video ID already exists in the GCS bucket.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob_name = f"audio/{video_id}.wav"
        blob = bucket.blob(blob_name)

        
        if blob.exists():
            return f"gs://{bucket_name}/{blob_name}"
        return None
    except Exception as e:
        logger.error(f"Error checking for existing audio: {e}")
        return None



def process_youtube_audio(video_url, bucket_name,source_language,target_language,user_id,task_id):
    """
    Downloads YouTube audio, converts it to MP3 using FFmpeg, and uploads to GCS.
    """
    try:
        # Extract video ID
        video_id = get_video_id(video_url)
        if not video_id:
            return {"error": "Invalid YouTube URL."}

        # Check if audio already exists
        existing_signed_url = check_subtitle_exists(bucket_name, video_id,source_language,target_language)
        task_details = {
            "task_id": task_id,
            "video_url": video_url,
            "user_id": user_id,
            "source_language":source_language,
            "target_language":target_language,
            "url_type": 'youtube',
            "status": "succesful",  
            "downloadUrl":f"{existing_signed_url}",
            "created_at": datetime.now(),
        }
        if existing_signed_url:
            return {"message": "Audio already exists.", "task": task_details, "tokens_used":25}
        

        gcs_uri = check_audio_exists(bucket_name, video_id)

        # Temporary paths
        temp_video_path = f"/tmp/{video_id}.m4a"
        temp_audio_path = f"/tmp/{video_id}.wav"

        # yt-dlp options
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_video_path,
            "logger": MyLogger(),  # Custom logger for yt-dlp
        }
        
        if not gcs_uri:
            yt_dlp_download(video_url, ydl_opts)
            convert_audio_to_wav(temp_video_path, temp_audio_path)

            bucket_name = bucket_name
            destination_blob_name = f"audio/{video_id}.wav"
            gcs_uri = upload_to_gcs(bucket_name, temp_audio_path, destination_blob_name)


        if not gcs_uri:
            return {"error": "Failed to upload audio to GCS."}
        
        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=LANGUAGE_CODE_MAPPING.get(source_language, "en-US"),
            enable_automatic_punctuation=True,
        )
        operation = speech_client.long_running_recognize(config=config, audio=audio)
        operation_id = operation.operation.name

        logger.info(f"Generated async operation: {operation_id}")         
  
        task_details = {
            "task_id": task_id,
            "video_url": video_url,
            "user_id": user_id,
            "source_language":source_language,
            "target_language":target_language,
            "operation_id": operation_id,
            "status": "in_progress",
            "url_type": 'youtube',  
            "downloadUrl":"",
            "created_at": datetime.now(),
        }
        collection.insert_one(task_details)

        # Clean up temporary files
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        return {"message": "Subtitle generation processing", "task": task_details, "tokens_used":50}
       
    except Exception as e:
        logger.error(f"Error processing YouTube audio: {e}")
        return {"error": str(e)}

def yt_dlp_download(url: str, ydl_opts: dict):
    """
    Download media using yt-dlp and save it to a local file.
    """
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.error(f"Error in yt_dlp_download: {e}")
        raise

