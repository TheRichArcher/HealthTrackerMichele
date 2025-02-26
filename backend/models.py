from datetime import datetime, timedelta
from backend.routes.extensions import db
from sqlalchemy.orm import validates, Query
from sqlalchemy import func
import enum

# Define enums for database use
class UserTierEnum(enum.Enum):
    FREE = "free"
    PAID = "paid"
    ONE_TIME = "one_time"

class CareRecommendationEnum(enum.Enum):
    HOME_CARE = "You can likely manage this at home."
    SEE_DOCTOR = "Consider seeing a doctor soon."
    URGENT_CARE = "You should seek urgent care."

# Constants for use in code
class UserTier:
    FREE = "free"
    PAID = "paid"
    ONE_TIME = "one_time"

class CareRecommendation:
    HOME_CARE = "You can likely manage this at home."
    SEE_DOCTOR = "Consider seeing a doctor soon."
    URGENT_CARE = "You should seek urgent care."

# Base query class that filters out soft-deleted records by default
class QueryWithSoftDelete(Query):
    _with_deleted = False

    def __new__(cls, *args, **kwargs):
        obj = super(QueryWithSoftDelete, cls).__new__(cls)
        obj._with_deleted = kwargs.pop('_with_deleted', False)
        if len(args) > 0:
            super(QueryWithSoftDelete, obj).__init__(*args, **kwargs)
            return obj.filter_by(deleted_at=None) if not obj._with_deleted else obj
        return obj

    def with_deleted(self):
        return self.__class__(self._entity_zero(), 
                             session=self.session, 
                             _with_deleted=True)

    def without_deleted(self):
        return self.filter_by(deleted_at=None)

    def only_deleted(self):
        return self.with_deleted().filter(self._entity_zero().class_.deleted_at.isnot(None))

# Base model for models with soft delete
class SoftDeleteMixin:
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)
    
    query_class = QueryWithSoftDelete
    
    def soft_delete(self):
        self.deleted_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()  # Commit immediately
    
    def restore(self):
        self.deleted_at = None
        db.session.add(self)
        db.session.commit()  # Commit immediately
    
    @property
    def is_deleted(self):
        return self.deleted_at is not None
    
    @classmethod
    def get_deleted(cls):
        """Get all soft-deleted records"""
        return cls.query.only_deleted().all()

