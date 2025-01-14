

import logging

from functions_framework import http

from helper import extract_audio,download_video, generate_subtitles, transcribe_audio, update_task_status, upload_subtitles_to_gcp
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

@http
def process_video(request):
    """
    Cloud Function to process videos and generate subtitles.
    Supports multiple source and target languages.
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
        source_language = request_json.get("source_language", "en")  # Default to English
        target_language = request_json["target_language"]  
        url_type = request_json["url_type"]


        logger.info(f"Downloading video for task_id: {task_id}")
        video_path = download_video(video_url, url_type)


        logger.info(f"Extracting audio for task_id: {task_id}")
        audio_path = extract_audio(video_path)


        logger.info(f"Transcribing audio for task_id: {task_id}")
        transcript_with_timestamps = transcribe_audio(audio_path, source_language)


        logger.info(f"Generating subtitles for task_id: {task_id}")
        subtitles = generate_subtitles(transcript_with_timestamps, target_language)


        logger.info(f"Uploading subtitles for task_id: {task_id}")
        download_url = upload_subtitles_to_gcp(subtitles, task_id)

        logger.info(f"Updating task status for task_id: {task_id}")
        update_task_status(task_id, "completed", download_url)

        return "Video processing completed", 200, headers

    except Exception as e:
        logger.error(f"Error in process_video: {str(e)}")
        update_task_status(task_id, "failed")
        return f"Error: {str(e)}", 500, headers