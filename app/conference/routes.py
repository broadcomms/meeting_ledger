# app/conference/routes.py
from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user
from app.models import Meeting
from app.extensions import db, socketio  # Assuming socketio is created in your extensions module

conference_bp = Blueprint('conference_bp', __name__, url_prefix='/conference')

@conference_bp.route('/start/<int:meeting_id>', methods=['POST'])
@login_required
def start_conference(meeting_id):
    """
    Organizer starts the conference.
    - Checks if the current user is the meeting organizer.
    - Sets the conference_active flag to True.
    - Broadcasts a 'conference_started' event to the meeting room.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    if meeting.conference_active:
        return jsonify({'success': False, 'error': 'Conference already started'}), 400

    meeting.conference_active = True
    db.session.commit()
    
    # Broadcast event so that clients can update their UI (if needed)
    socketio.emit('conference_started', {'meeting_id': meeting_id},
                  room=f"meeting_{meeting_id}", namespace='/webrtc')
    
    return jsonify({'success': True, 'message': 'Conference started'})

@conference_bp.route('/stop/<int:meeting_id>', methods=['POST'])
@login_required
def stop_conference(meeting_id):
    """
    Organizer stops the conference.
    - Verifies that the current user is the organizer.
    - Sets the conference_active flag to False.
    - Broadcasts a 'conference_ended' event to the meeting room.
    """
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.organizer_id != current_user.user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    if not meeting.conference_active:
        return jsonify({'success': False, 'error': 'Conference is not active'}), 400

    meeting.conference_active = False
    db.session.commit()
    
    # Broadcast event so that clients (including attendees) know the conference has ended
    socketio.emit('conference_ended', {'meeting_id': meeting_id},
                  room=f"meeting_{meeting_id}", namespace='/webrtc')
    
    return jsonify({'success': True, 'message': 'Conference stopped'})

