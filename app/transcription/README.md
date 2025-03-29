# Live transcription via Socket.IO, CRUD, Summarization and Task Extraction

Integration within a Flask App.

```sh
flask_project/
├── run.py
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models.py
│   ├── transcription/
│   │   └── routes.py
│   ├── templates/
│   │   └── transcription.html
│   └── static/
│       └── record-worklet.js
```

```py
# run.py

import eventlet
import eventlet.wsgi
from app import create_app, socketio
from flask_talisman import Talisman
from socketio import WSGIApp  # from python-socketio package

app = create_app()
# Apply Talisman to force HTTPS and set security headers
Talisman(app, content_security_policy=None)

# Optional middleware to inject 'flask.app' into the environ so Socket.IO handlers work properly
class FlaskAppEnvironMiddleware:
    def __init__(self, app):
        self.app = app
    def __call__(self, environ, start_response):
        environ['flask.app'] = app
        return self.app(environ, start_response)

# Wrap the Flask app with Socket.IO's WSGIApp
wsgi_app = WSGIApp(socketio.server, app)
wsgi_app = FlaskAppEnvironMiddleware(wsgi_app)

# Create a TCP listener on the desired port
listener = eventlet.listen(('0.0.0.0', 5001))
# Wrap the listener with SSL using your certificate and key
ssl_listener = eventlet.wrap_ssl(listener,
                                 certfile='cert.pem',
                                 keyfile='key.pem',
                                 server_side=True)

# Start the Eventlet WSGI server with the SSL-wrapped listener and our wrapped app
eventlet.wsgi.server(ssl_listener, wsgi_app)

```

```py
# app/__init__.py

from flask import Flask
from .extensions import db, socketio
from app.transcription.routes import transcription_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    
    app.register_blueprint(transcription_bp, url_prefix="/transcription")
    
    with app.app_context():
        db.create_all()
    
    return app

```

```py
# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change_me_in_env")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # IBM WatsonX
    WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY", "")
    WATSONX_URL = os.environ.get("WATSONX_URL", "")
    WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID", "")
    WATSONX_STT_URL = os.environ.get("WATSONX_STT_URL", "")

    WATSONX_MODEL_ID_1 = os.environ.get("WATSONX_MODEL_ID_1", "")
    WATSONX_MODEL_ID_2 = os.environ.get("WATSONX_MODEL_ID_2", "")
    WATSONX_MODEL_ID_3 = os.environ.get("WATSONX_MODEL_ID_3", "")

```

```py
# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_login import LoginManager

db = SQLAlchemy()
socketio = SocketIO()
login_manager = LoginManager()

```

```py
# app/models.py
from datetime import datetime
from flask_login import UserMixin
from .extensions import db

class Transcript(db.Model):
    __tablename__ = 'transcripts'
    transcript_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    raw_transcript = db.Column(db.Text, nullable=False)
    processed_transcript = db.Column(db.Text, default='')
    language = db.Column(db.String(10), default='en')
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Summary(db.Model):
    __tablename__ = 'summaries'
    summary_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    summary_text = db.Column(db.Text, nullable=False)
    summary_type = db.Column(db.String(20), default='detailed')
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ActionItem(db.Model):
    __tablename__ = 'action_items'
    action_item_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    assigned_to = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='pending')
    priority = db.Column(db.String(20), default='medium')
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(50), default='user')
    # Add this:
    profile_pic_url = db.Column(db.String(255), default='')
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    updated_timestamp = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_id(self):
        return str(self.user_id)

class Meeting(db.Model):
    __tablename__ = 'meetings'
    meeting_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    date_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Interval)
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    conference_active = db.Column(db.Boolean, default=False)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship("User", backref="organized_meetings")
    participants = db.relationship("Participant", backref="meeting", cascade="all, delete-orphan")

class Participant(db.Model):
    __tablename__ = 'participants'
    participant_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.meeting_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    role = db.Column(db.String(50), default='attendee')

    user = db.relationship("User", backref="participations")

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    message_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


```

