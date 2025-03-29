# 
# app/__init__.py
#

import eventlet
eventlet.monkey_patch()

from flask import Flask
from flask_cors import CORS
from .config import Config
from .extensions import db, socketio, login_manager, mail
from flask_migrate import Migrate  # if you use flask-migrate
from flask_login import current_user
from app.models import User

# Blueprint imports
from .main.routes import main_bp
from .auth.routes import auth_bp
from .dashboard.routes import dashboard_bp
from .meeting.routes import meeting_bp
from .profile.routes import profile_bp
from .conference.routes import conference_bp
from .transcription.routes import transcription_bp
from .task.routes import task_bp
from .calendar.routes import calendar_bp
from .documents.routes import documents_bp
from .chat.routes import chat_bp
from .organization.routes import organization_bp
from .agent.routes import agent_bp

# WebSocket initialization
from .websockets import init_socketio_events

def create_app(config_filename=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Enable CORS for all API routes
    CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

    # Initialize Extensions
    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")
    login_manager.init_app(app)
    mail.init_app(app)  # IMPORTANT: Initialize Flask-Mail
    login_manager.login_view = "auth_bp.login"  # Where to redirect if not logged in

    # Provide user_loader so Flask-Login knows how to load user from an ID
    @login_manager.user_loader
    def load_user(user_id):
        # Return a User object or None
        return User.query.get(int(user_id))

    migrate = Migrate(app, db)  # If you're using migrations

    # Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(meeting_bp, url_prefix="/meetings")
    app.register_blueprint(transcription_bp, url_prefix="/transcription")
    app.register_blueprint(conference_bp)
    app.register_blueprint(task_bp, url_prefix="/tasks" )
    app.register_blueprint(calendar_bp, url_prefix="/calendar" )
    app.register_blueprint(documents_bp, url_prefix="/documents" )
    app.register_blueprint(chat_bp, url_prefix="/chat")
    app.register_blueprint(organization_bp, url_prefix="/organization")
    app.register_blueprint(agent_bp)
    # Create tables if needed (or rely on migrations)
    with app.app_context():
        db.create_all()

    # Register Socket.IO events (transcription, chat, webrtc, etc.)
    init_socketio_events(socketio)
    
    # After app and extensions are initialized, import and register websocket events
    from app.websockets.webrtc_ws import register_webrtc_events
    from app.websockets.chat_ws import register_chat_events
    register_webrtc_events(socketio)
    register_chat_events(socketio)

    return app