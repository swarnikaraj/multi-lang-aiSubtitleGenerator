

import datetime
import uuid
import functions_framework
from helper import is_youtube_url, upload_video_to_bucket, publish_status, create_task
import json
import os
import logging
from pymongo import MongoClient

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "tubeai")
COLLECTION_NAME = "SubtitledVideos"

# Initialize MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@functions_framework.http
def generate_subtitle(request):
    """
    Cloud Function to download YouTube audio and upload it to GCS.
    Handles CORS for cross-origin requests.
    """
    try:
        # Set CORS headers
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json"
        }

        # Handle preflight OPTIONS request
        if request.method == "OPTIONS":
            return "", 204, headers

        # Parse JSON request
        request_json = request.get_json(silent=True)
        if not request_json or "video_url" not in request_json:
            return json.dumps({"error": "Invalid input. 'video_url' is required."}), 400, headers

        # Extract video URL
        video_url = request_json["video_url"]
        BUCKET_NAME = "tube_genius"  # Replace with your GCS bucket name

        youtube_url = request_json["youtube_url"]
        video_file = request_json["video_file"]
        user_id = request_json["user_id"]
        language = request_json["language"]

        if not youtube_url and not video_file:
            return json.dumps({"error": "Either YouTube URL or video file is required"}), 400, headers
        if not user_id:
            return json.dumps({"error": "Unauthenticated"}), 401, headers       
        if not language:
            return json.dumps({"error": "language is required"}), 400, headers   

        # Handle YouTube URL
        if youtube_url:
            if not is_youtube_url(youtube_url):
                return json.dumps({"error": "Invalid YouTube URL"}), 400, headers
            video_url = youtube_url
            url_type = "youtube"
        else:
            # Handle video file upload
            video_url = upload_video_to_bucket(video_file)
            url_type = "upload"

        task_id = str(uuid.uuid4())

        # Create GCP Task
        create_task(video_url, task_id, user_id, language, url_type)

        # Insert task details into MongoDB
        task_details = {
            "task_id": task_id,
            "video_url": video_url,
            "user_id": user_id,
            "language": language,
            "url_type": url_type,
            "status": "pending",  
            "downloadUrl":f"https://storage.googleapis.com/{BUCKET_NAME}/subtitles/{task_id}.vtt",
            "created_at": datetime.datetime.now(),
        }
        collection.insert_one(task_details)

        # Publish status as "pending"
        publish_status(task_id, "pending")

        return json.dumps({"task_id": task_id, "status": "pending"}), 200, headers

    except Exception as e:
        logger.error(f"Error in generate_subtitle: {str(e)}")
        return json.dumps({"error": str(e)}), 500, headers