```py
# app/transcription/routes.py

import json
import base64
import threading
import time
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
from flask_socketio import join_room, emit
from datetime import datetime
from passlib.hash import bcrypt
from werkzeug.utils import secure_filename
import os

from app.extensions import db, socketio
from app.config import Config
from app.models import (
    Meeting,
    Participant,
    Transcript,
    Summary,
    ActionItem
)


transcription_bp = Blueprint("transcription_bp", __name__, template_folder="templates")

# Global dictionary to store active transcription sessions and a lock for thread-safety.
ACTIVE_SESSIONS = {}
ACTIVE_SESSIONS_LOCK = threading.Lock()


# Dummy TranscriptionSession for testing purposes.
class TranscriptionSession:
    def __init__(self, api_key, stt_url, meeting_id, user_id, app, socketio_instance):
        self.api_key = api_key
        self.stt_url = stt_url
        self.meeting_id = meeting_id
        self.user_id = user_id
        self.app = app
        self.socketio = socketio_instance
        self.audio_chunks = []
        self.running = False

    def start(self):
        self.running = True
        print(f"Transcription session started for meeting {self.meeting_id}")

    def add_audio_chunk(self, chunk):
        if self.running:
            self.audio_chunks.append(chunk)
            # For testing, simulate processing and send a dummy transcript update.
            transcript = f"Received {len(chunk)} bytes of audio data."
            self.socketio.emit("transcript_update", {"transcript": transcript},
                                 room=f"meeting_{self.meeting_id}", namespace="/transcription")

    def stop(self):
        self.running = False
        print(f"Transcription session stopped for meeting {self.meeting_id}")


# -----------------------------------------------------------------------------
# Route to display a meeting's transcripts, summary, and action items.
# -----------------------------------------------------------------------------
@transcription_bp.route("/<int:meeting_id>")
@login_required
def transcription(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    part = Participant.query.filter_by(meeting_id=meeting_id, user_id=current_user.user_id).first()
    if not part:
        flash("You are not a participant of this meeting.", "danger")
        return redirect(url_for("meeting_bp.meeting_list"))

    transcripts = (
        Transcript.query.filter_by(meeting_id=meeting_id)
        .order_by(Transcript.created_timestamp.asc())
        .all()
    )
    summary = Summary.query.filter_by(meeting_id=meeting_id).order_by(Summary.created_timestamp.desc()).first()
    tasks = ActionItem.query.filter_by(meeting_id=meeting_id).order_by(ActionItem.created_timestamp.asc()).all()

    return render_template(
        "transcription.html",
        transcripts=transcripts,
        meeting_id=meeting_id,
        summary=summary,
        tasks=tasks,
        user_id=current_user.user_id  # Pass user_id for client-side use.
    )

# -----------------------------------------------------------------------------
# Transcript update & deletion routes.
# -----------------------------------------------------------------------------
@transcription_bp.route("/transcript/<int:transcript_id>/update", methods=["POST"])
def update_transcript(transcript_id):
    data = request.get_json() or {}
    new_text = data.get("processed_transcript", "").strip()
    transcript = Transcript.query.get_or_404(transcript_id)
    transcript.processed_transcript = new_text
    db.session.commit()
    return jsonify({
        "transcript_id": transcript.transcript_id,
        "processed_transcript": transcript.processed_transcript
    })

@transcription_bp.route("/transcript/<int:transcript_id>/delete", methods=["POST"])
def delete_transcript(transcript_id):
    transcript = Transcript.query.get_or_404(transcript_id)
    db.session.delete(transcript)
    db.session.commit()
    return jsonify({
        "message": "Transcript deleted",
        "transcript_id": transcript_id
    })

@transcription_bp.route("/transcript/<int:transcript_id>/autocorrect", methods=["POST"])
def autocorrect_transcript(transcript_id):
    transcript = Transcript.query.get_or_404(transcript_id)
    text_to_correct = transcript.raw_transcript.strip()

    # Replace the following with your actual WatsonxLLM implementation.
    from langchain_ibm import WatsonxLLM
    from langchain_core.prompts import PromptTemplate

    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_1,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 1200,
            "temperature": 0.8,
            "top_k": 25,
            "top_p": 1,
        }
    )

    template = """
    Correct grammar without changing original meaning of transcript to keep speakers style 

    Text to correct: 
    {text} 
    
    Output only the final corrected text.
    """
    prompt = PromptTemplate.from_template(template)
    llm_chain = prompt | watsonx_llm
    corrected_text = llm_chain.invoke({"text": text_to_correct})

    transcript.processed_transcript = corrected_text.strip()
    db.session.commit()
    return jsonify({
        "transcript_id": transcript.transcript_id,
        "processed_transcript": transcript.processed_transcript
    })

@transcription_bp.route("/transcript/<int:transcript_id>/reset", methods=["POST"])
def reset_transcript(transcript_id):
    transcript = Transcript.query.get_or_404(transcript_id)
    transcript.processed_transcript = ""
    db.session.commit()
    return jsonify({
        "transcript_id": transcript.transcript_id,
        "raw_transcript": transcript.raw_transcript,
        "processed_transcript": transcript.processed_transcript
    })

# -----------------------------------------------------------------------------
# Action Item Extraction and CRUD.
# -----------------------------------------------------------------------------
@transcription_bp.route("/extract_tasks", methods=["POST"])
def extract_tasks():
    data = request.get_json() or {}
    meeting_id_str = data.get("meeting_id")
    if not meeting_id_str:
        return jsonify({"error": "No meeting_id provided"}), 400

    try:
        meeting_id = int(meeting_id_str)
    except ValueError:
        return jsonify({"error": "Invalid meeting_id"}), 400

    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    full_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript
        for t in transcripts
    ])

    from langchain_ibm import WatsonxLLM
    from langchain_core.prompts import PromptTemplate

    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_2,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 800,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
        }
    )

    prompt_template = """
    Extract all action items and tasks from the following meeting transcript.
    Return the output as a JSON array of objects, each with the following keys:
    "description" (string, required),
    "assigned_to" (integer or null),
    "status" (string, default "pending"),
    "priority" (string, default "medium"),
    "start_date" (string in YYYY-MM-DD format or null),
    "due_date" (string in YYYY-MM-DD format or null).

    Transcript:
    {text}

    Output:
    """
    prompt = PromptTemplate.from_template(prompt_template)
    llm_chain = prompt | watsonx_llm
    result = llm_chain.invoke({"text": full_text})
    try:
        tasks = json.loads(result)
    except Exception as e:
        return jsonify({"error": "Failed to parse tasks JSON", "details": str(e), "raw_output": result}), 500

    existing_tasks = ActionItem.query.filter_by(meeting_id=meeting_id).all()
    for task in existing_tasks:
        db.session.delete(task)
    db.session.commit()

    new_tasks = []
    for task_data in tasks:
        description = task_data.get("description", "").strip()
        if not description:
            continue
        new_task = ActionItem(
            meeting_id=meeting_id,
            description=description,
            assigned_to=task_data.get("assigned_to"),
            status=task_data.get("status", "pending"),
            priority=task_data.get("priority", "medium"),
            start_date=task_data.get("start_date") if task_data.get("start_date") else None,
            due_date=task_data.get("due_date") if task_data.get("due_date") else None,
        )
        db.session.add(new_task)
        new_tasks.append(new_task)
    db.session.commit()

    tasks_list = [{
        "action_item_id": t.action_item_id,
        "description": t.description,
        "assigned_to": t.assigned_to,
        "status": t.status,
        "priority": t.priority,
        "start_date": t.start_date.isoformat() if t.start_date else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "created_timestamp": t.created_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    } for t in new_tasks]

    return jsonify({"tasks": tasks_list})

@transcription_bp.route("/action_item/<int:action_item_id>/update_status", methods=["POST"])
def update_task_status(action_item_id):
    data = request.get_json() or {}
    new_status = data.get("status")
    if new_status not in ["pending", "complete"]:
        return jsonify({"error": "Invalid status"}), 400
    task = ActionItem.query.get_or_404(action_item_id)
    task.status = new_status
    db.session.commit()
    return jsonify({
        "action_item_id": task.action_item_id,
        "status": task.status
    })

@transcription_bp.route("/action_item/<int:action_item_id>/update", methods=["POST"])
def update_task_details(action_item_id):
    data = request.get_json() or {}
    description = data.get("description", "").strip()
    if not description:
        return jsonify({"error": "Description is required"}), 400
    task = ActionItem.query.get_or_404(action_item_id)
    task.description = description
    task.assigned_to = data.get("assigned_to", task.assigned_to)
    task.priority = data.get("priority", task.priority)
    task.start_date = data.get("start_date", task.start_date)
    task.due_date = data.get("due_date", task.due_date)
    db.session.commit()
    return jsonify({
        "action_item_id": task.action_item_id,
        "description": task.description,
        "assigned_to": task.assigned_to,
        "priority": task.priority,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "due_date": task.due_date.isoformat() if task.due_date else None
    })

# -----------------------------------------------------------------------------
# Socket.IO Handlers for live transcription and summary generation.
# -----------------------------------------------------------------------------
@socketio.on("connect", namespace="/transcription")
def handle_connect():
    meeting_id = request.args.get("meeting_id")
    if meeting_id:
        join_room(f"meeting_{meeting_id}")
        print(f"Client joined room meeting_{meeting_id}")

@socketio.on("start_transcription", namespace="/transcription")
def handle_start_transcription(data):
    meeting_id = str(data.get("meeting_id"))
    user_id = data.get("user_id")
    if not meeting_id:
        emit("error_message", {"error": "No meeting_id provided."})
        return

    with ACTIVE_SESSIONS_LOCK:
        if meeting_id in ACTIVE_SESSIONS:
            emit("transcription_started", {"message": "Transcription already running."})
            return

        session = TranscriptionSession(
            api_key=Config.WATSONX_API_KEY,
            stt_url=Config.WATSONX_STT_URL,
            meeting_id=meeting_id,
            user_id=user_id,
            app=current_app._get_current_object(),
            socketio_instance=socketio,
        )
        session.start()
        ACTIVE_SESSIONS[meeting_id] = session

    join_room(f"meeting_{meeting_id}")
    emit("transcription_started", {"message": "Transcription started."}, room=f"meeting_{meeting_id}")

@socketio.on("audio_chunk", namespace="/transcription")
def handle_audio_chunk(data):
    meeting_id = str(data.get("meeting_id"))
    chunk_b64 = data.get("chunk")
    if not meeting_id or not chunk_b64:
        return
    with ACTIVE_SESSIONS_LOCK:
        session = ACTIVE_SESSIONS.get(meeting_id)
    if not session:
        return
    if "data:" in chunk_b64:
        chunk_b64 = chunk_b64.split(",")[1]
    audio_bytes = base64.b64decode(chunk_b64)
    session.add_audio_chunk(audio_bytes)

@socketio.on("stop_transcription", namespace="/transcription")
def handle_stop_transcription(data):
    meeting_id = str(data.get("meeting_id"))
    if not meeting_id:
        return
    with ACTIVE_SESSIONS_LOCK:
        session = ACTIVE_SESSIONS.pop(meeting_id, None)
    if session:
        session.stop()
        emit("transcription_stopped", {"message": "Transcription stopped."}, room=f"meeting_{meeting_id}")
    else:
        emit("transcription_stopped", {"message": "No active transcription found."}, room=f"meeting_{meeting_id}")

@socketio.on("generate_summary", namespace="/transcription")
def handle_generate_summary(data):
    meeting_id = data.get("meeting_id")
    if not meeting_id:
        emit("error_message", {"error": "No meeting_id provided for summary generation."})
        return

    from app.models import Transcript

    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    full_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript
        for t in transcripts
    ])

    print("Aggregated transcripts:", full_text)
    
    from langchain_ibm import WatsonxLLM
    from langchain_core.prompts import PromptTemplate

    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 1200,
            "min_new_tokens": 10,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
        },
    )

    template = """
                Summarize the following meeting transcripts concisely and clearly:
                
                {text}
                
                Avoid using emotional language or sensationalist tone.
                Focus on conveying the main points and takeaways from the meeting.
                Capture and preserve the original flow and tone.
                Output only the final summary text (100-300 words).
                """
    prompt = PromptTemplate.from_template(template)
    llm_chain = prompt | watsonx_llm

    summary_text = ""
    summary_chunks = llm_chain.stream({"text": full_text})
    for chunk in summary_chunks:
        time.sleep(0)  # simulate delay if needed
        summary_text += chunk
        emit("summary_update", {"summary_chunk": chunk}, namespace="/transcription", room=f"meeting_{meeting_id}")
    
    with current_app.app_context():
        existing = Summary.query.filter_by(meeting_id=meeting_id).first()
        if existing:
            existing.summary_text = summary_text
        else:
            new_summary = Summary(meeting_id=meeting_id, summary_text=summary_text)
            db.session.add(new_summary)
        db.session.commit()
    emit("summary_complete", {"message": "Summary generation complete."}, namespace="/transcription", room=f"meeting_{meeting_id}")



```

