import logging
import os
import functions_framework
import json
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

subscriber = pubsub_v1.SubscriberClient(credentials=credentials)


PROJECT_ID = credentials.project_id  
SUBSCRIPTION_NAME = "subtitle-status-sub"  
SUBSCRIPTION_PATH = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_NAME)

@functions_framework.http
def check_status(request):
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

        # Pull messages from the subscription
        response = subscriber.pull(
            request={
                "subscription": SUBSCRIPTION_PATH,
                "max_messages": 10,  # Adjust based on expected message volume
            }
        )

        task_status = None
        ack_ids = []

        # Search for the message with the matching task_id
        for message in response.received_messages:
            data = json.loads(message.message.data.decode("utf-8"))

            if data.get("task_id") == task_id:
                task_status = data.get("status")
                break

            ack_ids.append(message.ack_id)

        # Acknowledge all messages (even if the task_id wasn't found)
        if ack_ids:
            subscriber.acknowledge(
                request={
                    "subscription": SUBSCRIPTION_PATH,
                    "ack_ids": ack_ids,
                }
            )

        if not task_status:
            return json.dumps({"error": "Task not found"}), 404, headers

        return json.dumps({"task_id": task_id, "status": task_status}), 200, headers

    except Exception as e:
        return json.dumps({"error": str(e)}), 500, headers