import json
import os
import sys
from unittest.mock import MagicMock

# Mock out modules that aren't installed or configured
sys.modules['dotenv'] = MagicMock()
sys.modules['supabase'] = MagicMock()

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from main import app

def export_openapi():
    # Force FastAPI to generate the schema
    openapi_schema = app.openapi()
    
    # Write it to the root of the repo
    with open('openapi.json', 'w', encoding='utf-8') as f:
        json.dump(openapi_schema, f, indent=2)
    
    print("OpenAPI schema exported to openapi.json successfully!")

if __name__ == '__main__':
    export_openapi()
