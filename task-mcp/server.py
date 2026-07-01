from mcp.server.fastmcp import FastMCP
import uvicorn
import json
import sys
import os
from datetime import datetime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.google_auth import get_google_service

# Initialize FastMCP Server
mcp = FastMCP("task-mcp")

def get_tasks_service():
    """Dynamically get the authenticated Google Tasks API service."""
    return get_google_service('tasks', 'v1')

def get_or_create_tasklist(service):
    """Retrieves the ID of the 'MCP Tasks' list, creating it if it doesn't exist."""
    try:
        lists_result = service.tasklists().list().execute()
        lists = lists_result.get('items', [])
        
        # Look for "MCP Tasks"
        for lst in lists:
            if lst.get('title') == 'MCP Tasks':
                return lst.get('id')
                
        # Create it if not found
        new_list = service.tasklists().insert(body={'title': 'MCP Tasks'}).execute()
        return new_list.get('id')
    except Exception as err:
        print(f"[Task MCP Warning] Failed to find or create 'MCP Tasks' list, falling back to default: {err}")
        return '@default'

def format_due_date(date_str):
    """Formats raw date strings into Google Tasks compliant RFC 3339 format (YYYY-MM-DDT00:00:00.000Z)."""
    if not date_str:
        return None
    try:
        # Standardize ISO date
        parsed_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return parsed_date.strftime('%Y-%m-%dT00:00:00.000Z')
    except Exception:
        # Fallback to date portion if simple YYYY-MM-DD
        if len(date_str) >= 10:
            return f"{date_str[:10]}T00:00:00.000Z"
        return None

def formatDateDisplay(date_str):
    """Nicely formats Google Tasks RFC 3339 due dates for HTML rendering."""
    if not date_str:
        return 'No due date'
    try:
        parsed = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
        return parsed.strftime('%a, %b %d, %Y')
    except Exception:
        return date_str

def build_response(json_data, html_data):
    """Format combined response for Orchestrator and UI."""
    return json.dumps({
        "json": json_data,
        "html": html_data
    }, indent=2)

# --- Tool Definitions ---

