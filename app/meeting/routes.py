# app/meeting/routes.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, current_app
    )

from flask_login import login_required, current_user
from datetime import datetime, timedelta
from passlib.hash import bcrypt
from werkzeug.utils import secure_filename
import os
import base64
import json

# Import your own modules as needed:
from app.extensions import db, socketio
from app.config import Config
from app.models import (
    Meeting, Participant, Transcript, Summary, ActionItem,
    User, ChatMessage
    )

from app.transcription.transcription import TranscriptionSession  # if you keep Watson STT in a separate module
from sqlalchemy import desc  # Add this import
meeting_bp = Blueprint("meeting_bp", __name__, template_folder="templates")

# Allowed file types
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "docx", "xlsx", "pptx", "txt", "zip"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

##############################################################################
# MEETING CRUD
##############################################################################
@meeting_bp.route("/")
@login_required
def meeting_list():
    """
    Display a list of meetings where the current_user is either organizer
    or a participant, sorted by most recent first.
    """
    user_id = current_user.user_id
    organized = Meeting.query.filter_by(organizer_id=user_id).order_by(Meeting.date_time.desc()).all()
    participation = Participant.query.filter_by(user_id=user_id).all()

    participant_meetings = [p.meeting for p in participation if p.meeting.organizer_id != user_id]
    participant_meetings.sort(key=lambda m: m.date_time, reverse=True)  # Sort participant meetings in descending order

    # Suppose you fetch a meeting or default to None
    meeting = Meeting.query.first()
    return render_template(
        "meeting_list.html", 
        organized=organized, 
        participant_meetings=participant_meetings,
        datetime=datetime,  # Pass datetime to the template
        timedelta=timedelta,
        meeting=meeting
    )

@meeting_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_meeting():
    """
    Create a new Meeting. The current_user becomes the organizer.
    """
    # We add org selection logic:
    user_orgs = [m.organization for m in current_user.org_memberships if m.status == "active"]
    
    
    if request.method == "POST":
        org_id = request.form.get("org_id", type=int)
        # Ensure user is in that org
        if org_id not in [o.org_id for o in user_orgs]:
            flash("Invalid organization selection.", "danger")
            return redirect(url_for("meeting_bp.new_meeting"))       
        
        
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        date_time_str = request.form.get("date_time", "").strip()
        duration_str = request.form.get("duration", "").strip()  # in minutes

        if not title or not date_time_str:
            flash("Title and Date/Time are required.", "danger")
            return redirect(url_for("meeting_bp.new_meeting"))

        try:
            dt = datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date/time format. Use YYYY-MM-DDTHH:MM.", "danger")
            return redirect(url_for("meeting_bp.new_meeting"))

        duration = None
        if duration_str:
            try:
                minutes = int(duration_str)
                duration = timedelta(minutes=minutes)
            except ValueError:
                flash("Invalid duration format.", "danger")
                return redirect(url_for("meeting_bp.new_meeting"))

        meeting = Meeting(
            title=title,
            description=description,
            date_time=dt,
            duration=duration,
            organizer_id=current_user.user_id,
            org_id=org_id # Associate the new meeting with the chosen org
        )
        db.session.add(meeting)
        db.session.commit()

        # Automatically create a Participant record for the organizer
        participant = Participant(
            meeting_id=meeting.meeting_id,
            user_id=current_user.user_id,
            role="organizer"
        )
        db.session.add(participant)
        db.session.commit()

        flash("Meeting created successfully.", "success")
        return redirect(url_for("meeting_bp.meeting_list"))

    return render_template("meeting_form.html", now=datetime.utcnow(), user_orgs=user_orgs)

