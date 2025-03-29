# app/organization/routes.py

from flask import Blueprint, request, redirect, url_for, flash, render_template, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Organization, OrganizationMember, User, Meeting, Invitation
from datetime import datetime
from flask_mail import Message

organization_bp = Blueprint("organization_bp", __name__, template_folder="templates")

# 0. View all organizations

@organization_bp.route("/list")
@login_required
def list_organizations():
    """
    Shows organizations the user belongs to, and optionally public orgs they can join.
    """
    # Orgs the current user is in:
    my_org_ids = [m.org_id for m in current_user.org_memberships]
    my_orgs = Organization.query.filter(Organization.org_id.in_(my_org_ids)).all()

    # Optionally list all public orgs that the user is not in:
    public_orgs = Organization.query.filter_by(is_private=False).filter(~Organization.org_id.in_(my_org_ids)).all()

    return render_template("organization_list.html", my_orgs=my_orgs, public_orgs=public_orgs)



# 1. Create and Organization
@organization_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_organization():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_private = (request.form.get("is_private") == "on")

        if not name:
            flash("Organization name is required.", "danger")
            return redirect(url_for("organization_bp.create_organization"))

        # Check if name already in use
        existing = Organization.query.filter_by(name=name).first()
        if existing:
            flash(f"Organization '{name}' already exists. Please choose a different name.", "danger")
            return redirect(url_for("organization_bp.create_organization"))

        # If no conflict, create the org
        new_org = Organization(
            name=name,
            owner_id=current_user.user_id,
            is_private=is_private,
        )
        db.session.add(new_org)
        db.session.commit()

        # Add owner as an admin member
        owner_membership = OrganizationMember(
            org_id=new_org.org_id,
            user_id=current_user.user_id,
            role="admin",
            status="active"
        )
        db.session.add(owner_membership)
        db.session.commit()

        flash("Organization created successfully!", "success")
        return redirect(url_for("organization_bp.view_organization", org_id=new_org.org_id))

    return render_template("create_organization.html")


# 2. View Organization
# ------------------------------------------------------------------------

@organization_bp.route("/<int:org_id>")
@login_required
def view_organization(org_id):
    """
    Displays organization details, including members, and upcoming/past meetings
    for the organization. If private, ensure user is a member.
    """
    org = Organization.query.get_or_404(org_id)

    # If private, must be a member or owner
    if org.is_private:
        membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()
        if not membership:
            flash("This organization is private. Access denied.", "danger")
            return redirect(url_for("organization_bp.list_organizations"))

    # For the UI, we want upcoming and past meetings
    upcoming_meetings = (org.meetings
                         .filter(Meeting.date_time >= datetime.utcnow())
                         .order_by(Meeting.date_time.asc())
                         .all())

    past_meetings = (org.meetings
                     .filter(Meeting.date_time < datetime.utcnow())
                     .order_by(Meeting.date_time.desc())
                     .all())

    return render_template("view_organization.html",
                           org=org,
                           upcoming_meetings=upcoming_meetings,
                           past_meetings=past_meetings)

# ------------------------------------------------------------------------
# Invite member
# ------------------------------------------------------------------------

@organization_bp.route("/invite_member", methods=["POST"])
@login_required
def invite_member():
    """
    Admin/manager can invite a user by email.
    If the user exists, create an OrganizationMember with status 'invited' 
    and record an Invitation so they can choose to accept or decline.
    If the user does not exist, create an Invitation record and send a registration link.
    """
    import secrets
    org_id = request.form.get("org_id", type=int)
    email = request.form.get("email", "").strip().lower()
    custom_message = request.form.get("custom_message", "").strip()
    org = Organization.query.get_or_404(org_id)

    # Check permission
    my_membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()
    if not my_membership or my_membership.role not in ["admin", "manager"]:
        flash("You do not have permission to invite members.", "danger")
        return redirect(url_for("organization_bp.view_organization", org_id=org_id))

    from app.auth.routes import send_email

    invited_user = User.query.filter_by(email=email).first()
    
    # For existing users:
    if invited_user:
        # Check if membership already exists
        existing_membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=invited_user.user_id).first()
        if existing_membership:
            flash("That user is already in the organization or has been invited.", "warning")
            return redirect(url_for("organization_bp.view_organization", org_id=org_id))
        
        # Create membership with status 'invited'
        new_membership = OrganizationMember(
            org_id=org_id,
            user_id=invited_user.user_id,
            role="user",
            status="invited"
        )
        db.session.add(new_membership)
        db.session.commit()

        # Create an Invitation record for existing users too
        invitation_token = secrets.token_urlsafe(32)
        invitation = Invitation(
            token=invitation_token,
            org_id=org_id,
            email=email,
            custom_message=custom_message
        )
        db.session.add(invitation)
        db.session.commit()

        # Build a link to the respond invitation page (which you already implemented)
        invitation_link = url_for("organization_bp.respond_invitation", invitation_id=invitation.invitation_id, _external=True)
        email_body = f"""
        <p>Hello {invited_user.first_name or invited_user.username},</p>
        <p>You have been invited to join the organization <strong>{org.name}</strong> on Meeting Ledger.</p>
        <p>{custom_message}</p>
        <p>Please click the link below to accept or decline the invitation:</p>
        <p><a href="{invitation_link}">Respond to Invitation</a></p>
        """
        send_email(to_address=email, subject="Invitation to Join Meeting Ledger Organization", body_html=email_body)
        flash(f"Invitation sent to {email}.", "success")
    else:
        # For users who do not exist, create an Invitation record and send registration link.
        invitation_token = secrets.token_urlsafe(32)
        invitation = Invitation(
            token=invitation_token,
            org_id=org_id,
            email=email,
            custom_message=custom_message
        )
        db.session.add(invitation)
        db.session.commit()

        registration_link = url_for("auth_bp.register", invitation_token=invitation_token, org_id=org_id, _external=True)
        email_body = f"""
        <p>Hello,</p>
        <p>You have been invited to join the organization <strong>{org.name}</strong> on Meeting Ledger.</p>
        <p>{custom_message}</p>
        <p>Please register using the following link. Once you register, you'll be automatically added to the organization:</p>
        <p><a href="{registration_link}">Register on Meeting Ledger</a></p>
        """
        send_email(to_address=email, subject="Invitation to Join Meeting Ledger Organization", body_html=email_body)
        flash(f"Invitation email sent to {email}.", "success")
    
    return redirect(url_for("organization_bp.view_organization", org_id=org_id))