@mcp.tool()
def create_task(title: str, due_date: str = "", description: str = "", related_event_id: str = "") -> str:
    """
    Create a new task in Google Tasks.
    
    Args:
        title: The name/title of the task.
        due_date: Optional due date (YYYY-MM-DD format).
        description: Optional notes or description of the task.
        related_event_id: Optional ID of a google calendar event to link this task to.
    """
    try:
        service = get_tasks_service()
        tasklist_id = get_or_create_tasklist(service)
        
        # Append related event ID into notes for filtering
        notes = description or ""
        if related_event_id:
            notes = f"[Event ID: {related_event_id}]\n" + notes
            
        task_body = {
            'title': title,
            'notes': notes
        }
        
        formatted_due = format_due_date(due_date)
        if formatted_due:
            task_body['due'] = formatted_due
            
        task = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        
        html = f"""
        <div class="mcp-task-card success-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-pending">Pending</span>
            <span class="mcp-id">{task.get('id')}</span>
          </div>
          <h4 class="mcp-title">{task.get('title')}</h4>
          {f'<p class="mcp-description">{description}</p>' if description else ''}
          <div class="mcp-meta">
            <span class="mcp-meta-item"><i class="icon-calendar"></i> Due: {formatDateDisplay(task.get('due'))}</span>
            {f'<span class="mcp-meta-item"><i class="icon-link"></i> Linked Event: {related_event_id}</span>' if related_event_id else ''}
          </div>
        </div>
        """
        
        # Format response data
        raw_result = {
            "id": task.get('id'),
            "title": task.get('title'),
            "status": "pending",
            "dueDate": task.get('due'),
            "description": description,
            "relatedEventId": related_event_id
        }
        return build_response(raw_result, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error creating task</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def update_task(id: str, title: str = None, due_date: str = None, description: str = None, status: str = None) -> str:
    """
    Update details of an existing task in Google Tasks.
    
    Args:
        id: The unique ID of the task.
        title: New task title.
        due_date: New due date (YYYY-MM-DD).
        description: New description/notes.
        status: Task status ('needsAction' or 'completed').
    """
    try:
        service = get_tasks_service()
        tasklist_id = get_or_create_tasklist(service)
        
        # Load existing task first to preserve linked event ID in notes
        existing = service.tasks().get(tasklist=tasklist_id, task=id).execute()
        notes = existing.get('notes', '')
        
        # Extract event ID if present
        related_event_id = ""
        if notes.startswith("[Event ID: "):
            end_idx = notes.find("]")
            if end_idx != -1:
                related_event_id = notes[11:end_idx]
        
        task_body = {}
        if title is not None:
            task_body['title'] = title
            
        if description is not None:
            # Preserve event ID in notes if it exists
            if related_event_id:
                task_body['notes'] = f"[Event ID: {related_event_id}]\n" + description
            else:
                task_body['notes'] = description
                
        if status is not None:
            # Google Tasks uses 'needsAction' for pending, and 'completed' for completed
            google_status = 'completed' if status == 'completed' else 'needsAction'
            task_body['status'] = google_status
            
        if due_date is not None:
            formatted_due = format_due_date(due_date)
            if formatted_due:
                task_body['due'] = formatted_due
                
        updated = service.tasks().patch(tasklist=tasklist_id, task=id, body=task_body).execute()
        
        display_status = "COMPLETED" if updated.get('status') == 'completed' else "PENDING"
        badge_class = "badge-completed" if display_status == "COMPLETED" else "badge-pending"
        card_class = "success-card" if display_status == "COMPLETED" else "info-card"
        title_class = "line-through" if display_status == "COMPLETED" else ""
        
        # Clean notes text for display
        clean_desc = updated.get('notes', '')
        if clean_desc.startswith("[Event ID: "):
            end_idx = clean_desc.find("]")
            if end_idx != -1:
                clean_desc = clean_desc[end_idx+1:].strip()
                
        html = f"""
        <div class="mcp-task-card {card_class}">
          <div class="mcp-card-header">
            <span class="mcp-badge {badge_class}">{display_status}</span>
            <span class="mcp-id">{updated.get('id')}</span>
          </div>
          <h4 class="mcp-title {title_class}">{updated.get('title')}</h4>
          {f'<p class="mcp-description">{clean_desc}</p>' if clean_desc else ''}
          <div class="mcp-meta">
            <span class="mcp-meta-item"><i class="icon-calendar"></i> Due: {formatDateDisplay(updated.get('due'))}</span>
            {f'<span class="mcp-meta-item"><i class="icon-link"></i> Linked Event: {related_event_id}</span>' if related_event_id else ''}
          </div>
        </div>
        """
        
        raw_result = {
            "id": updated.get('id'),
            "title": updated.get('title'),
            "status": "completed" if updated.get('status') == 'completed' else "pending",
            "dueDate": updated.get('due'),
            "description": clean_desc,
            "relatedEventId": related_event_id
        }
        return build_response(raw_result, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error updating task</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def delete_task(id: str) -> str:
    """
    Delete a task by its unique ID in Google Tasks.
    
    Args:
        id: The unique ID of the task to delete.
    """
    try:
        service = get_tasks_service()
        tasklist_id = get_or_create_tasklist(service)
        
        service.tasks().delete(tasklist=tasklist_id, task=id).execute()
        
        html = f"""
        <div class="mcp-task-card delete-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-deleted">Deleted</span>
            <span class="mcp-id">{id}</span>
          </div>
          <p class="mcp-feedback">Task has been permanently deleted from Google Tasks.</p>
        </div>
        """
        return build_response({"id": id, "deleted": True}, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error deleting task</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def list_tasks(status: str = "all", related_event_id: str = "") -> str:
    """
    List tasks from Google Tasks, optionally filtered by status or related Calendar Event ID.
    
    Args:
        status: Filter tasks by status ('pending', 'completed', or 'all').
        related_event_id: Filter tasks linked to a specific event ID.
    """
    try:
        service = get_tasks_service()
        tasklist_id = get_or_create_tasklist(service)
        
        # Retrieve tasks list
        tasks_result = service.tasks().list(tasklist=tasklist_id, showCompleted=True, showHidden=True).execute()
        tasks = tasks_result.get('items', [])
        
        parsed_tasks = []
        for t in tasks:
            notes = t.get('notes', '')
            
            # Extract related event ID if present
            ref_id = ""
            clean_desc = notes
            if notes.startswith("[Event ID: "):
                end_idx = notes.find("]")
                if end_idx != -1:
                    ref_id = notes[11:end_idx]
                    clean_desc = notes[end_idx+1:].strip()
            
            # Apply relatedEventId filter
            if related_event_id and ref_id != related_event_id:
                continue
                
            task_status = "completed" if t.get('status') == 'completed' else "pending"
            
            # Apply status filter
            if status == 'pending' and task_status != 'pending':
                continue
            if status == 'completed' and task_status != 'completed':
                continue
                
            parsed_tasks.append({
                "id": t.get('id'),
                "title": t.get('title'),
                "status": task_status,
                "dueDate": t.get('due', ''),
                "description": clean_desc,
                "relatedEventId": ref_id
            })
            
        # Build HTML list
        if not parsed_tasks:
            list_html = '<p class="mcp-empty">No tasks found matching current filters.</p>'
        else:
            list_items = []
            for pt in parsed_tasks:
                badge_class = "badge-completed" if pt['status'] == 'completed' else "badge-pending"
                list_items.append(f"""
                  <div class="mcp-list-item">
                    <div class="mcp-list-item-header">
                      <span class="mcp-badge {badge_class}">{pt['status']}</span>
                      <span class="mcp-id-small">{pt['id']}</span>
                    </div>
                    <div class="mcp-list-item-body">
                      <strong>{pt['title']}</strong>
                      {f"<p>{pt['description']}</p>" if pt['description'] else ''}
                    </div>
                    <div class="mcp-list-item-footer">
                      <span>Due: {formatDateDisplay(pt['dueDate'])}</span>
                      {f"<span>Event: {pt['relatedEventId']}</span>" if pt['relatedEventId'] else ''}
                    </div>
                  </div>
                """)
            list_html = f'<div class="mcp-list">{"".join(list_items)}</div>'
            
        html = f"""
        <div class="mcp-task-list-container">
          <h4 class="mcp-list-title">Google Tasks (Filter: {status}{f', Event: {related_event_id}' if related_event_id else ''})</h4>
          {list_html}
        </div>
        """
        return build_response(parsed_tasks, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error listing tasks</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def mark_task_complete(id: str) -> str:
    """
    Mark a task as completed in Google Tasks.
    
    Args:
        id: The unique ID of the task to mark as complete.
    """
    return update_task(id=id, status="completed")

# Express-like SSE Endpoint configuration
app = mcp.sse_app()

if __name__ == '__main__':
    # Run the server on port 3002
    print("[Task MCP] Starting Google Tasks MCP SSE server on port 3002...")
    uvicorn.run("server:app", host="0.0.0.0", port=3002, log_level="info")
