import logging
import os
import functions_framework
import json
from pymongo import MongoClient
from task_process import process_video
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "tubeai")
COLLECTION_NAME = "SubtitledVideos"

# Initialize MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]



@functions_framework.http
def subtitle_task_status(request):
    """
    Cloud Function to check the status of a task from Pub/Sub.
    Handles CORS for cross-origin requests.
    """
    try:
        # Set CORS headers
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json",
        }

        # Handle preflight OPTIONS request
        if request.method == "OPTIONS":
            return "", 204, headers

        # Parse JSON request
        request_json = request.get_json(silent=True)
        if not request_json or "task_id" not in request_json:
            return json.dumps({"error": "task_id is required"}), 400, headers
        
        

        task_id = request_json["task_id"]
        task = collection.find_one({"task_id": task_id})
        video_id = task.get("video_id")
        source_language = task.get("source_language")
        target_language = task.get("target_language")
       
        if not task:
            return {"error": "Task not found."}, 404, headers
        
        operation_id = task.get("operation_id")
        if not operation_id:
            return {"error": "Operation ID not found in task details."}, 400,headers
       
        BUCKET_NAME = "tube_genius"
        

        print("\nFinal Result:")
     
        result = process_video(BUCKET_NAME,task_id,operation_id,video_id,source_language,target_language)
        # Return the response
        if "error" in result:
            return json.dumps(result), 400, headers

        return json.dumps(result,indent=2), 200, headers

       
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, headers
    