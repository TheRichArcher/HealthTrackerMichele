from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_cors import CORS

# Initialize Flask extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
cors = CORS()