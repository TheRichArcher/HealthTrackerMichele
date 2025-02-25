from flask import Blueprint, jsonify

# Create Blueprint without hardcoded prefix
library_routes = Blueprint('library', __name__)

@library_routes.route('/', methods=['GET'])
def get_library_resources():
    # Initial library resources based on project requirements
    library_resources = [
        {
            "title": "Understanding AI Diagnostics",
            "url": "https://www.mayoclinic.org/symptoms",
            "category": "AI Information"
        },
        {
            "title": "NIH Health Information",
            "url": "https://www.nih.gov/health-information",
            "category": "Medical Resources"
        },
        {
            "title": "HIPAA Compliance & Your Data",
            "url": "https://www.hhs.gov/hipaa/for-individuals",
            "category": "Privacy & Compliance"
        },
        {
            "title": "Emergency Care Guidelines",
            "url": "https://www.cdc.gov/emergencypreparedness",
            "category": "Emergency Protocols"
        },
        {
            "title": "Understanding Confidence Scores",
            "url": "#",
            "category": "AI Information"
        }
    ]

    return jsonify({"library": library_resources})