# ------------------------------------------------------------------------

# 4. Request Join
@organization_bp.route("/request_join/<int:org_id>", methods=["POST"])
@login_required
def request_join(org_id):
    """
    Allows a user to request membership in a public organization.
    """
    org = Organization.query.get_or_404(org_id)
    if org.is_private:
        flash("This organization is private. You must be invited.", "danger")
        return redirect(url_for("organization_bp.list_organizations"))

    # Check if user is already a member
    existing = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()
    if existing:
        flash("You are already a member or have a pending invitation/request.", "info")
        return redirect(url_for("organization_bp.view_organization", org_id=org_id))

    new_member = OrganizationMember(
        org_id=org_id,
        user_id=current_user.user_id,
        role="user",
        status="requested"
    )
    db.session.add(new_member)
    db.session.commit()

    flash("Request to join sent.", "success")
    return redirect(url_for("organization_bp.view_organization", org_id=org_id))

# ------------------------------------------------------------------------

@organization_bp.route("/approve_request", methods=["POST"])
@login_required
def approve_request():
    org_id = request.form.get("org_id", type=int)
    user_id = request.form.get("user_id", type=int)
    membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=user_id).first_or_404()

    # Must be admin/manager to approve
    admin_membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()
    if not admin_membership or admin_membership.role not in ["admin", "manager"]:
        flash("You do not have permission to approve members.", "danger")
        return redirect(url_for("organization_bp.view_organization", org_id=org_id))

    membership.status = "active"
    db.session.commit()
    flash("Member approved.", "success")
    return redirect(url_for("organization_bp.view_organization", org_id=org_id))
# ------------------------------------------------------------------------
@organization_bp.route("/update_role", methods=["POST"])
@login_required
def update_role():
    """
    Admin can change a member's role to user, manager, or admin.
    """
    org_id = request.form.get("org_id", type=int)
    user_id = request.form.get("user_id", type=int)
    new_role = request.form.get("role", "user")

    membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=user_id).first_or_404()
    my_membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()

    # Only an admin can set roles
    if not my_membership or my_membership.role != "admin":
        flash("Only an admin can change member roles.", "danger")
        return redirect(url_for("organization_bp.view_organization", org_id=org_id))

    membership.role = new_role
    db.session.commit()
    flash("Member role updated successfully.", "success")
    return redirect(url_for("organization_bp.view_organization", org_id=org_id))
# ------------------------------------------------------------------------
@organization_bp.route("/remove_member", methods=["POST"])
@login_required
def remove_member():
    """
    Admin or manager can remove a member from the org.
    """
    org_id = request.form.get("org_id", type=int)
    user_id = request.form.get("user_id", type=int)
    membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=user_id).first_or_404()

    my_membership = OrganizationMember.query.filter_by(org_id=org_id, user_id=current_user.user_id).first()
    if not my_membership or my_membership.role not in ["admin", "manager"]:
        flash("You do not have permission to remove members.", "danger")
        return redirect(url_for("organization_bp.view_organization", org_id=org_id))

    db.session.delete(membership)
    db.session.commit()
    flash("Member removed from organization.", "info")
    return redirect(url_for("organization_bp.view_organization", org_id=org_id))

# ------------------------------------------------------------------------
# Respond to invitations
# ------------------------------------------------------------------------
@organization_bp.route("/respond_invitation", methods=["GET", "POST"])
@login_required
def respond_invitation():
    """
    Allows an invited user to accept or decline an invitation.
    The invitation_id is passed as a query parameter.
    """
    invitation_id = request.args.get("invitation_id", type=int)
    if not invitation_id:
        flash("Invalid invitation link.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    # Load the invitation record
    invitation = Invitation.query.get_or_404(invitation_id)
    
    # Ensure the invitation email matches the current user's email
    if invitation.email.lower() != current_user.email.lower():
        flash("This invitation does not belong to your account.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    if request.method == "POST":
        response = request.form.get("response")
        if response == "accept":
            # Check if a membership already exists
            membership = OrganizationMember.query.filter_by(
                org_id=invitation.org_id,
                user_id=current_user.user_id
            ).first()
            if membership:
                membership.status = "active"
            else:
                membership = OrganizationMember(
                    org_id=invitation.org_id,
                    user_id=current_user.user_id,
                    role="user",
                    status="active"
                )
                db.session.add(membership)
            db.session.delete(invitation)  # Remove the invitation after use
            db.session.commit()
            flash("You have accepted the invitation and are now a member.", "success")
        elif response == "decline":
            db.session.delete(invitation)
            db.session.commit()
            flash("You have declined the invitation.", "info")
        else:
            flash("Invalid response.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    return render_template("respond_invitation.html", invitation=invitation)
