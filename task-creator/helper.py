import datetime
import re
import uuid
import os
import json
import logging
from google.cloud import tasks_v2
from google.cloud import storage
from google.cloud import pubsub_v1
from google.oauth2 import service_account

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

# Initialize GCP clients with the credentials
tasks_client = tasks_v2.CloudTasksClient(credentials=credentials)
storage_client = storage.Client(credentials=credentials)
publisher = pubsub_v1.PublisherClient(credentials=credentials)

# GCP Config (loaded from the service account key or environment variables)
PROJECT_ID = credentials.project_id  
LOCATION = os.getenv("GCP_LOCATION", "us-central1")  # Default to "us-central1" if not set
QUEUE_NAME = os.getenv("GCP_QUEUE_NAME", "subtitle-video-processing-queue")
BUCKET_NAME = os.getenv("GCP_BUCKET_NAME", "tube_genius")
PUBSUB_TOPIC = os.getenv("GCP_PUBSUB_TOPIC", "subtitle-status")
VIDEO_PROCESSING_FUNCTION_URL = os.getenv("VIDEO_PROCESSING_FUNCTION_URL")

# Validate required environment variables
if not VIDEO_PROCESSING_FUNCTION_URL:
    logger.error("VIDEO_PROCESSING_FUNCTION_URL environment variable is required")
    raise ValueError("VIDEO_PROCESSING_FUNCTION_URL environment variable is required")

# YouTube URL Validation
def is_youtube_url(url):
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+"
    return re.match(youtube_regex, url) is not None

# Upload Video to GCS
def upload_video_to_bucket(file):
    task_id = str(uuid.uuid4())
    blob = storage_client.bucket(BUCKET_NAME).blob(f"videos/{task_id}.mp4")
    blob.upload_from_file(file)
    return f"https://storage.googleapis.com/{BUCKET_NAME}/videos/{task_id}.mp4"

# Create GCP Task
def create_task(video_url, task_id, user_id, language, url_type):
    task = {
        "http_request": {
            "http_method": "POST",
            "url": VIDEO_PROCESSING_FUNCTION_URL,
            "headers": {
                "Content-Type": "application/json",  # Add this header
            },
            "body": json.dumps({
                "task_id": task_id,
                "video_url": video_url,
                "user_id": user_id,
                "language": language,
                "url_type": url_type,
            }).encode(),
        }
    }
    parent = tasks_client.queue_path(PROJECT_ID, LOCATION, QUEUE_NAME)
    tasks_client.create_task(parent=parent, task=task)

# Publish Status to Pub/Sub
def publish_status(task_id, status):
    topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
    data = json.dumps({"task_id": task_id, "status": status}).encode()
    publisher.publish(topic_path, data)