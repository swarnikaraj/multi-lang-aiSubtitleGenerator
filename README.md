# AI-Based Multi-Language Subtitle Generator

## Overview
This repository contains a scalable, production-ready Python-based AI subtitle generator leveraging Google Cloud Platform (GCP) tools. The application processes video/audio files to generate multi-language subtitles using GCP's Speech-to-Text (STT) model. It is designed for scalability and efficiency, employing asynchronous task processing and modern web technologies.

The system comprises two main components:
1. **Task Manager**: Handles task creation and adds tasks to a queue.
2. **Task Processor**: Processes queued tasks asynchronously to generate subtitles.

## Key Features
- **Multi-language Support**: Generate subtitles in various languages using GCP’s robust STT models.
- **Scalability**: Designed for high scalability using GCP Cloud Functions and Cloud Tasks.
- **Asynchronous Processing**: Efficiently manages task loads with Pub/Sub and task queues.
- **Web Frontend**: Built using Next.js for an intuitive user interface.
- **Production-Ready**: Suitable for deployment in real-world, high-load scenarios.

## Tech Stack
- **Backend**: Python, Google Cloud Functions, GCP Cloud Tasks, GCP Speech-to-Text
- **Frontend**: Next.js
- **Messaging**: GCP Pub/Sub
- **Libraries**: `pollib`, `google-cloud` SDKs

---

## Getting Started

### Prerequisites
1. **Google Cloud Platform (GCP)**:
   - A GCP project with billing enabled.
   - Access to the following GCP services:
     - Cloud Functions
     - Cloud Tasks
     - Pub/Sub
     - Speech-to-Text API
2. **Local Development Tools**:
   - Python 3.9+
   - Node.js (for Next.js frontend)
   - `gcloud` CLI installed and authenticated

### Setting up GCP Locally

1. **Enable Required APIs**:
   ```bash
   gcloud services enable \
     cloudfunctions.googleapis.com \
     pubsub.googleapis.com \
     cloudtasks.googleapis.com \
     speech.googleapis.com
   ```

2. **Create Required Resources**:
   - **Pub/Sub Topics**:
     ```bash
     gcloud pubsub topics create task-topic
     gcloud pubsub subscriptions create task-subscription --topic=task-topic
     ```
   - **Cloud Task Queue**:
     ```bash
     gcloud tasks queues create subtitle-queue
     ```

3. **Set Up IAM Roles**:
   Ensure the service account used for the Cloud Function has the following roles:
   - Pub/Sub Publisher and Subscriber
   - Cloud Tasks Enqueuer
   - Speech-to-Text API User

4. **Deploy Cloud Functions**:
   - Deploy the **Task Manager(task-creator)**:
     ```bash
     gcloud functions deploy task-manager \
       --runtime python39 \
       --trigger-http \
       --allow-unauthenticated
     ```
   - Deploy the **Task Processor(worker)**:
     ```bash
     gcloud functions deploy task-processor \
       --runtime python39 \
       --trigger-topic task-topic
     ```

---

### Local Setup

#### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ai-subtitle-generator.git
cd ai-subtitle-generator
```

#### 2. Backend Setup
1. Create a Python virtual environment:
   ```bash
   python3 -m venv env
   source env/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables (create a `.env` file):
   ```env
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account-key.json
   MONGO_URI=your mongo db uri
   ```
4. Add config.json file inside root of worker folder
{
  "GCS_BUCKET_NAME": "bucketname",
  "PUBSUB_TOPIC": "pubsub-topic"
}
#### 3. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

---

## Running the Project Locally

1. **Run the Backend**:
   Start the local Pub/Sub emulator and task queue emulator (if available), or use the GCP-managed instances.
   ```bash
   python task-creator/main.py  # Starts the task manager
   python worker/main.py  # Starts the task processor
   ```

2. **Run the Frontend**:
   Start the Next.js development server:
   ```bash
   npm run dev
   ```

3. Access the web application at `http://localhost:3000`.

---

## How It Works

1. **Task Creation**:
   - Users upload video/audio files via the web interface.
   - The Task Manager adds the processing request to a Cloud Task Queue.

2. **Asynchronous Processing**:
   - The Task Processor consumes tasks from the queue.
   - Each task invokes the Speech-to-Text API to generate subtitles in the specified language.

3. **Subtitle Delivery**:
   - Processed subtitles are stored in GCP Storage.
   - Users can download the generated subtitles via the web interface.

---

## Contributing
We welcome contributions! Please fork this repository and submit a pull request with your changes. For major updates, please open an issue first to discuss your proposed changes.

---

## License
This project is licensed under the MIT License. See the LICENSE file for details.

---

## Contact
For questions or collaboration opportunities, please reach out to [swarnikarajsingh@gmail.com](mailto:swarnikarajsingh@gmail.com) or connect via [LinkedIn](https://www.linkedin.com/in/swarnnika/).

---

## Demo
![Demo Screenshot](path/to/demo-image.png)

---

## Acknowledgments
- Google Cloud Platform for robust APIs and tools
- The open-source community for support and inspiration

