# app/transcription/routes.py

import eventlet
eventlet.monkey_patch()

from flask import Flask, Blueprint, render_template, request, current_app, jsonify
# from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from threading import Lock
from app.config import Config
from app.transcription.transcription import TranscriptionSession
from app.models import db, Transcript, Summary, Meeting, ActionItem  # Ensure the Transcript model is imported
from flask_login import current_user

db.init_app  # using the same db instance from models.py
transcription_bp = Blueprint("transcription_bp", __name__, template_folder="templates")

#socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")
from app.extensions import socketio

# Global dictionary to track active transcription sessions.
ACTIVE_SESSIONS = {}
ACTIVE_SESSIONS_LOCK = Lock()



@transcription_bp.route("/<int:meeting_id>")
def transcription(meeting_id):
    # For demo: meeting_id=123 and user_id=999.
    # Query all transcripts for meeting 123 ordered by created timestamp and pass them to meeting.html
    meeting = meeting_id # Get the meeting Object.
    user_id = current_user.user_id
    
    
    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).order_by(Transcript.created_timestamp.asc()).all()
    summary = Summary.query.filter_by(meeting_id=meeting_id).order_by(Summary.created_timestamp.desc()).first()
    from app.models import ActionItem  # Import the ActionItem model here
    tasks = ActionItem.query.filter_by(meeting_id=meeting_id).order_by(ActionItem.created_timestamp.asc()).all()
    return render_template("transcription.html", meeting_id=meeting_id, user_id=user_id, transcripts=transcripts, summary=summary, tasks=tasks)



# ------------------------------------------------------------------
# Routes for updating & deleting transcripts
# ------------------------------------------------------------------

@transcription_bp.route("/transcript/<int:transcript_id>/update", methods=["POST"])
def update_transcript(transcript_id):
    """
    Receive JSON: { "processed_transcript": "...new text..." }
    Save it in Transcript.processed_transcript, leaving raw_transcript intact.
    """
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
    """
    Delete the transcript record from the database.
    """
    transcript = Transcript.query.get_or_404(transcript_id)
    db.session.delete(transcript)
    db.session.commit()

    return jsonify({
        "message": "Transcript deleted",
        "transcript_id": transcript_id
    })
    
    
    
@transcription_bp.route("/transcript/<int:transcript_id>/autocorrect", methods=["POST"])
def autocorrect_transcript(transcript_id):
    """
    Fetch the existing transcript from the DB,
    run it through the LLM for grammar/punctuation correction,
    then update processed_transcript.
    """
    transcript = Transcript.query.get_or_404(transcript_id)

    # Get the correct meeting_id from the transcript
    meeting_id = transcript.meeting_id  # ✅ Get the meeting_id dynamically
    # Ensure we are emitting to the correct room
    meeting_room = f"meeting_{meeting_id}"  # ✅ Correct room
    # Determine which field to correct. Often you'd correct the raw_transcript,
    # or if the user has previously edited it, you might use processed_transcript.
    text_to_correct = transcript.raw_transcript.strip()

    # Use your WatsonxLLM or whichever LLM you have configured.
    # For example:
    from langchain_ibm import WatsonxLLM
    from langchain_core.prompts import PromptTemplate
    from app.config import Config

    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_1,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        # Model parameters, etc.
        params={
            "decoding_method": "sample",
            "max_new_tokens": 1200,
            "temperature": 0.8,
            "top_k": 25,
            "top_p": 1,
        }
    )

    # Create a prompt that instructs the model to correct grammar/punctuation.
    # Emphasize minimal alteration to preserve the speaker’s meaning.
    template = """
    You are a professional editor. Your task is to correct the following text by fixing grammar and punctuation errors **without changing its original meaning or style**.

    Input text:
    {text}

    Output Format:
    - Only return the corrected text.
    - Do not provide explanations, steps, or any additional formatting.
    - Do not add any headings, lists, or markdown-style sections.
    - Do not say "Here is the final corrected text".

    Output:
    """

    prompt = PromptTemplate.from_template(template)
    llm_chain = prompt | watsonx_llm
    
    # Generate the corrected text
    corrected_text = llm_chain.stream({"text": text_to_correct})
    
    accumulator = ""
    for chunk in corrected_text:
        accumulator += chunk
        print(chunk)
        #socketio.emit("autocorrect_update", {"transcript_id": transcript_id, "chunk": chunk}, namespace="/transcription")
        socketio.emit("autocorrect_update", {"transcript_id": transcript_id, "chunk": chunk}, namespace="/transcription", room=meeting_room)
    
    print("Auto Correction complete")
    
    
    # After streaming save the full corrected text
    transcript.processed_transcript = accumulator.strip()
    db.session.commit()
    
    
    # Notify frontend that autocorrect is complete
    socketio.emit("autocorrect_complete", {"transcript_id": transcript_id, "processed_transcript": transcript.processed_transcript}, namespace="/transcription", room=meeting_room)


    #emit("autocorrect_complete", {"transcript_id": transcript_id, "processed_transcript": transcript.processed_transcript}, namespace="/transcription", room=request.)
    return jsonify({
        "transcript_id": transcript.transcript_id,
        "processed_transcript": transcript.processed_transcript
    })

