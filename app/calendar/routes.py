# app/calender/routes.py

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
from app.models import ActionItem, User, Meeting, TaskComment, CalendarEvent
from app.extensions import db
from datetime import datetime



calendar_bp = Blueprint("calendar_bp", __name__, template_folder="templates")

# Render the calender template
@calendar_bp.route("/")
@login_required
def calendar_view():
    """ Render the calendar template. """
    return render_template("calendar.html")

# This should remain unchanged for ajax requests.
@calendar_bp.route("/events")
@login_required
def get_events():
    """ Return all calendar events for the logged-in user. """
    meetings = Meeting.query.filter(Meeting.organizer_id == current_user.user_id).all()
    tasks = ActionItem.query.filter(ActionItem.assigned_to == current_user.user_id).all()
    custom_events = CalendarEvent.query.filter_by(user_id=current_user.user_id).all()

    events = []

    for meeting in meetings:
        events.append({
            "id": f"meeting-{meeting.meeting_id}",
            "title": meeting.title,
            "start": meeting.date_time.isoformat(),
            "end": (meeting.date_time + (meeting.duration or timedelta(hours=1))).isoformat(),
            "color": "blue",
            "url": url_for("meeting_bp.meeting_details", meeting_id=meeting.meeting_id)
        })

    for task in tasks:
        if task.due_date:
            events.append({
                "id": f"task-{task.action_item_id}",
                "title": task.description,
                "start": task.due_date.isoformat(),
                "color": "red",
                "url": url_for("task_bp.edit_task", task_id=task.action_item_id)
            })

    for event in custom_events:
        events.append({
            "id": f"custom-{event.event_id}",
            "title": event.title,
            "start": event.start_date.isoformat(),
            "end": event.end_date.isoformat() if event.end_date else event.start_date.isoformat(),
            "color": "green",
        })

    return jsonify(events)


@calendar_bp.route("/events/new", methods=["POST"])
@login_required
def create_event():
    """ Create a new calendar event. """
    data = request.get_json()
    title = data.get("title")
    event_type = data.get("event_type")
    start_date = datetime.strptime(data.get("start_date"), "%Y-%m-%dT%H:%M:%S")
    end_date = datetime.strptime(data.get("end_date"), "%Y-%m-%dT%H:%M:%S") if data.get("end_date") else None

    event = CalendarEvent(
        title=title,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        user_id=current_user.user_id
    )
    db.session.add(event)
    db.session.commit()

    return jsonify({"message": "Event created successfully!"})

@calendar_bp.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    """ Delete a calendar event. """
    event = CalendarEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify({"message": "Event deleted successfully!"})
