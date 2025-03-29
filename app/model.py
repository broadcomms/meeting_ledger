# app/models.py
from datetime import datetime
from flask_login import UserMixin
from .extensions import db

# ---------------- Transcript Model ----------------
class Transcript(db.Model):
    __tablename__ = 'transcripts'
    transcript_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    speaker_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    raw_transcript = db.Column(db.Text, nullable=False)
    processed_transcript = db.Column(db.Text, default='')
    language = db.Column(db.String(10), default='en')
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    speaker = db.relationship("User", backref="transcripts")

# ---------------- Summary Model ----------------
class Summary(db.Model):
    __tablename__ = 'summaries'
    summary_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    summary_text = db.Column(db.Text, nullable=False)
    summary_type = db.Column(db.String(20), default='detailed')
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- ActionItem Model ----------------
class ActionItem(db.Model):
    __tablename__ = 'action_items'
    action_item_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.meeting_id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    assignee = db.relationship("User", backref="tasks")
    meeting = db.relationship("Meeting", backref="tasks")

# ---------------- TaskComment Model ----------------
class TaskComment(db.Model):
    __tablename__ = 'task_comments'
    comment_id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('action_items.action_item_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    comment_text = db.Column(db.Text, nullable=False)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="comments")
    task = db.relationship("ActionItem", backref="comments")

# ---------------- User Model ----------------
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    
    # Basic Identity
    username = db.Column(db.String(100), nullable=True)  # Used for display name
    email = db.Column(db.String(255), unique=True, nullable=False)  # For login
    password = db.Column(db.Text, nullable=False)
    
    # Profile Information
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    job_title = db.Column(db.String(150), nullable=True)
    organization = db.Column(db.String(150), nullable=True)
    phone_number = db.Column(db.String(50), nullable=True)
    
    # Role Based Access Control (RBAC)
    role = db.Column(db.String(50), default='user')  # 'admin', 'manager', 'user'
    
    # Email verification
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255), nullable=True)
    
    # Password Reset
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Profile Picture
    profile_pic_url = db.Column(db.String(255), default='')
    
    # Timestamps
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    updated_timestamp = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # Organizations owned by the user
    owned_organizations = db.relationship("Organization", back_populates="owner")
    # Memberships in organizations
    org_memberships = db.relationship("OrganizationMember", back_populates="user", lazy="dynamic")
    # Meetings organized by the user (explicit relationship using primary join)
    meetings_organized = db.relationship(
        "Meeting",
        primaryjoin="User.user_id == Meeting.organizer_id",
        lazy="dynamic"
    )
    # Meetings the user participates in (using back_populates)
    participations = db.relationship("Participant", back_populates="user", lazy="dynamic")
    calendar_events = db.relationship("CalendarEvent", back_populates="user")

    chat_files = db.relationship("ChatFile", back_populates="user")
    def get_id(self):
        return str(self.user_id)
# ---------------- Meeting Model ----------------
class Meeting(db.Model):
    __tablename__ = 'meetings'
    meeting_id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.org_id"), nullable=True)  # optional
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    date_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Interval)
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    meeting_type = db.Column(db.String(100), nullable=True)  # Added field for meeting type
    meeting_objectives = db.Column(db.Text, nullable=True)  # Added field for meeting objectives
    conference_active = db.Column(db.Boolean, default=False)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship("User", foreign_keys=[organizer_id], overlaps="meetings_organized")

    participants = db.relationship("Participant", backref="meeting", cascade="all, delete-orphan")
    organization = db.relationship("Organization", back_populates="meetings")


# ---------------- Participant Model ----------------
class Participant(db.Model):
    __tablename__ = 'participants'
    participant_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meetings.meeting_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    role = db.Column(db.String(50), default='attendee')

    # Use explicit back_populates to avoid naming conflicts.
    user = db.relationship("User", back_populates="participations")

# ---------------- ChatMessage Model ----------------
class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    message_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- CalendarEvent Model ----------------
class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'
    event_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    event_type = db.Column(db.String(20), nullable=False)  # "meeting", "task", "custom"
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    related_id = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    
    user = db.relationship("User", back_populates="calendar_events")


# ---------------- TaskFile Model ----------------
class TaskFile(db.Model):
    __tablename__ = 'task_files'
    file_id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('action_items.action_item_id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("ActionItem", backref="files")

# ---------------- ChatFile Model ----------------
class ChatFile(db.Model):
    __tablename__ = 'chat_files'
    file_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    username = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="chat_files")

# ---------------- Organization Model ----------------
class Organization(db.Model):
    __tablename__ = 'organizations'
    org_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    is_private = db.Column(db.Boolean, default=True)  # True => private, False => public
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    members = db.relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    owner = db.relationship("User", back_populates="owned_organizations")
    meetings = db.relationship("Meeting", back_populates="organization", lazy="dynamic")

# ---------------- OrganizationMember Model ----------------
class OrganizationMember(db.Model):
    __tablename__ = 'organization_members'
    member_id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.org_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    role = db.Column(db.String(50), default='user')  
    status = db.Column(db.String(20), default='active')  
    joined_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="org_memberships")
    organization = db.relationship("Organization", back_populates="members")

# ---------------- Invitation Model ----------------
class Invitation(db.Model):
    __tablename__ = 'invitations'
    invitation_id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.org_id'), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    custom_message = db.Column(db.Text, nullable=True)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # You might add an expiration timestamp if needed.
    
    # Add relationship so you can reference the organization from the invitation
    organization = db.relationship("Organization", backref="invitations")

