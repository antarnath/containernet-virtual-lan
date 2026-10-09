"""Test OpenAPI schema for events endpoint."""
import json
from app.main import app
schema = app.openapi()
print('events registered:', '/api/projects/{project_id}/events' in schema.get('paths', {}))
for p in sorted(schema.get('paths', {}).keys()):
    if 'event' in p:
        print(' -', p, list(schema['paths'][p].keys()))
