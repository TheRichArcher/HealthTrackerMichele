import os

# Path to the symptom_routes.py file
symptom_routes_path = os.path.join('backend', 'routes', 'symptom_routes.py')

# Read the file
with open(symptom_routes_path, 'r') as f:
    content = f.read()

# Check if the file uses the new OpenAI client
if 'from openai import OpenAI' in content:
    print("Found new OpenAI client import")
    
    # Replace with legacy client
    content = content.replace('from openai import OpenAI', 'import openai')
    
    # Replace client initialization
    content = content.replace('client = OpenAI(', 'openai.api_key = os.getenv("OPENAI_API_KEY")\n    # client = OpenAI(')
    
    # Replace client usage
    content = content.replace('client.chat.completions.create', 'openai.ChatCompletion.create')
    
    # Write the modified content back
    with open(symptom_routes_path, 'w') as f:
        f.write(content)
    
    print(f"Modified {symptom_routes_path} to use legacy OpenAI client")
else:
    print("New OpenAI client import not found")