```html

<!-- 
    app/templates/transcription.html
 -->

<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <title>Transcription - Meeting {{ meeting_id }}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  </head>
  <body>
    <h1>Meeting {{ meeting_id }} Transcription</h1>

    <button id="startBtn">Start Transcription</button>
    <button id="stopBtn" disabled>Stop Transcription</button>
    <p id="status"></p>

    <!-- Live transcript display -->
    <div id="transcriptDiv" style="white-space: pre-wrap; border:1px solid #ccc; padding:10px; margin-top:10px;">
      Transcript appears here...
    </div>

    <h2>Transcripts</h2>
    <div id="transcriptListContainer" style="height:300px; overflow-y:auto; border:1px solid #ccc; padding:10px;">
      <ul id="savedTranscriptsList">
        {% for transcript in transcripts %}
          <li id="transcript-li-{{ transcript.transcript_id }}">
            <hr>
            <strong>{{ transcript.created_timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</strong>: 
            <br>
            <span id="transcript-text-{{ transcript.transcript_id }}">
              {% if transcript.processed_transcript %}
                {{ transcript.processed_transcript }}
              {% else %}
                {{ transcript.raw_transcript }}
              {% endif %}
            </span>
            <br>
            <button onclick="autoCorrectTranscript('{{ transcript.transcript_id }}')">Auto Correct</button>
            <button onclick="editTranscript('{{ transcript.transcript_id }}')">Edit</button>
            <button onclick="resetTranscript('{{ transcript.transcript_id }}')">Reset</button>
            <button onclick="deleteTranscript('{{ transcript.transcript_id }}')">Delete</button>
          </li>
        {% endfor %}
      </ul>
      {% if transcripts|length == 0 %}
        <p id="noTranscriptsMsg">No transcripts available for this meeting. Click "Start Transcription" to start capturing.</p>
      {% endif %}
    </div>

    <h2>Summary</h2>
    <button id="generateSummaryBtn">Generate Summary</button>
    <div id="summaryContainer" style="height:200px; overflow-y:auto; border:1px solid #ccc; padding:10px; margin-top:10px;">
      {% if summary %}
        <div id="summaryContent">{{ summary.summary_text | safe }}</div>
      {% else %}
        <p id="summaryPlaceholder">Summary will appear here...</p>
      {% endif %}
    </div>

    <h2>Action Items</h2>
    <button id="extractTasksBtn">Extract Tasks</button>
    <div id="taskContainer" style="height:200px; overflow-y:auto; border:1px solid #ccc; padding:10px; margin-top:10px;">
      {% if tasks %}
        {% for task in tasks %}
          <div id="task-{{ task.action_item_id }}" style="border-bottom: 1px solid #ccc; padding: 5px;">
            <input type="checkbox" onchange="updateTaskStatus('{{ task.action_item_id }}', this.checked ? 'complete' : 'pending')" {% if task.status == 'complete' %}checked{% endif %}>
            <span id="task-desc-{{ task.action_item_id }}" style="margin-left: 10px;">{{ task.description }}</span>
            <button onclick="editTask('{{ task.action_item_id }}')" style="margin-left: 10px;">Edit</button>
          </div>
        {% endfor %}
      {% else %}
        <p>No action items available for this meeting.</p>
      {% endif %}
    </div>

    <!-- Socket.IO Client -->
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    
    <script>
      const MEETING_ID = "{{ meeting_id }}";
      const USER_ID = "{{ user_id }}";

      let socket;
      let audioContext;
      let mediaStream;
      let recorderNode;

      const startBtn = document.getElementById("startBtn");
      const stopBtn = document.getElementById("stopBtn");
      const statusEl = document.getElementById("status");
      const transcriptDiv = document.getElementById("transcriptDiv");
      const savedTranscriptsList = document.getElementById("savedTranscriptsList");
      const transcriptListContainer = document.getElementById("transcriptListContainer");
      const generateSummaryBtn = document.getElementById("generateSummaryBtn");
      const summaryContainer = document.getElementById("summaryContainer");

      socket = io("/transcription", { query: "meeting_id=" + MEETING_ID });
      socket.on("connect", () => { console.log("Connected to /transcription"); });
      socket.on("transcription_started", data => { statusEl.textContent = data.message; });
      socket.on("transcription_stopped", data => { statusEl.textContent = data.message; });
      socket.on("transcript_update", data => { transcriptDiv.textContent = data.transcript; });
      socket.on("error_message", data => { alert(data.error); });

      socket.on("transcript_saved", data => {
        const noMsg = document.getElementById("noTranscriptsMsg");
        if (noMsg) { noMsg.remove(); }
        const li = document.createElement("li");
        li.id = "transcript-li-" + data.transcript_id;
        li.innerHTML = `<hr>
          <strong>${data.created_timestamp}</strong>: 
          <br>
          <span id="transcript-text-${data.transcript_id}">${data.raw_transcript}</span>
          <br>
          <button onclick="editTranscript('${data.transcript_id}')">Edit</button>
          <button onclick="deleteTranscript('${data.transcript_id}')">Delete</button>`;
        savedTranscriptsList.appendChild(li);
        transcriptListContainer.scrollTop = transcriptListContainer.scrollHeight;
      });

      // Summary logic
      let summaryAccumulated = "";
      generateSummaryBtn.addEventListener("click", () => {
        summaryAccumulated = "";
        summaryContainer.innerHTML = "";
        socket.emit("generate_summary", { meeting_id: MEETING_ID });
      });
      socket.on("summary_update", data => {
        summaryAccumulated += data.summary_chunk;
        const renderedHtml = marked.parse(summaryAccumulated);
        summaryContainer.innerHTML = renderedHtml;
        summaryContainer.scrollTop = summaryContainer.scrollHeight;
      });
      socket.on("summary_complete", data => { console.log(data.message); });

      async function startTranscription() {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        socket.emit("start_transcription", { meeting_id: MEETING_ID, user_id: USER_ID });
        //audioContext = new AudioContext({ sampleRate: 16000 });
        audioContext = new AudioContext();

        try {
          mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
          alert("Microphone permission denied or error: " + err);
          stopBtn.disabled = true;
          startBtn.disabled = false;
          return;
        }
        await audioContext.audioWorklet.addModule('/static/record-worklet.js');
        recorderNode = new AudioWorkletNode(audioContext, 'recorder-processor');
        recorderNode.port.onmessage = event => {
          const inputData = event.data;
          let buffer = new ArrayBuffer(inputData.length * 2);
          let view = new DataView(buffer);
          for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
          }
          const binary = String.fromCharCode(...new Uint8Array(buffer));
          const base64String = btoa(binary);
          socket.emit("audio_chunk", { meeting_id: MEETING_ID, chunk: base64String });
        };
        const micSource = audioContext.createMediaStreamSource(mediaStream);
        micSource.connect(recorderNode).connect(audioContext.destination);
      }

      function stopTranscription() {
        stopBtn.disabled = true;
        startBtn.disabled = false;
        socket.emit("stop_transcription", { meeting_id: MEETING_ID });
        if (recorderNode) recorderNode.disconnect();
        if (audioContext) audioContext.close();
        if (mediaStream) {
          mediaStream.getTracks().forEach(track => track.stop());
        }
        mediaStream = null;
        recorderNode = null;
        audioContext = null;
      }

      function editTranscript(transcriptId) {
        const textEl = document.getElementById(`transcript-text-${transcriptId}`);
        const oldText = textEl.textContent.trim();
        const newText = prompt("Edit transcript text:", oldText);
        if (!newText || newText === oldText) return;
        fetch(`/transcription/transcript/${transcriptId}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ processed_transcript: newText })
        })
        .then(r => r.json())
        .then(data => { textEl.textContent = data.processed_transcript; })
        .catch(err => console.error("Error updating transcript:", err));
      }

      function deleteTranscript(transcriptId) {
        if (!confirm("Are you sure you want to delete this transcript?")) return;
        fetch(`/transcription/transcript/${transcriptId}/delete`, { method: "POST" })
        .then(r => r.json())
        .then(data => { document.getElementById(`transcript-li-${transcriptId}`).remove(); })
        .catch(err => console.error("Error deleting transcript:", err));
      }

      function autoCorrectTranscript(transcriptId) {
        fetch(`/transcription/transcript/${transcriptId}/autocorrect`, { method: "POST" })
        .then(response => response.json())
        .then(data => {
          const textEl = document.getElementById(`transcript-text-${transcriptId}`);
          textEl.textContent = data.processed_transcript;
        })
        .catch(err => console.error("Error auto-correcting transcript:", err));
      }

      function resetTranscript(transcriptId) {
        fetch(`/transcription/transcript/${transcriptId}/reset`, { method: "POST" })
        .then(response => response.json())
        .then(data => {
          const textEl = document.getElementById(`transcript-text-${transcriptId}`);
          textEl.textContent = data.raw_transcript;
        })
        .catch(err => console.error("Error resetting transcript:", err));
      }

      function extractTasks() {
        fetch("/transcription/extract_tasks", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ meeting_id: MEETING_ID })
        })
        .then(response => response.json())
        .then(data => {
          if (data.error) { alert("Error extracting tasks: " + data.error); return; }
          displayTasks(data.tasks);
        })
        .catch(err => console.error("Error extracting tasks:", err));
      }

      function displayTasks(tasks) {
        const taskContainer = document.getElementById("taskContainer");
        taskContainer.innerHTML = "";
        tasks.forEach(task => {
          const div = document.createElement("div");
          div.id = "task-" + task.action_item_id;
          div.style.borderBottom = "1px solid #ccc";
          div.style.padding = "5px";
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.checked = (task.status === "complete");
          checkbox.addEventListener("change", function() {
            updateTaskStatus(task.action_item_id, this.checked ? "complete" : "pending");
          });
          div.appendChild(checkbox);
          const descSpan = document.createElement("span");
          descSpan.id = "task-desc-" + task.action_item_id;
          descSpan.style.marginLeft = "10px";
          descSpan.textContent = task.description;
          div.appendChild(descSpan);
          const editBtn = document.createElement("button");
          editBtn.textContent = "Edit";
          editBtn.style.marginLeft = "10px";
          editBtn.addEventListener("click", function() { editTask(task.action_item_id); });
          div.appendChild(editBtn);
          taskContainer.appendChild(div);
        });
      }

      function updateTaskStatus(taskId, newStatus) {
        fetch(`/transcription/action_item/${taskId}/update_status`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ status: newStatus })
        })
        .then(response => response.json())
        .then(data => { console.log("Task status updated", data); })
        .catch(err => console.error("Error updating task status:", err));
      }

      function editTask(taskId) {
        const descSpan = document.getElementById("task-desc-" + taskId);
        const currentDesc = descSpan.textContent;
        const newDesc = prompt("Edit task description:", currentDesc);
        if (!newDesc || newDesc === currentDesc) return;
        fetch(`/transcription/action_item/${taskId}/update`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ description: newDesc })
        })
        .then(response => response.json())
        .then(data => { descSpan.textContent = data.description; })
        .catch(err => console.error("Error updating task description:", err));
      }

      startBtn.addEventListener("click", startTranscription);
      stopBtn.addEventListener("click", stopTranscription);
      document.getElementById("extractTasksBtn").addEventListener("click", extractTasks);
      
      window.addEventListener("DOMContentLoaded", () => {
        const summaryContentEl = document.getElementById("summaryContent");
        if (summaryContentEl) {
          summaryContentEl.innerHTML = marked.parse(summaryContentEl.innerHTML);
        }
      });
    </script>
  </body>
