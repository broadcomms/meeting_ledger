# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change_me_in_env")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URI", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # IBM WatsonX
    WATSONX_API_KEY = os.environ.get("WATSONX_API_KEY", "")
    WATSONX_URL = os.environ.get("WATSONX_URL", "")
    WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID", "")
    WATSONX_STT_URL = os.environ.get("WATSONX_STT_URL", "")

    WATSONX_MODEL_ID_1 = os.environ.get("WATSONX_MODEL_ID_1", "")
    WATSONX_MODEL_ID_2 = os.environ.get("WATSONX_MODEL_ID_2", "")
    WATSONX_MODEL_ID_3 = os.environ.get("WATSONX_MODEL_ID_3", "")
    
    # Flask-Mail config
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
