from app import app
from backend.routes.extensions import db, bcrypt
from backend.models import User, Symptom, SymptomLog, Report, HealthData
from datetime import datetime

with app.app_context():
    try:
        # Delete existing user if it exists
        existing_user = User.query.filter_by(username="testuser").first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        # Hash password using Flask Bcrypt
        hashed_password = bcrypt.generate_password_hash("testpassword").decode("utf-8")

        # Insert user
        user = User(username="testuser", password=hashed_password)
        db.session.add(user)
        db.session.commit()

        # Insert symptom
        symptom = Symptom(name="Headache", description="Severe pain in the head")
        db.session.add(symptom)
        db.session.commit()

        # Insert symptom log (corrected to use symptom_id)
        symptom_log = SymptomLog(user_id=user.id, symptom_id=symptom.id, severity=3, notes="Started yesterday")
        db.session.add(symptom_log)
        db.session.commit()

        # Insert report (corrected to include title & content)
        report = Report(
            user_id=user.id,
            title="Headache Analysis",
            content="Patient reported a headache for the past week.",
        )
        db.session.add(report)
        db.session.commit()

        # Insert health data
        health_data = HealthData(user_id=user.id, data_type="Blood Pressure", value="120/80")
        db.session.add(health_data)
        db.session.commit()

        print("✅ Test data inserted successfully!")

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error inserting test data: {str(e)}")
