from app import app
from backend.routes.extensions import db, bcrypt
from backend.models import User, Symptom, SymptomLog, Report, HealthData
from datetime import datetime, timedelta

with app.app_context():
    try:
        # Clear existing test data
        User.query.filter_by(username="testuser").delete()
        db.session.commit()

        # Create test user
        hashed_password = bcrypt.generate_password_hash("testpassword").decode("utf-8")
        user = User(
            username="testuser",
            password=hashed_password,
            email="test@example.com"  # Add email if required
        )
        db.session.add(user)
        db.session.commit()

        # Create symptoms
        symptoms = [
            Symptom(name="Headache", description="Pain in the head region"),
            Symptom(name="Fever", description="Elevated body temperature"),
            Symptom(name="Cough", description="Persistent coughing"),
            Symptom(name="Fatigue", description="Feeling of tiredness")
        ]
        db.session.bulk_save_objects(symptoms)
        db.session.commit()

        # Create symptom logs with proper symptom_id references
        current_time = datetime.utcnow()
        symptom_logs = []
        for i, symptom in enumerate(symptoms):
            log = SymptomLog(
                user_id=user.id,
                symptom_id=symptom.id,
                severity=i + 1,  # Varying severity 1-4
                notes=f"Day {i+1} of symptoms",
                timestamp=current_time - timedelta(days=i)
            )
            symptom_logs.append(log)
        db.session.bulk_save_objects(symptom_logs)
        db.session.commit()

        # Create reports with required fields
        reports = [
            Report(
                user_id=user.id,
                title="Weekly Health Summary",
                content="Patient experienced varying symptoms over the past week, including headaches and fever.",
                timestamp=current_time
            ),
            Report(
                user_id=user.id,
                title="Monthly Progress Report",
                content="Overall improvement in symptoms noted. Headache frequency has decreased.",
                timestamp=current_time - timedelta(days=30)
            )
        ]
        db.session.bulk_save_objects(reports)
        db.session.commit()

        # Create health data entries
        health_data = [
            HealthData(
                user_id=user.id,
                data_type="Blood Pressure",
                value="120/80",
                timestamp=current_time
            ),
            HealthData(
                user_id=user.id,
                data_type="Temperature",
                value="98.6",
                timestamp=current_time
            ),
            HealthData(
                user_id=user.id,
                data_type="Heart Rate",
                value="72",
                timestamp=current_time
            )
        ]
        db.session.bulk_save_objects(health_data)
        db.session.commit()

        print("✅ Test data inserted successfully!")
        print(f"Created user: {user.username}")
        print(f"Created {len(symptoms)} symptoms")
        print(f"Created {len(symptom_logs)} symptom logs")
        print(f"Created {len(reports)} reports")
        print(f"Created {len(health_data)} health data entries")

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error inserting test data: {str(e)}")
        raise e  # Re-raise the exception for debugging