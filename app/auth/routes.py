# app/auth/routes.py

import os
import jwt
import datetime
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from passlib.hash import bcrypt
from sqlalchemy import or_
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
# Flask-Mail
from flask_mail import Message

# Import database & models
from app.extensions import db, login_manager, mail
from app.models import User

auth_bp = Blueprint("auth_bp", __name__, template_folder="templates")

# SECRET_KEY for JWT or token generation (in production, load from config)
SECRET_KEY = os.environ.get("SECRET_KEY", "change_me_in_env")

########################################################
# Helper function to send verification/reset emails
########################################################
def send_email(to_address, subject, body_html):
    """
    Uses Flask-Mail to send an HTML email.
    Make sure your app.config[MAIL_*] settings are correct.
    """
    msg = Message(
        subject, 
        sender=("Meeting Ledger", "patrickndille@gmail.com"),
        recipients=[to_address]
        )
    msg.html = body_html
    mail.send(msg)
    print("Email Verification message sent") # DEBUG

########################################################
# Registration
########################################################
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    
    """
    Handle user registration.
    If an invitation token and org_id are provided, automatically add the new user
    to that organization.
    """
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        username = request.form.get("username", "").strip()  # Optional: for display
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        job_title = request.form.get("job_title", "").strip()
        organization = request.form.get("organization", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        # Basic validation
        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("auth_bp.register"))

        # Check for existing user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("That email is already taken.", "danger")
            return redirect(url_for("auth_bp.register"))

        # Hash password with passlib
        hashed_pw = bcrypt.hash(password)

        # Generate verification token
        verification_token = secrets.token_urlsafe(32)

        new_user = User(
            email=email,
            password=hashed_pw,
            username=username if username else email.split("@")[0],
            first_name=first_name,
            last_name=last_name,
            job_title=job_title,
            organization=organization,
            phone_number=phone_number,
            email_verified=False,
            verification_token=verification_token,
            role="user",
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Check if invitation token was provided
        invitation_token = request.args.get("invitation_token")
        org_id = request.args.get("org_id", type=int)
        if invitation_token and org_id:
            from app.models import Invitation, OrganizationMember
            invitation = Invitation.query.filter_by(token=invitation_token, org_id=org_id, email=email).first()
            if invitation:
                # Create membership for the new user
                new_membership = OrganizationMember(
                    org_id=org_id,
                    user_id=new_user.user_id,
                    role="user",
                    status="active"
                )
                db.session.add(new_membership)
                # Optionally, mark the invitation as used (or delete it)
                db.session.delete(invitation)
                db.session.commit()

        # Send verification email
        verification_link = url_for("auth_bp.verify_email", token=verification_token, _external=True)
        email_body = f"""
        <p>Welcome to Meeting Ledger!</p>
        <p>Please verify your email by clicking this link:
        <a href="{verification_link}">Verify Email</a></p>
        <p>If you did not sign up for Meeting Ledger, please ignore this email.</p>
        """
        send_email(to_address=email, subject="Verify your Meeting Ledger account", body_html=email_body)

        flash("Registration successful! Please check your email to verify your account.", "success")
        return redirect(url_for("auth_bp.login"))

    # Render registration form (optionally, pass along invitation_token and org_id to the template)
    invitation_token = request.args.get("invitation_token")
    org_id = request.args.get("org_id")
    return render_template("register.html", invitation_token=invitation_token, org_id=org_id)

########################################################
# Email Verification
########################################################
@auth_bp.route("/verify_email/<token>")
def verify_email(token):
    """
    Handles email verification via token in the URL.
    If token matches, set email_verified=True.
    Then if any invitation exist for this email, automatically add
    user to those organizations.
    """
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash("Invalid verification token.", "danger")
        return redirect(url_for("auth_bp.login"))

    # Mark user as verified
    user.email_verified = True
    user.verification_token = None  # Clear token so it can’t be reused
    db.session.commit()

    # Check for invitations that match this user's email
    from app.models import Invitation, OrganizationMember
    pending_invitations = Invitation.query.filter_by(email=user.email).all()

    added_orgs = []
    for inv in pending_invitations:
        # Check if user is already in the org
        existing_member = OrganizationMember.query.filter_by(
            org_id=inv.org_id,
            user_id=user.user_id
        ).first()
        if not existing_member:
            # Add them as active or invited
            new_member = OrganizationMember(
                org_id=inv.org_id,
                user_id=user.user_id,
                role="user",
                status="active"
            )
            db.session.add(new_member)
            added_orgs.append(inv.org_id)
        # Remove or mark invitation as used
        db.session.delete(inv)
    db.session.commit()

    if added_orgs:
        flash("Your email has been verified! You have also been added to any pending organizations.", "success")
    else:
        flash("Your email has been verified!", "success")

    return redirect(url_for("auth_bp.login"))


########################################################
# Login
########################################################
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Email-based login.
    - Check if email_verified first. If not verified, block or show message.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth_bp.login"))

        if not bcrypt.verify(password, user.password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth_bp.login"))

        if not user.email_verified:
            flash("Your email is not verified. Please check your inbox.", "danger")
            return redirect(url_for("auth_bp.login"))

        # Log user in
        login_user(user)
        flash("Logged in successfully.", "success")
        return redirect(url_for("dashboard_bp.dashboard"))

    return render_template("login.html")

########################################################
# Logout
########################################################
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_bp.index"))



########################################################
# Password Reset - Request (Forgot Password)
########################################################
@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """
    Request password reset. Generates a token and emails it to the user.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("If that email exists, a reset link has been sent.", "info")
            return redirect(url_for("auth_bp.forgot_password"))

        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        db.session.commit()

        reset_link = url_for("auth_bp.reset_password", token=reset_token, _external=True)
        email_body = f"""
        <p>We received a request to reset your Meeting Ledger password.</p>
        <p>Click here to reset: <a href="{reset_link}">Reset Password</a></p>
        <p>If you did not request this, please ignore.</p>
        """
        send_email(to_address=email, subject="Password Reset - Meeting Ledger", body_html=email_body)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth_bp.login"))

    return render_template("forgot_password.html")

########################################################
# Password Reset - Process
########################################################
@auth_bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """
    Validate reset token, let user set a new password.
    """
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        flash("Invalid or expired reset token.", "danger")
        return redirect(url_for("auth_bp.forgot_password"))

    # Check if token is expired
    if user.reset_token_expires < datetime.datetime.utcnow():
        flash("That reset link has expired. Please request a new one.", "danger")
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        return redirect(url_for("auth_bp.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or not confirm_password:
            flash("All fields are required.", "danger")
            return redirect(url_for("auth_bp.reset_password", token=token))

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth_bp.reset_password", token=token))

        # Update password
        user.password = bcrypt.hash(new_password)
        # Clear reset token
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()

        flash("Your password has been updated. Please log in.", "success")
        return redirect(url_for("auth_bp.login"))

    return render_template("reset_password.html")

########################################################
# Example Role-Restricted Endpoint
########################################################
@auth_bp.route("/admin_only")
@login_required
def admin_only():
    """
    Example protected route that only Admin can access.
    """
    if current_user.role != "admin":
        flash("You do not have permission to access this resource.", "danger")
        return redirect(url_for("dashboard_bp.dashboard"))
    return "Welcome, Admin! (This is a secure admin-only endpoint.)"







###########################################
############################
# JWT-based API Endpoints    (Returns JSON)
############################
###########################################
import jwt
import datetime

SECRET_KEY = "your_secret_key_here"  # Use from config in production

def generate_token(user):
    """Generate JWT token for authentication"""
    payload = {
        "user_id": user.user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    """Authenticate user (email-based) and return a JWT token"""
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.verify(password, user.password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.email_verified:
        return jsonify({"error": "Email not verified"}), 403

    payload = {
        "user_id": user.user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user.user_id,
            "email": user.email,
            "role": user.role
        }
    })

@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    """Register a new user (email-based) via JSON API"""
    data = request.get_json()
    email = data.get("email", "").lower()
    username = data.get("username", "")
    password = data.get("password", "")
    # For brevity, ignoring other profile fields in the JSON API

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    existing_user = User.query.filter(
        or_(User.email == email, User.username == username)
    ).first()
    if existing_user:
        return jsonify({"error": "Email or username already taken"}), 400

    verification_token = secrets.token_urlsafe(32)
    hashed_pw = bcrypt.hash(password)
    new_user = User(
        email=email,
        password=hashed_pw,
        username=username if username else email.split("@")[0],
        email_verified=False,
        verification_token=verification_token,
        role="user",
    )
    db.session.add(new_user)
    db.session.commit()

    # To auto-send verification email in the API route:
    # verification_link = url_for("auth_bp.verify_email", token=verification_token, _external=True)
    # send_email(...) # etc.
    
    return jsonify({"message": "User registered successfully, verify email to activate."}), 201

@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    """Logout user from session-based login"""
    logout_user()
    return jsonify({"message": "Logged out successfully"}), 200

@auth_bp.route("/api/auth/user", methods=["GET"])
@login_required
def api_get_user():
    """Return logged-in user details"""
    return jsonify({
        "user": {
            "id": current_user.user_id,
            "email": current_user.email,
            "role": current_user.role,
            "email_verified": current_user.email_verified
        }
    })

