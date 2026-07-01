import os
import json
import uuid
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Mock Database setup for headless testing
MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), 'mock_db.json')

def load_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            with open(MOCK_DB_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"events": [], "tasks": [], "tasklists": [{"id": "@default", "title": "My Tasks"}]}

def save_mock_db(db):
    with open(MOCK_DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)

# --- MOCK GOOGLE API SERVICE CLASS HIERARCHY ---

class MockExecute:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return self.data

class MockEvents:
    def insert(self, calendarId, body):
        db = load_mock_db()
        event_id = "mock_evt_" + uuid.uuid4().hex[:12]
        event = {
            "id": event_id,
            "summary": body.get("summary", ""),
            "description": body.get("description", ""),
            "start": body.get("start", {}),
            "end": body.get("end", {}),
            "reminders": body.get("reminders", {})
        }
        db["events"].append(event)
        save_mock_db(db)
        return MockExecute(event)
        
    def list(self, calendarId, timeMin=None, timeMax=None, q=None, singleEvents=None, orderBy=None):
        db = load_mock_db()
        items = db["events"]
        if q:
            items = [e for e in items if q.lower() in e.get("summary", "").lower() or q.lower() in e.get("description", "").lower()]
        return MockExecute({"items": items})
        
    def patch(self, calendarId, eventId, body):
        db = load_mock_db()
        event = next((e for e in db["events"] if e["id"] == eventId), None)
        if event:
            if "summary" in body: event["summary"] = body["summary"]
            if "description" in body: event["description"] = body["description"]
            if "start" in body: event["start"] = body["start"]
            if "end" in body: event["end"] = body["end"]
            if "reminders" in body: event["reminders"] = body["reminders"]
            save_mock_db(db)
            return MockExecute(event)
        raise Exception(f"Event with ID {eventId} not found")
        
    def delete(self, calendarId, eventId):
        db = load_mock_db()
        db["events"] = [e for e in db["events"] if e["id"] != eventId]
        save_mock_db(db)
        return MockExecute(None)
        
    def get(self, calendarId, eventId):
        db = load_mock_db()
        event = next((e for e in db["events"] if e["id"] == eventId), None)
        if event:
            return MockExecute(event)
        raise Exception(f"Event with ID {eventId} not found")

class MockCalendarService:
    def events(self):
        return MockEvents()

class MockTasks:
    def insert(self, tasklist, body):
        db = load_mock_db()
        task_id = "mock_task_" + uuid.uuid4().hex[:12]
        task = {
            "id": task_id,
            "title": body.get("title", ""),
            "notes": body.get("notes", ""),
            "due": body.get("due", ""),
            "status": "needsAction"
        }
        db["tasks"].append(task)
        save_mock_db(db)
        return MockExecute(task)
        
    def list(self, tasklist, showCompleted=True, showHidden=True):
        db = load_mock_db()
        return MockExecute({"items": db["tasks"]})
        
    def patch(self, tasklist, task, body):
        db = load_mock_db()
        item = next((t for t in db["tasks"] if t["id"] == task), None)
        if item:
            if "title" in body: item["title"] = body["title"]
            if "notes" in body: item["notes"] = body["notes"]
            if "due" in body: item["due"] = body["due"]
            if "status" in body: item["status"] = body["status"]
            save_mock_db(db)
            return MockExecute(item)
        raise Exception(f"Task with ID {task} not found")
        
    def delete(self, tasklist, task):
        db = load_mock_db()
        db["tasks"] = [t for t in db["tasks"] if t["id"] != task]
        save_mock_db(db)
        return MockExecute(None)
        
    def get(self, tasklist, task):
        db = load_mock_db()
        item = next((t for t in db["tasks"] if t["id"] == task), None)
        if item:
            return MockExecute(item)
        raise Exception(f"Task with ID {task} not found")

class MockTaskLists:
    def list(self):
        db = load_mock_db()
        return MockExecute({"items": db["tasklists"]})
    def insert(self, body):
        db = load_mock_db()
        lst_id = "mock_list_" + uuid.uuid4().hex[:6]
        lst = {"id": lst_id, "title": body.get("title", "")}
        db["tasklists"].append(lst)
        save_mock_db(db)
        return MockExecute(lst)

class MockTasksService:
    def tasks(self):
        return MockTasks()
    def tasklists(self):
        return MockTaskLists()

# --- MAIN GET_SERVICE EXPORT ---

def get_google_service(service_name, version):
    """
    Returns an authenticated Google API client service.
    If credentials.json or token.json are not present, transparently falls back to
    a Mock service to allow testing the dashboard without Google Account setup.
    """
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    token_path = os.path.join(config_dir, 'token.json')
    
    # Fallback to Mock Services if credentials are not configured
    if not os.path.exists(token_path):
        print(f"[Google Auth] token.json not found. Using MOCK Mode for '{service_name}' API.")
        if service_name == 'calendar':
            return MockCalendarService()
        elif service_name == 'tasks':
            return MockTasksService()
        else:
            raise ValueError(f"Unknown mock service: {service_name}")

    try:
        creds = Credentials.from_authorized_user_file(token_path)
        
        # Auto-refresh if expired
        if creds and creds.expired and creds.refresh_token:
            print(f"[Google Auth] Refreshing credentials for '{service_name}' API...")
            creds.refresh(Request())
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
                
        if not creds or not creds.valid:
            raise Exception("Credentials invalid")
            
        return build(service_name, version, credentials=creds)
        
    except Exception as err:
        print(f"[Google Auth Warning] Auth failed ({err}). Falling back to MOCK Mode.")
        if service_name == 'calendar':
            return MockCalendarService()
        elif service_name == 'tasks':
            return MockTasksService()
        else:
            raise ValueError(f"Unknown mock service: {service_name}")
