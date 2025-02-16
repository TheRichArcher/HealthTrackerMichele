from app import app
from extensions import db
from models import User, Symptom, SymptomLog, Report, HealthData
import bcrypt
from datetime import datetime

with app.app_context():
    try:
        # Delete existing user if it exists
        existing_user = User.query.filter_by(username="testuser").first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        # Hash password
        hashed_password = bcrypt.hashpw("testpassword".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Insert into 'users'
        user = User(username="testuser", password=hashed_password)
        db.session.add(user)
        db.session.commit()

        # Insert into 'symptoms'
        symptom = Symptom(
            user_id=user.id,
            name="Headache",
            description="Severe pain in the head",
            intensity="High",
            onset_date=datetime.utcnow(),
        )
        db.session.add(symptom)
        db.session.commit()

        # Insert into 'symptom_logs'
        symptom_log = SymptomLog(user_id=user.id, symptom="Headache", severity="Moderate", notes="Started yesterday")
        db.session.add(symptom_log)
        db.session.commit()

        # Insert into 'reports'
        report = Report(user_id=user.id, symptoms="Headache", timeline="Past week")
        db.session.add(report)
        db.session.commit()

        # Insert into 'health_data'
        health_data = HealthData(user_id=user.id, data_type="Blood Pressure", value="120/80")
        db.session.add(health_data)
        db.session.commit()

        print("✅ Test data inserted successfully!")

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error inserting test data: {str(e)}")