</html>


```

```js
// app/static/record-worklet.js

class RecorderProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
    }
  
    process(inputs, outputs, parameters) {
      const input = inputs[0];
      if (input && input[0]) {
        // Send the raw audio samples from channel 0 to the main thread.
        this.port.postMessage(input[0]);
      }
      // Keep processor alive.
      return true;
    }
  }
  
  registerProcessor('recorder-processor', RecorderProcessor);
  




```
### Endpoints

**Meeting Transcription**
```
http://localhost:5001/trascription/<int:meeting_id> 
```


```sh
```





# Each Participant Streams Their Own Audio to STT
Find attached are all the codes that we are working on. I want you to rework the transcription system with Option A with some additional reworks such that When a participant joins, the start sending their mic feed directly to the transcription server.

# Example codes for each Participant Transcribes Locally

```js
/***********************************************
 * Example of each participant starting STT
 * *********************************************/

// In videoConference.js
async function joinConference() {
  localStream = await navigator.mediaDevices.getUserMedia(...);
  localVideo.srcObject = localStream;
  // ...
  // Then start local transcription for my mic:
  if (window.startLocalTranscription) {
    window.startLocalTranscription(); 
  }
}

```

```js
// In transcription.js
window.startLocalTranscription = async function() {
  // same code you have in startTranscription() 
  // but it only uses localStream.getAudioTracks().
};

