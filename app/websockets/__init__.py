# app/websockets/__init__.py

from .chat_ws import register_chat_events
from .transcription_ws import register_transcription_events
from .webrtc_ws import register_webrtc_events
from .agent_ws import register_agent_events

def init_socketio_events(socketio):
    """
    Initialize all Socket.IO event handlers across namespaces.
    """
    register_chat_events(socketio)
    register_transcription_events(socketio)
    register_webrtc_events(socketio)
    register_agent_events(socketio)