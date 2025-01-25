import os
import subprocess
import logging
import yt_dlp
from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from helper import generate_subtitles, transcribe_audio, upload_subtitles_to_gcp
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to the service account key JSON file
SERVICE_ACCOUNT_KEY_FILE = "service-account-key.json"

# Initialize clients using the service account key
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_KEY_FILE)
storage_client = storage.Client(credentials=credentials)

# Add the FFmpeg binary to the PATH environment variable
bin_path = os.path.abspath("bin")  # Path to the bin directory containing ffmpeg and ffprobe
os.environ["PATH"] += os.pathsep + bin_path

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

def check_audio_exists(bucket_name, video_id):
    """
    Check if an audio file for the given video ID already exists in the GCS bucket.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob_name = f"subtitles/{video_id}.vtt"
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





def process_youtube_audio(video_url, bucket_name,source_language,target_language):
    """
    Downloads YouTube audio, converts it to MP3 using FFmpeg, and uploads to GCS.
    """
    try:
        # Extract video ID
        video_id = get_video_id(video_url)
        if not video_id:
            return {"error": "Invalid YouTube URL."}

        # Check if audio already exists
        existing_signed_url = check_audio_exists(bucket_name, video_id)
        if existing_signed_url:
            return {"message": "Audio already exists.", "signed_url": existing_signed_url, "tokens_used":25}

        # Temporary paths
        temp_video_path = f"/tmp/{video_id}.m4a"
        temp_audio_path = f"/tmp/{video_id}.mp3"

        # yt-dlp options
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_video_path,
            "logger": MyLogger(),  # Custom logger for yt-dlp
        }

        # Download YouTube audio using yt-dlp
        yt_dlp_download(video_url, ydl_opts)

        # Convert audio to MP3 using FFmpeg
        convert_audio_to_mp3(temp_video_path, temp_audio_path)

        logger.info(f"Transcribing audio for task_id: {video_id}")
        transcript_with_timestamps = transcribe_audio(temp_audio_path, source_language)


        logger.info(f"Generating subtitles for task_id: {video_id}")
        subtitles = generate_subtitles(transcript_with_timestamps, target_language)

        # Upload processed audio to GCS and get signed URL
        destination_blob_name = f"subtitles/{video_id}.vtt"
        signed_url = upload_subtitles_to_gcp(bucket_name, video_id,subtitles, destination_blob_name, credentials)

        # Clean up temporary files
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        if signed_url:
            return {"message": "Audio processing and upload successful.", "signed_url": signed_url, "tokens_used":50}
        else:
            return {"error": "Failed to upload audio to GCS."}
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

def convert_audio_to_mp3(input_path, output_path):
    """
    Converts audio to MP3 format using FFmpeg.
    """
    try:
        command = [
            "ffmpeg",
            "-i", str(input_path),  # Ensure string
            "-vn",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "192k",
            str(output_path)  # Ensure string
        ]
        logger.info(f"Running FFmpeg command: {' '.join(command)}")
        subprocess.run(command, check=True)
        logger.info(f"Converted audio to MP3: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e}")
        raise RuntimeError("FFmpeg conversion failed.")