```

When a participant joins, the start sending their mic feed directly to the transcription server on transcription_ws.py endpoint. (app/websockets/transcription_ws.py).

The server sorts the transcripts by time stamp.

Record all participants dialogs separately to the database, and then merge them into the transcript table.

Implement live streaming of transcription to the front end UI like this.

Profile Picture   Username(user_id=1) timestamp
                  Transcript text

Profile Picture   Username(user_id=3)  timestamp
                  Transcript text

Profile Picture   Username(user_id=2) timestamp
                  Transcript text

Profile Picture   Username(user_id=2) timestamp
                  Transcript text

Profile Picture   Username(user_id=1) timestamp
                  Transcript text


If the user is local user then Username = You

The Server Saves the following in the database table called dialogue

User
- user_id
- username

Participant
- participant_id
- meeting_id
- user_id
- role

Transcripts
- transcript_id
- meeting_id
- raw_transcript
- processed_transcript

Dialogue
- dialogue_id
- speaker_id
- transcript_id
- dialogue_text

STREAMING. 

So it has to stream so when a user starts to speak it create a new dialog box with the users name and text updates as it is generated by the STT service. If 3 users are speaking at the same time then we will have 3 dialogue boxes updating at the same time and it goes this way.


# RESET DATABASE TABLE

```py
from app import db
from app.models import Transcript

# Delete all rows from the Transcript table.
Transcript.query.delete()

# Commit the changes.
db.session.commit()

```

# REWORK TRANSCRIPTION FLOW

Each speaker is tagged with user_id and update single dialog element per speaker until they finish speaking.

