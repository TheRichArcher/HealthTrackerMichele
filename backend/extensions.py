from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_cors import CORS

# Initialize Flask extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
cors = CORS()

def init_extensions(app):
    """Initialize Flask extensions with the given app instance."""
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})  # Adjust CORS settings as needed