class User(SoftDeleteMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)  # Added index
    password = db.Column(db.String(120), nullable=False)
    subscription_tier = db.Column(
        db.Enum(UserTierEnum, name='user_tier_enum'), 
        default=UserTierEnum.FREE, 
        nullable=False,
        index=True  # Added index for subscription_tier
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add table-level indexes
    __table_args__ = (
        db.Index('ix_users_username_subscription', 'username', 'subscription_tier'),  # Composite index
    )

    # Relationships with cascade behavior
    symptoms = db.relationship('SymptomLog', backref='user', lazy=True, 
                              cascade="all, delete-orphan")  # Cascade delete
    reports = db.relationship('Report', backref='user', lazy=True, 
                             cascade="all, delete-orphan")  # Cascade delete
    health_data = db.relationship('HealthData', backref='user', lazy=True, 
                                 cascade="all, delete-orphan")  # Cascade delete

    def __repr__(self):
        return f'<User {self.username}>'
    
    @classmethod
    def get_by_subscription_tier(cls, tier):
        """Get all active users with a specific subscription tier"""
        return cls.query.without_deleted().filter(cls.subscription_tier == tier).all()
    
    @classmethod
    def get_by_username(cls, username):
        """Get user by username, excluding soft-deleted users"""
        return cls.query.without_deleted().filter(cls.username == username).first()
    
    @classmethod
    def search(cls, term):
        """Search for users by username"""
        return cls.query.without_deleted().filter(cls.username.ilike(f'%{term}%')).all()

class Symptom(SoftDeleteMixin, db.Model):
    __tablename__ = 'symptoms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)  # Added index
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Add table-level indexes for common text searches
    __table_args__ = (
        db.Index('ix_symptoms_name_text', 'name', postgresql_using='gin', 
                postgresql_ops={'name': 'gin_trgm_ops'}),  # Text search index
    )

    # Relationships - use passive_deletes to avoid actual deletion
    logs = db.relationship('SymptomLog', backref='symptom', lazy=True,
                          passive_deletes=True)  # Don't cascade delete, use passive_deletes

    def __repr__(self):
        return f'<Symptom {self.name}>'
    
    @classmethod
    def search(cls, term):
        """Search for symptoms by name or description"""
        return cls.query.without_deleted().filter(
            db.or_(
                cls.name.ilike(f'%{term}%'),
                cls.description.ilike(f'%{term}%')
            )
        ).all()
    
    @classmethod
    def get_by_name(cls, name):
        """Get symptom by exact name"""
        return cls.query.without_deleted().filter(cls.name == name).first()
    
    @classmethod
    def get_by_name_like(cls, name_pattern):
        """Get symptoms with names matching a pattern"""
        return cls.query.without_deleted().filter(cls.name.ilike(f'%{name_pattern}%')).all()

class SymptomLog(db.Model):
    __tablename__ = 'symptom_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    symptom_id = db.Column(db.Integer, db.ForeignKey('symptoms.id', ondelete="SET NULL"), nullable=True, index=True)
    severity = db.Column(db.Integer, index=True)  # Added index for severity queries
    notes = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)  # Added index
    symptom_name = db.Column(db.String(100), index=True)  # Added index for symptom_name

    # Add table-level indexes for common queries
    __table_args__ = (
        db.Index('ix_symptom_logs_user_timestamp', 'user_id', 'timestamp'),  # Composite index
        db.Index('ix_symptom_logs_severity_timestamp', 'severity', 'timestamp'),  # Composite index
    )

    def __repr__(self):
        return f'<SymptomLog {self.user_id} - {self.symptom_id or self.symptom_name}>'
    
    @classmethod
    def get_by_user(cls, user_id, include_deleted_symptoms=False):
        """Get symptom logs for a specific user, optionally including those with deleted symptoms"""
        query = cls.query.filter(cls.user_id == user_id)
        
        if not include_deleted_symptoms:
            # Left join with Symptom to handle both cases:
            # 1. Where symptom_id exists and the symptom is not deleted
            # 2. Where symptom_id is NULL (but we still have symptom_name)
            query = query.outerjoin(Symptom, cls.symptom_id == Symptom.id).filter(
                db.or_(
                    Symptom.deleted_at.is_(None),  # Symptom exists and is not deleted
                    cls.symptom_id.is_(None)       # No linked symptom (using symptom_name instead)
                )
            )
        
        return query.order_by(cls.timestamp.desc()).all()
    
    @classmethod
    def get_by_severity(cls, min_severity, max_severity=None):
        """Get symptom logs within a severity range"""
        query = cls.query.filter(cls.severity >= min_severity)
        
        if max_severity is not None:
            query = query.filter(cls.severity <= max_severity)
            
        # Join with User to exclude logs from deleted users
        query = query.join(User, cls.user_id == User.id).filter(User.deleted_at.is_(None))
        
        return query.order_by(cls.timestamp.desc()).all()
    
    @classmethod
    def get_by_symptom(cls, symptom_id):
        """Get logs for a specific symptom"""
        # Join with User to exclude logs from deleted users
        return cls.query.filter(cls.symptom_id == symptom_id)\
                .join(User, cls.user_id == User.id)\
                .filter(User.deleted_at.is_(None))\
                .order_by(cls.timestamp.desc()).all()

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, index=True)  # Added index
    content = db.Column(db.Text, nullable=False)
    care_recommendation = db.Column(
        db.Enum(CareRecommendationEnum, name='care_recommendation_enum'),
        nullable=True,
        index=True  # Added index for care_recommendation
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)  # Added index
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add table-level indexes for common queries
    __table_args__ = (
        db.Index('ix_reports_user_created', 'user_id', 'created_at'),  # Composite index
        db.Index('ix_reports_title_text', 'title', postgresql_using='gin', 
                postgresql_ops={'title': 'gin_trgm_ops'}),  # Text search index
    )

    def __repr__(self):
        return f'<Report {self.title}>'
    
    @classmethod
    def get_by_care_recommendation(cls, recommendation):
        """Get reports with a specific care recommendation"""
        # Join with User to exclude reports from deleted users
        return cls.query.filter(cls.care_recommendation == recommendation)\
                .join(User, cls.user_id == User.id)\
                .filter(User.deleted_at.is_(None))\
                .all()
    
    @classmethod
    def get_by_user(cls, user_id):
        """Get reports for a specific user"""
        # Join with User to ensure the user is not deleted
        return cls.query.filter(cls.user_id == user_id)\
                .join(User, cls.user_id == User.id)\
                .filter(User.deleted_at.is_(None))\
                .order_by(cls.created_at.desc()).all()
    
    @classmethod
    def search_by_title(cls, title_pattern):
        """Search reports by title"""
        # Join with User to exclude reports from deleted users
        return cls.query.filter(cls.title.ilike(f'%{title_pattern}%'))\
                .join(User, cls.user_id == User.id)\
                .filter(User.deleted_at.is_(None))\
                .order_by(cls.created_at.desc()).all()

class HealthData(db.Model):
    __tablename__ = 'health_data'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    data_type = db.Column(db.String(50), nullable=False, index=True)  # Added index
    value = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)  # Added index

    # Add table-level indexes for common queries
    __table_args__ = (
        db.Index('ix_health_data_user_type_time', 'user_id', 'data_type', 'timestamp'),  # Composite index
    )

    def __repr__(self):
        return f'<HealthData {self.data_type}: {self.value}>'
    
    @classmethod
    def get_by_user_and_type(cls, user_id, data_type):
        """Get health data for a specific user and type"""
        # Join with User to ensure the user is not deleted
        return cls.query.filter(
            cls.user_id == user_id,
            cls.data_type == data_type
        ).join(User, cls.user_id == User.id)\
          .filter(User.deleted_at.is_(None))\
          .order_by(cls.timestamp.desc()).all()
    
    @classmethod
    def get_latest_by_user(cls, user_id):
        """Get the latest health data entries for a user, one per type"""
        subquery = db.session.query(
            cls.data_type,
            func.max(cls.timestamp).label('max_timestamp')
        ).filter(cls.user_id == user_id)\
         .group_by(cls.data_type)\
         .subquery('latest_timestamps')
        
        # Join with User to ensure the user is not deleted
        return cls.query.join(
            subquery,
            db.and_(
                cls.data_type == subquery.c.data_type,
                cls.timestamp == subquery.c.max_timestamp
            )
        ).filter(cls.user_id == user_id)\
         .join(User, cls.user_id == User.id)\
         .filter(User.deleted_at.is_(None))\
         .all()

class RevokedToken(db.Model):
    __tablename__ = 'revoked_tokens'
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, unique=True, index=True)  # Added index
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)  # Added index

    def __repr__(self):
        return f'<RevokedToken {self.jti}>'
    
    @classmethod
    def is_revoked(cls, jti):
        """Check if a token is revoked"""
        return cls.query.filter(cls.jti == jti).first() is not None
    
    @classmethod
    def cleanup_expired(cls, expiry_days=30):
        """Remove tokens older than the specified number of days"""
        expiry_date = datetime.utcnow() - timedelta(days=expiry_days)
        cls.query.filter(cls.created_at < expiry_date).delete()
        db.session.commit()