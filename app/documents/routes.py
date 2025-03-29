# app/document/routes.py

from flask import (
    Blueprint, render_template, request
)
from flask_login import login_required, current_user

# Import your own modules as needed:
from app.config import Config
from app.models import TaskFile, ChatFile
from app.extensions import db
from datetime import datetime
import os

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "zip"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

documents_bp = Blueprint("documents_bp", __name__, template_folder="templates")

# Render the calender template
@documents_bp.route("/")
@login_required
def documents_view():
    """ 
    Retrieve documents from TaskFile and ChatFile and
    display them together in the documents.html template. 
    Allows filtering by type, uploader, meeting, and date range.
    """

    # ------------------ 1) Grab filters from request.args  ------------------
    filter_source = request.args.get("source", "").strip()         # "Chat File", "Task File", or ""
    filter_uploader = request.args.get("uploader", "").strip()     # e.g. "sally"
    filter_meeting = request.args.get("meeting_id", "").strip()    # e.g. "9"
    filter_start = request.args.get("start_date", "").strip()      # e.g. "2025-01-01"
    filter_end = request.args.get("end_date", "").strip()          # e.g. "2025-12-31"

    # Convert start/end to actual datetimes if present
    start_dt = None
    end_dt = None
    date_format = "%Y-%m-%d"
    try:
        if filter_start:
            start_dt = datetime.strptime(filter_start, date_format)
        if filter_end:
            # end_dt + 1 day if you want it inclusive to that day
            end_dt = datetime.strptime(filter_end, date_format)
    except ValueError:
        pass  # If there's an error, just ignore for now

    # -------------- 2) Query both ChatFile and TaskFile from the DB --------------
    chat_files = ChatFile.query.all()
    task_files = TaskFile.query.all()
    
    # -------------- 3) Convert them into a single list of dicts  --------------
    all_docs = []
    
    # For ChatFile
    for cf in chat_files:
        # If you store the meeting ID in ChatFile.meeting_id
        doc_info = {
            "source": "Chat File",
            "filename": cf.filename,
            "file_url": cf.file_url,
            "uploader": cf.username,
            "uploaded_at": cf.uploaded_at,
            "meeting_id": cf.meeting_id,   # add so we can filter by meeting
        }
        all_docs.append(doc_info)

    # For TaskFile
    for tf in task_files:
        # If your TaskFile is related to a task which references meeting,
        # you can do tf.task.meeting_id if you want the meeting filter
        meeting_id_val = tf.task.meeting_id if (tf.task and tf.task.meeting_id) else None

        doc_info = {
            "source": "Task File",
            "filename": tf.filename,
            "file_url": f"/static/uploads/{tf.filename}",
            "uploader": tf.task.assignee.username if tf.task and tf.task.assignee else "Unknown",
            "uploaded_at": tf.uploaded_at,
            "meeting_id": meeting_id_val,  # might be None if not set
        }
        all_docs.append(doc_info)

    # -------------- 4) Apply filters in Python  --------------
    filtered_docs = []

    for doc in all_docs:
        # Filter by Type
        if filter_source and doc["source"] != filter_source:
            continue

        # Filter by Uploader
        if filter_uploader and doc["uploader"] != filter_uploader:
            continue

        # Filter by Meeting
        # If the user typed in a numeric meeting_id, we check doc's meeting_id
        if filter_meeting:
            try:
                requested_meeting_id = int(filter_meeting)
                if doc["meeting_id"] != requested_meeting_id:
                    continue
            except ValueError:
                pass  # If invalid, ignore filter

        # Filter by date range
        if start_dt and doc["uploaded_at"] and doc["uploaded_at"] < start_dt:
            continue
        if end_dt and doc["uploaded_at"] and doc["uploaded_at"] > end_dt:
            continue

        # If it passes all filters, keep it
        filtered_docs.append(doc)

    # Sort the final list if desired (descending by time)
    filtered_docs.sort(
        key=lambda doc: doc["uploaded_at"] or datetime.min,
        reverse=True
    )

    # -------------- 5) Render the template  --------------
    return render_template(
        "documents.html", 
        all_docs=filtered_docs,
        filter_source=filter_source,
        filter_uploader=filter_uploader,
        filter_meeting=filter_meeting,
        filter_start=filter_start,
        filter_end=filter_end
    )