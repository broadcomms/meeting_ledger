# app/chat/routes.py

from flask import Blueprint, request, jsonify
import os
from werkzeug.utils import secure_filename
from flask_login import current_user
from app.models import ChatFile, db

chat_bp = Blueprint("chat", __name__)

UPLOAD_FOLDER = "app/static/uploads/documents"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@chat_bp.route("/upload_file", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(file_path)

        user = current_user if current_user.is_authenticated else None
        username = user.username if user else "Anonymous"

        chat_file = ChatFile(
            meeting_id=request.form.get("meeting_id"),
            user_id=user.user_id if user else None,
            username=username,
            filename=filename,
            file_url=f"/static/uploads/documents/{filename}"
        )
        db.session.add(chat_file)
        db.session.commit()

        return jsonify({
            "success": True,
            "filename": filename,
            "file_url": f"/static/uploads/documents/{filename}"
        })

    return jsonify({"error": "Invalid file type"}), 400