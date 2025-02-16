import os
import logging
import openai
import socket
import subprocess
from datetime import timedelta
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    get_jwt_identity, jwt_required, get_jwt
)
from .extensions import db, bcrypt

# Initialize Flask application with static file handling
app = Flask(__name__,
    static_folder='static/dist',
    static_url_path=''
)
CORS(app, origins=os.getenv('CORS_ORIGINS', '*'))

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600)))
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000)))
jwt = JWTManager(app)

# Logging Configuration
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError('DATABASE_URL is missing. Check your .env file.')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Initialize Flask extensions
db.init_app(app)
bcrypt.init_app(app)

# Import models after database initialization
from models import User, Symptom, SymptomLog, Report, HealthData, RevokedToken

# Manual Database Creation
with app.app_context():
    db.create_all()
    logger.info('✅ Database tables created manually')

[... rest of the file remains exactly the same until the blueprint imports ...]

# Import Blueprints
from routes.symptom_and_static_routes import symptom_routes
from routes.health_data_routes import health_data_routes
from routes.report_routes import report_routes
from routes.user_routes import user_routes
from routes.utils_health_routes import utils_health_bp
from routes.onboarding_routes import onboarding_routes
from routes.library_routes import library_routes

[... rest of the file remains exactly the same ...]