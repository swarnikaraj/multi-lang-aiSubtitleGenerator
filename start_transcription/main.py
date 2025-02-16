import json
import logging
import functions_framework  # Required for Google Cloud Functions
from task_process import process_youtube_audio
from task_process import db
from bson.objectid import ObjectId


# Configure logging
logging.basicConfig(level=logging.INFO)

@functions_framework.http
def start_transcription(request):
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
        
        task_id = request_json["task_id"]
        video_url = request_json["video_url"]
        user_id = request_json["user_id"]
        source_language = request_json("source_language", "en")  
        target_language = request_json["target_language"]  
        


        if not request_json or "video_url" not in request_json:
            return json.dumps({"error": "Invalid input. 'video_url' is required."}), 400, headers
        
        if not user_id:
            return json.dumps({"error": "Invalid input. 'user_id' is required."}), 401, headers

        
        user_object_id = ObjectId(user_id)
        query = {
            "_id": user_object_id,
            "issubscribed": True,
            "coins": {"$gt": 100}
        }
        user = db.users.find_one(query)

        if not user:
            return json.dumps({"error": "Unauthorized"}), 401, headers
        # Extract video URL
        video_url = request_json["video_url"]
        BUCKET_NAME = "tube_genius"  

        # Process the YouTube audio
        result = process_youtube_audio(video_url, BUCKET_NAME,source_language,target_language,user_id,task_id)

        db.users.update_one(
            {"_id": user_object_id},
            {"$inc": {"coins": -100}}  # Deduct 100 coins
        )

        # Return the response
        if "error" in result:
            return json.dumps(result), 400, headers

        return json.dumps(result), 200, headers

    except Exception as e:
        logging.error(f"Error in download_audio: {str(e)}")
        return json.dumps({"error": str(e)}), 500, headers