@meeting_bp.route("/<int:meeting_id>")
@login_required
def meeting_details(meeting_id):
    """
    View details of a single meeting. Must be a participant to access.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    part = Participant.query.filter_by(meeting_id=meeting_id, user_id=current_user.user_id).first()
    if not part:
        flash("You are not a participant of this meeting.", "danger")
        return redirect(url_for("meeting_bp.meeting_list"))

    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).order_by(Transcript.created_timestamp.asc()).all()
    #summary = Summary.query.filter_by(meeting_id=meeting_id, summary_type='detailed').order_by(Summary.created_timestamp.desc()).first()

    tasks = ActionItem.query.filter_by(meeting_id=meeting_id).order_by(ActionItem.created_timestamp.asc()).all()
    participants = Participant.query.filter_by(meeting_id=meeting_id).all()

    # Fetch chat messages with user profile pictures
    chat_messages = (
        db.session.query(ChatMessage, User.profile_pic_url)
        .join(User, ChatMessage.user_id == User.user_id)
        .filter(ChatMessage.meeting_id == meeting_id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    
    # Convert chat messages into a structured list
    chat_messages_data = [
        {
            "username": msg.username,
            "message": msg.message,
            "timestamp": msg.timestamp,
            "profile_pic_url": f"/static/{profile_pic}" if profile_pic else "/static/default-profile.png",
        }
        for msg, profile_pic in chat_messages
    ]
    
    
    # Retrieve the latest 'agenda' summary from the DB
    agenda_summary = Summary.query.filter_by(
        meeting_id=meeting_id, 
        summary_type="agenda"
        ).order_by(Summary.created_timestamp.desc()).first()
    
    # Parse the stored JSON from the summary_text if available
    agenda_data = None
    if agenda_summary:
        try:
            agenda_data = json.loads(agenda_summary.summary_text)
        except Exception as e:
            current_app.logger.error("Failed to parse agenda summary JSON: %s", e)
            agenda_data = None
    
    
    
    return render_template(
        "meeting_details.html",
        meeting=meeting,
        transcripts=transcripts,
       # summary=summary,
        tasks=tasks,
        participants=participants,
        chat_messages=chat_messages_data, # Updated to pass profile_pic_url
        agenda_data=agenda_data
    )

@meeting_bp.route("/<int:meeting_id>/edit", methods=["GET", "POST"])
@login_required
def edit_meeting(meeting_id):
    """
    Edit a meeting. Only the organizer can do this.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        flash("You are not authorized to edit this meeting.", "danger")
        return redirect(url_for("meeting_bp.meeting_list"))

    if request.method == "POST":
        meeting.title = request.form.get("title", "").strip()
        meeting.description = request.form.get("description", "").strip()
        date_time_str = request.form.get("date_time", "").strip()
        duration_str = request.form.get("duration", "").strip()

        if not meeting.title or not date_time_str:
            flash("Title and Date/Time are required.", "danger")
            return redirect(url_for("meeting_bp.edit_meeting", meeting_id=meeting_id))

        try:
            meeting.date_time = datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            flash("Invalid date/time format. Use YYYY-MM-DDTHH:MM.", "danger")
            return redirect(url_for("meeting_bp.edit_meeting", meeting_id=meeting_id))

        if duration_str:
            try:
                minutes = int(duration_str)
                meeting.duration = timedelta(minutes=minutes)
            except ValueError:
                flash("Invalid duration format.", "danger")
                return redirect(url_for("meeting_bp.edit_meeting", meeting_id=meeting_id))

        db.session.commit()
        flash("Meeting updated successfully.", "success")
        return redirect(url_for("meeting_bp.meeting_list"))

    return render_template("meeting_form.html", meeting=meeting)

