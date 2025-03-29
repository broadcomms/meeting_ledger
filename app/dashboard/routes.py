# app/dashboard/routes.py

import os
from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.models import User, Meeting, Participant, ActionItem, OrganizationMember, Invitation
from sqlalchemy import or_, desc
import os

dashboard_bp = Blueprint("dashboard_bp", __name__, template_folder="templates")

def path_exists_in_static(relative_path: str) -> bool:
    """
    Given a relative path like 'uploads/profile_pics/3_user.png',
    build an absolute path in 'static/' and check if the file exists.
    """
    if not relative_path:
        return False
    full_path = os.path.join(current_app.static_folder, relative_path)
    return os.path.isfile(full_path)

@dashboard_bp.route("/")
@login_required
def dashboard():
    # If user isn't 'user', block them
    if current_user.role not in ["user", "manager", "admin"]:
        flash("Access denied.", "danger")
        return redirect(url_for("main_bp.index"))

    # Validate profile pic
    if not path_exists_in_static(current_user.profile_pic_url):
        current_user.profile_pic_url = ""

    # Gather the user’s meetings
    organized_meetings = Meeting.query.filter_by(organizer_id=current_user.user_id).all()
    participation = Participant.query.filter_by(user_id=current_user.user_id).all()
    participant_meetings = [p.meeting for p in participation if p.meeting.organizer_id != current_user.user_id]
    meetings = organized_meetings + participant_meetings

    # Gather tasks
    meeting_ids = list(set(m.meeting_id for m in meetings))
    tasks = ActionItem.query.filter(ActionItem.meeting_id.in_(meeting_ids)).all()

    # Gather members
    members = User.query.all()
    for member in members:
        if not path_exists_in_static(member.profile_pic_url):
            member.profile_pic_url = "default-profile.png"

    # Get active memberships:
    my_org_memberships = OrganizationMember.query.filter_by(user_id=current_user.user_id, status="active").all()
    my_orgs = [membership.organization for membership in my_org_memberships]
    # Also get pending invitations (for memberships with status "invited")
    pending_memberships = OrganizationMember.query.filter_by(user_id=current_user.user_id, status="invited").all()
    # Optionally, get the corresponding Invitation record for each pending membership:
    pending_invitations = []
    for membership in pending_memberships:
        invitation = Invitation.query.filter_by(org_id=membership.org_id, email=current_user.email).first()
        if invitation:
            pending_invitations.append(invitation)
            
            
            
            
    # Query a meeting object (whatever logic you want)
    meeting = Meeting.query.first()  # or get a specific meeting if you have an ID
    if not meeting:
        # handle no meeting found, or create a default one, or skip passing it
        meeting = None
            
    return render_template("dashboard.html",
                           user=current_user,
                           meetings=meetings,
                           tasks=tasks,
                           members=members,
                           my_orgs=my_orgs,  # pass the list to the template
                           pending_invitations=pending_invitations,
                           meeting=meeting
                          )
