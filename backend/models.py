from enum import Enum
from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy
from backend.extensions import db, bcrypt

class UserTierEnum(Enum):
    """Enumeration for user subscription tiers."""
    FREE = "free"
    PAID = "paid"
    ONE_TIME = "one_time"

class CareRecommendationEnum(Enum):
    """Enumeration for care recommendation levels."""
    HOME_CARE = "home_care"
    SEE_DOCTOR = "see_doctor"
    URGENT_CARE = "urgent_care"

class User(db.Model):
    """User model for authentication and subscription management."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    subscription_tier = db.Column(db.Enum(UserTierEnum), default=UserTierEnum.FREE, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    symptoms = db.relationship('SymptomLog', backref='user', lazy='dynamic')
    reports = db.relationship('Report', backref='user', lazy='dynamic')
    health_data = db.relationship('HealthData', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Verify the user's password."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convert user to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'email': self.email,
            'subscription_tier': self.subscription_tier.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Symptom(db.Model):
    """Symptom model for cataloging known symptoms (optional, not used directly yet)."""
    __tablename__ = 'symptoms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description
        }

class SymptomLog(db.Model):
    """Log of user-reported symptoms."""
    __tablename__ = 'symptom_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symptom_name = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text, nullable=True)  # Stores AI response or additional details
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert symptom log to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symptom_name': self.symptom_name,
            'notes': json.loads(self.notes) if self.notes and self.notes.startswith('{') else self.notes,
            'timestamp': self.timestamp.isoformat()
        }

class Report(db.Model):
    """Report model for storing AI-generated assessments or doctor reports."""
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)  # JSON string with assessment details
    care_recommendation = db.Column(db.Enum(CareRecommendationEnum), default=CareRecommendationEnum.SEE_DOCTOR, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert report to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'content': json.loads(self.content) if self.content and self.content.startswith('{') else self.content,
            'care_recommendation': self.care_recommendation.value,
            'created_at': self.created_at.isoformat()
        }

class HealthData(db.Model):
    """Health data model for storing additional user health metrics."""
    __tablename__ = 'health_data'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)  # e.g., 'heart_rate', 'blood_pressure'
    value = db.Column(db.String(100), nullable=False)  # JSON or string value
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert health data to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'data_type': self.data_type,
            'value': json.loads(self.value) if self.value and self.value.startswith('{') else self.value,
            'recorded_at': self.recorded_at.isoformat()
        }

class RevokedToken(db.Model):
    """Model for storing revoked JWT tokens."""
    __tablename__ = 'revoked_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(120), unique=True, nullable=False)
    revoked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert revoked token to dictionary."""
        return {
            'id': self.id,
            'jti': self.jti,
            'revoked_at': self.revoked_at.isoformat()
        }