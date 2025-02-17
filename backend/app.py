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
from extensions import db, bcrypt


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

# Import Blueprints
from routes.symptom_and_static_routes import symptom_routes
from routes.health_data_routes import health_data_routes
from routes.report_routes import report_routes
from routes.user_routes import user_routes
from routes.utils_health_routes import utils_health_bp
from routes.onboarding_routes import onboarding_routes
from routes.library_routes import library_routes

# Register Blueprints with /api prefix
app.register_blueprint(symptom_routes, url_prefix='/api/symptoms')
app.register_blueprint(health_data_routes, url_prefix='/api/health-data')
app.register_blueprint(report_routes, url_prefix='/api/reports')
app.register_blueprint(user_routes, url_prefix='/api/users')
app.register_blueprint(utils_health_bp, url_prefix='/api')
app.register_blueprint(onboarding_routes, url_prefix='/api/onboarding')
app.register_blueprint(library_routes, url_prefix='/api/library')

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'status': 401,
        'sub_status': 42,
        'msg': 'The token has expired'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'status': 401,
        'sub_status': 43,
        'msg': 'Invalid token'
    }), 401

# Serve React App - must be after API routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path.startswith('api/'):
        return {'error': 'Not Found'}, 404
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# API Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'The server is running smoothly.'
    }), 200

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'User already exists'}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            'message': 'User created successfully',
            'user_id': new_user.id
        }), 201

    except Exception as e:
        logger.error(f'Error creating user: {str(e)}')
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

def find_available_port(starting_port=5001):
    """Finds an available port starting from the given port number."""
    current_port = starting_port
    while current_port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', current_port)) != 0:
                return current_port
            current_port += 1
    raise RuntimeError('No available ports found')

def kill_existing_flask():
    """Kills any existing Flask process safely."""
    try:
        output = subprocess.check_output(['pgrep', '-f', 'python.*app.py'], text=True).strip()
        if output:
            for pid in output.split('\n'):
                try:
                    subprocess.run(['kill', '-9', pid], check=True)
                    logger.info(f'Killed existing Flask process: {pid}')
                except subprocess.SubprocessError as e:
                    logger.warning(f'Failed to kill process {pid}: {e}')
    except subprocess.SubprocessError:
        logger.info('No existing Flask process found')

# WSGI Application
application = app

if __name__ == '__main__':
    logger.info('Starting Flask application...')
    kill_existing_flask()

    port = find_available_port(5001)
    os.environ['FLASK_RUN_PORT'] = str(port)

    logger.info(f'Starting server on port {port}')
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=port,
        debug=False
    )