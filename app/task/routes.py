# app/task/routes.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, current_app
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from passlib.hash import bcrypt

# Import your own modules as needed:
from app.config import Config
from flask_login import current_user
from app.models import ActionItem, User, Meeting, TaskComment, TaskFile
from app.extensions import db
from datetime import datetime

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = os.path.join("app", "static", "uploads", "documents")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "zip"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


task_bp = Blueprint("task_bp", __name__, template_folder="templates")

@task_bp.route("/")
@login_required
def tasks():
    """ View all tasks assigned to the user. """
    user_id = current_user.user_id
    tasks = ActionItem.query.filter(
        (ActionItem.assigned_to == user_id) | (ActionItem.meeting.has(Meeting.organizer_id == user_id))
    ).all()
    return render_template("tasks.html", tasks=tasks)


@task_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_task():
    """ Create a new task with file uploads. """
    if request.method == "POST":
        description = request.form.get("description", "").strip()
        assigned_to = request.form.get("assigned_to")
        priority = request.form.get("priority", "medium")
        due_date_str = request.form.get("due_date")
        meeting_id = request.form.get("meeting_id")

        if not description:
            flash("Task description is required", "danger")
            return redirect(url_for("task_bp.new_task"))

        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
        
        task = ActionItem(
            description=description,
            assigned_to=int(assigned_to) if assigned_to else None,
            priority=priority,
            due_date=due_date,
            meeting_id=meeting_id
        )
        db.session.add(task)
        db.session.commit()
        
                # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        
        # Handle File Uploads
        if "task_files" in request.files:
            files = request.files.getlist("task_files")
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)

                    task_file = TaskFile(task_id=task.action_item_id, filename=filename)
                    db.session.add(task_file)

            db.session.commit()
        
        flash("Task created successfully!", "success")
        return redirect(url_for("task_bp.tasks"))

    users = User.query.all()
    meetings = Meeting.query.filter_by(organizer_id=current_user.user_id).all()
    return render_template("task_form.html", users=users, meetings=meetings)


@task_bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    """ Edit an existing task and manage file uploads. """
    task = ActionItem.query.get_or_404(task_id)

    if request.method == "POST":
        task.description = request.form.get("description", "").strip()
        task.assigned_to = int(request.form.get("assigned_to")) if request.form.get("assigned_to") else None
        task.priority = request.form.get("priority", "medium")

        due_date_str = request.form.get("due_date")
        if due_date_str:
            task.due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        else:
            task.due_date = None
        
        
        db.session.commit()
        
                # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        
        # Handle File Uploads
        if "task_files" in request.files:
            files = request.files.getlist("task_files")
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)

                    task_file = TaskFile(task_id=task.action_item_id, filename=filename)
                    db.session.add(task_file)

            db.session.commit()
        
        
        
        flash("Task updated successfully!", "success")
        return redirect(url_for("task_bp.tasks", task_id=task.action_item_id))

    users = User.query.all()
    for user in users:
        if user.profile_pic_url:
            user.profile_pic_url = f"/static/{user.profile_pic_url}"
        else:
            user.profile_pic_url = "/static/default-profile.png"

    meetings = Meeting.query.filter_by(organizer_id=current_user.user_id).all()
    return render_template("task_form.html", task=task, users=users, meetings=meetings)


@task_bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    """ Delete a task. """
    task = ActionItem.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted successfully!", "success")
    return redirect(url_for("task_bp.tasks"))


@task_bp.route("/<int:task_id>/update_status", methods=["POST"])
@login_required
def update_task_status(task_id):
    """ Update task status (pending, in_progress, completed). """
    task = ActionItem.query.get_or_404(task_id)
    new_status = request.json.get("status")

    if new_status not in ["pending", "in_progress", "completed"]:
        return jsonify({"error": "Invalid status"}), 400

    task.status = new_status
    db.session.commit()

    return jsonify({"task_id": task.action_item_id, "status": task.status})

@task_bp.route("/<int:task_id>/comment", methods=["POST"])
@login_required
def add_comment(task_id):
    """ Add a comment to a task. """
    task = ActionItem.query.get_or_404(task_id)
    comment_text = request.form.get("comment_text", "").strip()

    if not comment_text:
        flash("Comment cannot be empty", "danger")
        return redirect(url_for("task_bp.edit_task", task_id=task_id))

    comment = TaskComment(task_id=task_id, user_id=current_user.user_id, comment_text=comment_text)
    db.session.add(comment)
    db.session.commit()
    
    flash("Comment added successfully!", "success")
    return redirect(url_for("task_bp.edit_task", task_id=task_id))

@task_bp.route("/file/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_file(file_id):
    """ Delete a file attached to a task. """
    file = TaskFile.query.get_or_404(file_id)
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)

    # Remove the file from storage
    if os.path.exists(file_path):
        os.remove(file_path)

    db.session.delete(file)
    db.session.commit()
    
    flash("File deleted successfully!", "success")
    return redirect(url_for("task_bp.edit_task", task_id=file.task_id))