@meeting_bp.route("/<int:meeting_id>/delete", methods=["POST"])
@login_required
def delete_meeting(meeting_id):
    """
    Delete a meeting. Only the organizer can do this.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        flash("You are not authorized to delete this meeting.", "danger")
        return redirect(url_for("meeting_bp.meeting_list"))

    db.session.delete(meeting)
    db.session.commit()
    flash("Meeting deleted successfully.", "success")
    return redirect(url_for("meeting_bp.meeting_list"))

##############################################################################
# PARTICIPANTS
##############################################################################
@meeting_bp.route("/<int:meeting_id>/participants/add", methods=["GET", "POST"])
@login_required
def add_participant(meeting_id):
    """
    Add a user to an existing meeting. Only the organizer can do this.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        flash("You are not authorized to modify participants for this meeting.", "danger")
        return redirect(url_for("meeting_bp.meeting_list"))

    if request.method == "POST":
        user_id = request.form.get("user_id")
        if not user_id:
            flash("Please select a user.", "danger")
            return redirect(url_for("meeting_bp.add_participant", meeting_id=meeting_id))

        try:
            user_id = int(user_id)
        except ValueError:
            flash("Invalid user ID.", "danger")
            return redirect(url_for("meeting_bp.add_participant", meeting_id=meeting_id))

        existing = Participant.query.filter_by(meeting_id=meeting_id, user_id=user_id).first()
        if existing:
            flash("User is already a participant.", "warning")
            return redirect(url_for("meeting_bp.add_participant", meeting_id=meeting_id))

        participant = Participant(
            meeting_id=meeting_id,
            user_id=user_id,
            role="attendee"
        )
        db.session.add(participant)
        db.session.commit()

        flash("Participant added successfully.", "success")
        return redirect(url_for("meeting_bp.meeting_details", meeting_id=meeting_id))

    existing_ids = [p.user_id for p in Participant.query.filter_by(meeting_id=meeting_id).all()]
    users = User.query.filter(~User.user_id.in_(existing_ids)).all()
    return render_template("add_participant.html", meeting=meeting, users=users)

