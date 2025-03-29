# app/profile/routes.py

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from passlib.hash import bcrypt
from app.models import User, db

profile_bp = Blueprint("profile_bp", __name__, template_folder="templates")

# Allowed file extensions for profile photos
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def path_exists_in_static(relative_path: str) -> bool:
    """
    Given a relative path (e.g., "uploads/profile_pics/3_user.png"),
    build the absolute path using current_app.static_folder and check if the file exists.
    """
    if not relative_path:
        return False
    full_path = os.path.join(current_app.static_folder, relative_path)
    return os.path.isfile(full_path)

##############################################################################
# Update Profile Photo
##############################################################################
@profile_bp.route("/update_photo", methods=["GET", "POST"])
@login_required
def update_photo():
    """
    Updates the current user's profile photo.
    The file is saved under static/uploads/profile_pics.
    The relative URL is stored in the user's profile_pic_url column.
    """
    if request.method == "POST":
        file = request.files.get("profile_pic")
        if not file:
            flash("No file provided.", "danger")
            return redirect(url_for("profile_bp.update_photo"))
        if not allowed_file(file.filename):
            flash("Invalid file type. Only PNG/JPG/JPEG/GIF are allowed.", "danger")
            return redirect(url_for("profile_bp.update_photo"))
        
        # Secure filename and save file
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(current_app.static_folder, "uploads", "profile_pics")
        os.makedirs(upload_folder, exist_ok=True)
        unique_filename = f"{current_user.user_id}_{filename}"
        save_path = os.path.join(upload_folder, unique_filename)
        file.save(save_path)
        
        # Store the relative URL (without '/static/')
        relative_url = f"uploads/profile_pics/{unique_filename}"
        current_user.profile_pic_url = relative_url
        db.session.commit()
        
        flash("Profile photo updated successfully!", "success")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    return render_template("update_photo.html")


##############################################################################
# Edit Account (Email, Username, and Profile Data)
##############################################################################
@profile_bp.route("/edit_account", methods=["GET", "POST"])
@login_required
def edit_account():
    """
    Allows the user to edit their personal information,
    including first/last name, job title, phone, etc.
    Only admin/manager can edit other users if needed (by passing user_id?).
    """
    user_id = request.args.get("user_id", type=int, default=current_user.user_id)

    # Only admin/manager can edit someone else's data
    if user_id != current_user.user_id:
        if current_user.role not in ["admin", "manager"]:
            flash("You do not have permission to edit another user's account.", "danger")
            return redirect(url_for("dashboard_bp.dashboard"))

    user_to_edit = User.query.get_or_404(user_id)

    if request.method == "POST":
        # If you're an admin or manager, or editing self
        new_username = request.form.get("username", "").strip()
        new_email = request.form.get("email", "").strip().lower()
        new_first_name = request.form.get("first_name", "").strip()
        new_last_name = request.form.get("last_name", "").strip()
        new_job_title = request.form.get("job_title", "").strip()
        new_organization = request.form.get("organization", "").strip()
        new_phone_number = request.form.get("phone_number", "").strip()

        # Basic validation
        if not new_email:
            flash("Email is required.", "danger")
            return redirect(url_for("profile_bp.edit_account"))

        # Check if new username or email is taken by someone else
        existing_user = User.query.filter(
            (User.user_id != user_to_edit.user_id) &
            ((User.username == new_username) | (User.email == new_email))
        ).first()
        if existing_user:
            flash("That email is already in use.", "danger")
            return redirect(url_for("profile_bp.edit_account"))

        # Update fields
        user_to_edit.username = new_username
        user_to_edit.email = new_email
        user_to_edit.first_name = new_first_name
        user_to_edit.last_name = new_last_name
        user_to_edit.job_title = new_job_title
        user_to_edit.organization = new_organization
        user_to_edit.phone_number = new_phone_number

        db.session.commit()

        flash("Account information updated successfully!", "success")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    return render_template("edit_account.html", user=user_to_edit)



##############################################################################
# Change Password
##############################################################################
@profile_bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """
    Verifies the current password and updates it to a new one.
    """
    if request.method == "POST":
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        
        if not current_password or not new_password or not confirm_password:
            flash("All fields are required.", "danger")
            return redirect(url_for("profile_bp.change_password"))
        
        if not bcrypt.verify(current_password, current_user.password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("profile_bp.change_password"))
        
        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
            return redirect(url_for("profile_bp.change_password"))
        
        current_user.password = bcrypt.hash(new_password)
        db.session.commit()
        
        flash("Password changed successfully!", "success")
        return redirect(url_for("dashboard_bp.dashboard"))
    
    return render_template("change_password.html")


##############################################################################
# Member Profile
##############################################################################
@profile_bp.route("/members/<int:user_id>")
@login_required
def member_profile(user_id):
    """
    Renders a specific user's profile.
    If the member's profile_pic_url is invalid, reset it to an empty string.
    """
    
    
    member = User.query.get_or_404(user_id)
    if not path_exists_in_static(member.profile_pic_url):
        member.profile_pic_url = "default-profile.png"
    return render_template("member_profile.html", member=member)
