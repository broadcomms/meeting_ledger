# app/websockets/agent_ws.py
from flask import current_app
from flask_socketio import join_room
from app.extensions import SocketIO

def register_agent_events(socketio: SocketIO):
    
    @socketio.on('join', namespace="/agent")
    def handle_join(data):
        room = data.get('room')
        if room:
            join_room(room)
            current_app.logger.info(f"Client joined room: {room}")