##############################################################################
# TRANSCRIPT ROUTES
##############################################################################
@meeting_bp.route("/transcript/<int:transcript_id>/update", methods=["POST"])
@login_required
def update_transcript(transcript_id):
    """
    Update (POST) the processed_transcript text for the given transcript.
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

@meeting_bp.route("/transcript/<int:transcript_id>/delete", methods=["POST"])
@login_required
def delete_transcript(transcript_id):
    """
    Delete a transcript by ID. 
    """
    transcript = Transcript.query.get_or_404(transcript_id)
    db.session.delete(transcript)
    db.session.commit()

    return jsonify({
        "message": "Transcript deleted",
        "transcript_id": transcript_id
    })

@meeting_bp.route("/transcript/<int:transcript_id>/autocorrect", methods=["POST"])
@login_required
def autocorrect_transcript(transcript_id):
    """
    Use WatsonxLLM to autocorrect grammar (while preserving style).
    """
    transcript = Transcript.query.get_or_404(transcript_id)
    text_to_correct = transcript.raw_transcript.strip()

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
    Correct grammar without changing original meaning of transcript to keep speakers style.

    Text to correct:
    {text}

    Output only the final corrected text. No explanation or description.
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

@meeting_bp.route("/transcript/<int:transcript_id>/reset", methods=["POST"])
@login_required
def reset_transcript(transcript_id):
    """
    Reset the processed_transcript field back to an empty string.
    """
    transcript = Transcript.query.get_or_404(transcript_id)
    transcript.processed_transcript = ""
    db.session.commit()

    return jsonify({
        "transcript_id": transcript.transcript_id,
        "raw_transcript": transcript.raw_transcript,
        "processed_transcript": transcript.processed_transcript
    })

##############################################################################
# TASK EXTRACTION ROUTE
##############################################################################
@meeting_bp.route("/extract_tasks", methods=["POST"])
@login_required
def extract_tasks():
    """
    Combine all transcripts for a meeting, feed them to a WatsonxLLM prompt,
    parse the resulting JSON to create ActionItem tasks in the DB.
    """
    from datetime import datetime
    import re
    import json

    def parse_iso_date(date_str):
        if not date_str or date_str.lower() == "null":
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

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
    You are an AI that extracts tasks from the following meeting transcript.
    Return only valid JSON with no code fences, no explanation, no disclaimers.
    Your entire response must be valid JSON. The JSON must be an array of objects.
    Each object must have the following keys:
      - "description" (string, required)
      - "assigned_to" (integer or null)
      - "status" (string, default "pending")
      - "priority" (string, default "medium")
      - "start_date" (string in YYYY-MM-DD format or null)
      - "due_date" (string in YYYY-MM-DD format or null)

    Transcript:
    {text}

    Output only the JSON array, nothing else.
    Do NOT include any additional text like 'JSON:' or 'Here is the JSON'. Only the raw array.
    Remember that start_date and due_date must be either null or in the exact format YYYY-MM-DD.
    """
    prompt = PromptTemplate.from_template(prompt_template)
    llm_chain = prompt | watsonx_llm

    result = llm_chain.invoke({"text": full_text})
    print("===== LLM Raw Result =====")
    print(result)
    try:
        tasks = json.loads(result)
    except Exception as e:
        return jsonify({
            "error": "Failed to parse tasks JSON",
            "details": str(e),
            "raw_output": result
        }), 500
    print(tasks) # DEBUG CODE
    # Remove existing tasks for this meeting, then re-create them
    existing_tasks = ActionItem.query.filter_by(meeting_id=meeting_id).all()
    for t in existing_tasks:
        db.session.delete(t)
    db.session.commit()

    new_tasks = []
    for tdata in tasks:
        description = tdata.get("description", "").strip()
        if not description:
            # Skip empty tasks
            continue
        new_task = ActionItem(
            meeting_id=meeting_id,
            description=description,
            assigned_to=tdata.get("assigned_to"),
            status=tdata.get("status", "pending"),
            priority=tdata.get("priority", "medium"),
            start_date=parse_iso_date(tdata.get("start_date")),
            due_date=parse_iso_date(tdata.get("due_date")),
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

##############################################################################
# ACTION ITEMS: Update Status, Update Details
##############################################################################
@meeting_bp.route("/action_item/<int:action_item_id>/update_status", methods=["POST"])
@login_required
def update_task_status(action_item_id):
    """
    Update just the status of a task (e.g. 'pending' or 'complete').
    """
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

@meeting_bp.route("/action_item/<int:action_item_id>/update", methods=["POST"])
@login_required
def update_task_details(action_item_id):
    """
    Update the details (description, assigned_to, priority, start_date, due_date)
    for a task.
    """
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

##############################################################################
# FILE UPLOAD
##############################################################################
@meeting_bp.route("/upload_file", methods=["POST"])
@login_required
def upload_file():
    """
    POST a file for the meeting. Broadcast a chat message with the file link.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    meeting_id = request.form.get("meeting_id")

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # Save file to uploads folder
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "static/uploads")
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
    save_path = os.path.join(upload_folder, unique_filename)
    file.save(save_path)

    file_url = url_for("static", filename=f"uploads/{unique_filename}")

    # Broadcast to the chat for that meeting
    socketio.emit(
        "chat_message",
        {
            "username": current_user.username,
            "message": f"Shared file: <a href='{file_url}' target='_blank'>{filename}</a>",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        },
        room=f"meeting_{meeting_id}",
        namespace="/chat"
    )

    return jsonify({"success": True, "file_url": file_url})

##############################################################################
# CONFERENCE (ORGANIZER-ONLY) START/STOP
##############################################################################
@meeting_bp.route("/conference/start/<int:meeting_id>", methods=["POST"])
@login_required
def start_conference(meeting_id):
    """
    Mark a meeting's `conference_active` field True. Notify participants via Socket.IO.
    Only the organizer can do this.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        return jsonify({"error": "Only the organizer can start the conference"}), 403

    meeting.conference_active = True
    db.session.commit()

    socketio.emit(
        "conference_started",
        {"meeting_id": meeting_id},
        room=f"meeting_{meeting_id}",
        namespace="/webrtc"
    )
    return jsonify({"success": True})

@meeting_bp.route("/conference/stop/<int:meeting_id>", methods=["POST"])
@login_required
def stop_conference(meeting_id):
    """
    Mark a meeting's `conference_active` field False. Notify participants via Socket.IO.
    Only the organizer can do this.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        return jsonify({"error": "Only the organizer can stop the conference"}), 403

    meeting.conference_active = False
    db.session.commit()

    socketio.emit(
        "conference_stopped",
        {"meeting_id": meeting_id},
        room=f"meeting_{meeting_id}",
        namespace="/webrtc"
    )
    return jsonify({"success": True})

# RESETTING TRANSCRIPT TABLE
@meeting_bp.route("/transcripts/reset", methods=["POST"])
# run using curl -X POST http://127.0.0.1:5001/meetings/transcripts/reset 
@login_required # take of login to simplify
def reset_transcripts():
    from app.models import Transcript
    Transcript.query.delete()
    db.session.commit()
    return jsonify({"message": "Transcripts have been reset successfully."})