@transcription_bp.route("/transcription/transcript/<int:transcript_id>/reset", methods=["POST"])
def reset_transcript(transcript_id):
    transcript = Transcript.query.get_or_404(transcript_id)
    # Clear the processed transcript so the raw transcript is used on display.
    transcript.processed_transcript = ''
    db.session.commit()

    return jsonify({
        "transcript_id": transcript.transcript_id,
        "raw_transcript": transcript.raw_transcript,
        "processed_transcript": transcript.processed_transcript
    })


import json  # Add at the top along with other imports

# In the create_app() function, after your existing transcript routes:

from app.models import ActionItem  # Import the new model

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

    # Get all transcripts for the meeting and aggregate the text.
    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    full_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript
        for t in transcripts
    ])
    
    # Use your LLM to extract tasks.
    from langchain_ibm import WatsonxLLM
    from langchain_core.prompts import PromptTemplate
    from app.config import Config

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

    # Delete existing action items for the meeting
    existing_tasks = ActionItem.query.filter_by(meeting_id=meeting_id).all()
    for task in existing_tasks:
        db.session.delete(task)
    db.session.commit()

    # Create new action items
    new_tasks = []
    for task_data in tasks:
        description = task_data.get("description", "").strip()
        if not description:
            continue  # Skip tasks with no description
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
    # Optionally update other fields if provided
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



##############################################################################
# Socket.IO Handlers for Transcription
##############################################################################

@socketio.on("connect", namespace="/transcription")
def handle_connect():
    meeting_id = request.args.get("meeting_id")
    if meeting_id:
        join_room(f"meeting_{meeting_id}")
        print(f"Client joined room meeting_{meeting_id}") # Ensure the client joins the correct room
        
@socketio.on("join", namespace="/transcription")
def handle_join(data):
    room = data.get("room")
    join_room(room)
    print(f"Client joined room {room}")  # Debugging log
    
@socketio.on("start_transcription", namespace="/transcription")
def handle_start_transcription(data):
    meeting_id = str(data.get("meeting_id"))
    user_id = data.get("user_id")
    if not meeting_id:
        emit("error_message", {"error": "No meeting_id provided."})
        return

    with ACTIVE_SESSIONS_LOCK:
        # If there's already an active session, stop it first so we can start fresh
        old_session = ACTIVE_SESSIONS.pop(meeting_id, None)
        if old_session:
            old_session.stop()

        session = TranscriptionSession(
            api_key=Config.WATSONX_API_KEY,
            stt_url=Config.WATSONX_STT_URL,  # must be your Watsonx STT endpoint
            meeting_id=meeting_id,
            user_id=user_id,
            app=current_app._get_current_object(),
            socketio_instance=socketio
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
        print("Received invalid audio chunk.")  # DEBUG
        return

    with ACTIVE_SESSIONS_LOCK:
        session = ACTIVE_SESSIONS.get(meeting_id)
    if not session:
        print("No active transcription session found for meeting:", meeting_id)  # DEBUG
        return

    import base64
    if "data:" in chunk_b64:
        chunk_b64 = chunk_b64.split(",")[1]
    audio_bytes = base64.b64decode(chunk_b64)
    print(f"Received audio chunk for meeting {meeting_id}: {len(audio_bytes)} bytes")  # DEBUG
    print(f"First bytes of received audio: {audio_bytes[:20]}")  # DEBUG

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

    # Read transcripts for this meeting.
    from models import Transcript
    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    full_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript 
        for t in transcripts
    ])
    
    print("Aggregated transcripts:", full_text) # DEBUG CODE, read transcript for meeting

    
    # Initialize WatsonxLLM from Langchain
    from langchain_ibm import WatsonxLLM
    # from config import Config  # Ensure Config is imported here
    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        # Model Parameters
        params=  {
            "decoding_method": "sample",
            "max_new_tokens": 1200,
            "min_new_tokens": 10,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
            }
    )
    
    # Create prompt template that expects a variable called text for the raw transcript
    from langchain_core.prompts import PromptTemplate
    template =  """
                Summarize the following meeting transcripts concisely and clearly:\n\n {text} \n\n
                
                Avoid using emotional language or sensationalist tone.
                Focus on conveying the main points and takeaways from the meeting.
                Capture and preserve the original flow and tone of the meeting.
                You should review your response and then output only the final text of your summary. 
                No explanation of how you did summarized the transcript, just output only the clean final text of the summary.
                The output should be concise, ideally between 100-300 words.
                """
    prompt = PromptTemplate.from_template(template)
    
    # Build the LLM chain.
    llm_chain = prompt | watsonx_llm
    
     # Call the chain's stream method with a dictionary.
    summary_text = "" # Initialize variable to store summary text to database
    summary_text = llm_chain.invoke({"text": full_text})
    
    

    emit("summary_update", {"summary_chunk": summary_text}, namespace="/transcription", room=f"meeting_{meeting_id}")
    # After streaming completes save summary to database
    with current_app.app_context():
        existing = Summary.query.filter_by(meeting_id=meeting_id).first()
        if existing:
            existing.summary_text = summary_text
        else:
            new_summary = Summary(meeting_id=meeting_id, summary_text=summary_text)
            db.session.add(new_summary)
        db.session.commit()
    emit("summary_complete", {"message": "Summary generation complete."}, namespace="/transcription", room=f"meeting_{meeting_id}")

