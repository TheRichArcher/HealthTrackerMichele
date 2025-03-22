from backend.extensions import db, bcrypt
from datetime import datetime
from enum import Enum

class UserTierEnum(Enum):
    FREE = "FREE"
    ONE_TIME = "ONE_TIME"
    PAID = "PAID"

class CareRecommendationEnum(Enum):
    NONE = "NONE"
    SELF_CARE = "SELF_CARE"
    SEE_DOCTOR = "SEE_DOCTOR"
    URGENT_CARE = "URGENT_CARE"
    EMERGENCY = "EMERGENCY"

class User(db.Model):
    """User model."""
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(100))
    subscription_tier = db.Column(db.Enum(UserTierEnum), default=UserTierEnum.FREE)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password) if self.password_hash else False

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "subscription_tier": self.subscription_tier.value,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }

class RevokedToken(db.Model):
    """Revoked token model."""
    __tablename__ = "revoked_tokens"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(120), unique=True, nullable=False)
    revoked_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "jti": self.jti,
            "revoked_at": self.revoked_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

class SymptomLog(db.Model):
    """Symptom log model."""
    __tablename__ = "symptoms"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symptom_name = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.Integer)
    intensity = db.Column(db.Integer, nullable=True)
    respiratory_rate = db.Column(db.Integer, nullable=True)
    oxygen_saturation = db.Column(db.Integer, nullable=True)
    waist_circumference = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "symptom_name": self.symptom_name,
            "severity": self.severity,
            "intensity": self.intensity,
            "respiratory_rate": self.respiratory_rate,
            "oxygen_saturation": self.oxygen_saturation,
            "waist_circumference": self.waist_circumference,
            "notes": self.notes,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }

class HealthData(db.Model):
    """Health data model."""
    __tablename__ = "health_data"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(255), nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "data_type": self.data_type,
            "value": self.value,  # Raw string
            "recorded_at": self.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

class Report(db.Model):
    """Report model."""
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    temp_user_id = db.Column(db.String(36))
    assessment_id = db.Column(db.String(36))
    title = db.Column(db.String(255))
    content = db.Column(db.Text)
    status = db.Column(db.String(50))
    care_recommendation = db.Column(db.Enum(CareRecommendationEnum))
    report_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "temp_user_id": self.temp_user_id,
            "assessment_id": self.assessment_id,
            "title": self.title,
            "content": self.content,  # Raw string
            "status": self.status,
            "care_recommendation": self.care_recommendation.value if self.care_recommendation else None,
            "report_url": self.report_url,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }