# app/websockets/chat_ws.py

import os
from flask import current_app, request
from flask_login import current_user
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

# Import your DB and ChatMessage model
from app.extensions import db
from app.models import ChatMessage, User, ChatFile

UPLOAD_FOLDER = "app/static/uploads/documents"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



def register_chat_events(socketio: SocketIO):
    """
    Register all Socket.IO chat event handlers under the '/chat' namespace.
    """
    @socketio.on("connect", namespace="/chat")
    def chat_connect(auth):
        print("[CHAT] CONNECT CALLED")

        meeting_id = None

        # Try auth (works in websocket handshake)
        if auth and "meeting_id" in auth:
            meeting_id = auth["meeting_id"]
        # Fallback if auth not present (e.g., polling transport)
        elif "meeting_id" in request.args:
            meeting_id = request.args.get("meeting_id")

        print("AUTH:", auth)
        print("ARGS:", request.args)
        print(f"[CHAT] MEETING ID {meeting_id}")

        if meeting_id:
            join_room(f"meeting_{meeting_id}")
            print(f"[CHAT] Client joined room meeting_{meeting_id}")
        else:
            print("[CHAT] ❌ No meeting_id provided, not joining any room.")



    @socketio.on("chat_message", namespace="/chat")
    def handle_chat_message(data):
        # Convert meeting_id to int if your DB column is integer
        try:
            meeting_id = int(data.get("meeting_id"))
        except (TypeError, ValueError):
            meeting_id = None
            
        message = data.get("message", "")
        user = User.query.get(current_user.user_id) if current_user.is_authenticated else None
        username = user.username if user else "Anonymous"
        
        # Build profile pic URL
        profile_pic_url = user.profile_pic_url if (user and user.profile_pic_url) else "default-profile.png"
        if not profile_pic_url.startswith("/static/"):
            profile_pic_url = "/static/" + profile_pic_url
        
        # Create a real datetime
        timestamp_dt = datetime.utcnow()

        # Store the message in DB
        chat_msg = ChatMessage(
            meeting_id=meeting_id,
            user_id=user.user_id if user else None,
            username=username,
            message=message,
            timestamp=timestamp_dt
        )
        db.session.add(chat_msg)
        db.session.commit()
        
        
        # Send timestamp as ISO string or "YYYY-MM-DD HH:MM:SS" to the UI
        timestamp_str = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Broadcast to everyone in the room
        emit(
            "chat_message",
            {
                "username": username,
                "message": message,
                "timestamp": timestamp_str,
                "profile_pic_url": profile_pic_url
            },
            room=f"meeting_{meeting_id}",
            namespace="/chat"
        )
    
    @socketio.on("file_upload", namespace="/chat")
    def handle_file_upload(data):
        """
        The client has already uploaded the file via /chat/upload_file.
        This event simply broadcasts a chat message with the clickable file link.
        """
        try:
            meeting_id = int(data.get("meeting_id"))
        except (TypeError, ValueError):
            meeting_id = None
            
        filename = data.get("filename")
        file_url = data.get("file_url")

        user = User.query.get(current_user.user_id) if current_user.is_authenticated else None
        username = user.username if user else "Anonymous"

        # Build profile pic
        profile_pic_url = user.profile_pic_url if (user and user.profile_pic_url) else "default-profile.png"
        if not profile_pic_url.startswith("/static/"):
            profile_pic_url = "/static/" + profile_pic_url

        timestamp_dt = datetime.utcnow()


        # Create a ChatMessage with the file link
        chat_message = ChatMessage(
            meeting_id=meeting_id,
            user_id=(user.user_id if user else None),
            username=username,
            message=f'<a href="{file_url}" target="_blank">📄 {filename}</a>',
            timestamp=timestamp_dt
        )
        db.session.add(chat_message)
        db.session.commit()
        
        timestamp_str = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")


        # Notify all attendees in the room
        emit(
            "chat_message",
            {
                "username": username,
                "message": f'<a href="{file_url}" target="_blank">📄 {filename}</a>',
                "timestamp": timestamp_str,
                "profile_pic_url": profile_pic_url
            },
            room=f"meeting_{meeting_id}",
            namespace="/chat"
        )