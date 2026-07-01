
from mcp.server.fastmcp import FastMCP
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import uvicorn
import json
import os
import re
import sys
from datetime import datetime, timedelta
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.google_auth import get_google_service

# Initialize FastMCP Server
mcp = FastMCP("calendar-mcp")

def get_calendar_service():
    """Dynamically get the authenticated Google Calendar API service."""
    return get_google_service('calendar', 'v3')

# Helper: resolve relative date strings (e.g. "tomorrow at 10 AM")
def resolve_date_time(date_str):
    if not date_str:
        return datetime.utcnow().isoformat() + 'Z'
        
    lower = date_str.lower().strip()
    now = datetime.now().astimezone()
    
    # Handlers for "today" and "tomorrow"
    if 'today' in lower or 'tomorrow' in lower:
        target_date = now
        if 'tomorrow' in lower:
            target_date += timedelta(days=1)
            
        time_match = re.search(r'(\d+)(?::(\d+))?\s*(am|pm)', lower)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3).lower()
            
            if ampm == 'pm' and hours < 12:
                hours += 12
            if ampm == 'am' and hours == 12:
                hours = 0
            target_date = target_date.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        else:
            target_date = target_date.replace(hour=12, minute=0, second=0, microsecond=0) # Default noon
            
        return target_date.isoformat()
        
    # Handlers for weekdays (e.g. "friday" or "monday")
    days_of_week = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    for idx, day in enumerate(days_of_week):
        if day in lower:
            current_day = now.weekday() # Monday is 0, Sunday is 6
            current_idx = (current_day + 1) % 7 # Map to Sunday=0..Sat=6
            days_to_add = idx - current_idx
            if days_to_add <= 0:
                days_to_add += 7 # Next week's weekday
                
            target_date = now + timedelta(days=days_to_add)
            
            time_match = re.search(r'(\d+)(?::(\d+))?\s*(am|pm)', lower)
            if time_match:
                hours = int(time_match.group(1))
                minutes = int(time_match.group(2)) if time_match.group(2) else 0
                ampm = time_match.group(3).lower()
                
                if ampm == 'pm' and hours < 12:
                    hours += 12
                if ampm == 'am' and hours == 12:
                    hours = 0
                target_date = target_date.replace(hour=hours, minute=minutes, second=0, microsecond=0)
            else:
                target_date = target_date.replace(hour=12, minute=0, second=0, microsecond=0)
                
            return target_date.isoformat()
            
    try:
        # Standard ISO parsing
        parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return parsed.isoformat()
    except Exception:
        pass
        
    return date_str

# Helper: Format ISO date string for display
def format_date_display(date_str):
    if not date_str:
        return ''
    try:
        # Remove timezone offset portion if any for simple display
        clean_str = date_str.split('+')[0].split('Z')[0]
        parsed = datetime.fromisoformat(clean_str)
        return parsed.strftime('%a, %b %d, %Y, %I:%M %p')
    except Exception:
        return date_str

# Helper: Call the Task MCP server tools using an internal client (Automatic MCP-to-MCP)
async def call_task_mcp(tool_name: str, args: dict):
    port = int(os.getenv("PORT", 3000))
    task_url = os.getenv("TASK_MCP_URL", f"http://localhost:{port}/task" if os.getenv("PORT") else "http://localhost:3002")
    print(f"[Calendar MCP Client] Connect to Task MCP at {task_url} to run: {tool_name}...")
    try:
        async with sse_client(f"{task_url}/sse") as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print(f"[Calendar MCP Client] Call: {tool_name} with args: {args}")
                response = await session.call_tool(tool_name, arguments=args)
                raw_text = response.content[0].text
                return json.loads(raw_text)
    except Exception as err:
        print(f"[Calendar MCP Client Error] Communication with Task MCP failed: {err}")
        raise Exception(f"Failed to communicate with Task MCP: {str(err)}")

# Helper: build structured response (JSON + HTML)
def build_response(json_data, html_data):
    return json.dumps({
        "json": json_data,
        "html": html_data
    }, indent=2)

# --- Tool Definitions ---

@mcp.tool()
async def create_event(title: str, start_time: str, end_time: str, description: str = "", reminder_minutes: int = 0, auto_create_task: bool = False) -> str:
    """
    Create a new event in Google Calendar, with options to automatically create a linked task.
    
    Args:
        title: Title of the event.
        start_time: Start time (ISO string or relative like "tomorrow at 10 AM").
        end_time: End time (ISO string or relative like "tomorrow at 11 AM").
        description: Optional description of the event.
        reminder_minutes: Optional reminder offset in minutes (0 for none).
        auto_create_task: If true, automatically call Task MCP to create a preparation task.
    """
    try:
        service = get_calendar_service()
        
        resolved_start = resolve_date_time(start_time)
        # Default end_time to 1 hour after start_time if not specified
        if not end_time:
            try:
                start_dt = datetime.fromisoformat(resolved_start)
                resolved_end = (start_dt + timedelta(hours=1)).isoformat()
            except Exception:
                resolved_end = resolve_date_time(end_time)
        else:
            resolved_end = resolve_date_time(end_time)
        
        event_body = {
            'summary': title,
            'description': description or "",
            'start': {'dateTime': resolved_start},
            'end': {'dateTime': resolved_end}
        }
        
        if reminder_minutes > 0:
            event_body['reminders'] = {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': reminder_minutes}
                ]
            }
            
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        
        task_result = None
        auto_task_html = ""
        
        if auto_create_task:
            try:
                # Call Task MCP to create preparation task
                task_result = await call_task_mcp('create_task', {
                    'title': f"Prepare for: {title}",
                    'due_date': resolved_start.split('T')[0],
                    'description': f"Automated preparation task for event '{title}' scheduled at {format_date_display(resolved_start)}.",
                    'related_event_id': event.get('id')
                })
                
                auto_task_html = f"""
                <div class="mcp-linked-action">
                  <div class="mcp-linked-icon"><i class="icon-link-flow"></i></div>
                  <div class="mcp-linked-content">
                    <h5>Linked Task Created (Via Task MCP)</h5>
                    <p><strong>Task:</strong> {task_result['json']['title']} (ID: {task_result['json']['id']})</p>
                  </div>
                </div>
                """
            except Exception as task_err:
                auto_task_html = f"""
                <div class="mcp-linked-action error-action">
                  <p>Failed to automatically create linked task: {str(task_err)}</p>
                </div>
                """
                
        html = f"""
        <div class="mcp-event-card success-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-event">Event Created</span>
            <span class="mcp-id">{event.get('id')}</span>
          </div>
          <h4 class="mcp-title">{event.get('summary')}</h4>
          <div class="mcp-time-range">
            <div><strong>Start:</strong> {format_date_display(event.get('start', {}).get('dateTime'))}</div>
            <div><strong>End:</strong> {format_date_display(event.get('end', {}).get('dateTime'))}</div>
          </div>
          {f'<p class="mcp-description">{description}</p>' if description else ''}
          <div class="mcp-meta">
            {f'<span class="mcp-meta-item"><i class="icon-bell"></i> Reminder: {reminder_minutes} mins before</span>' if reminder_minutes > 0 else ''}
          </div>
          {auto_task_html}
        </div>
        """
        
        raw_result = {
            "event": {
                "id": event.get('id'),
                "title": event.get('summary'),
                "startTime": event.get('start', {}).get('dateTime'),
                "endTime": event.get('end', {}).get('dateTime'),
                "description": description,
                "reminderMinutes": reminder_minutes
            },
            "taskResult": task_result
        }
        return build_response(raw_result, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error creating Google Calendar Event</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
async def update_event(id: str, title: str = None, start_time: str = None, end_time: str = None, description: str = None, reminder_minutes: int = None, auto_update_task: bool = False) -> str:
    """
    Update details of an existing event in Google Calendar, with option to update related tasks.
    
    Args:
        id: The unique Google Calendar Event ID.
        title: New event title.
        start_time: New start time.
        end_time: New end time.
        description: New description.
        reminder_minutes: New reminder offset in minutes (0 to remove).
        auto_update_task: If true, automatically update the due date of any linked tasks in Task MCP.
    """
    try:
        service = get_calendar_service()
        
        event_body = {}
        if title is not None:
            event_body['summary'] = title
        if description is not None:
            event_body['description'] = description
        if start_time is not None:
            event_body['start'] = {'dateTime': resolve_date_time(start_time)}
        if end_time is not None:
            event_body['end'] = {'dateTime': resolve_date_time(end_time)}
            
        if reminder_minutes is not None:
            if reminder_minutes > 0:
                event_body['reminders'] = {
                    'useDefault': False,
                    'overrides': [{'method': 'popup', 'minutes': reminder_minutes}]
                }
            else:
                event_body['reminders'] = {'useDefault': True}
                
        updated = service.events().patch(calendarId='primary', eventId=id, body=event_body).execute()
        
        task_result = None
        auto_task_html = ""
        
        if auto_update_task:
            try:
                # Find linked tasks in Task MCP
                list_res = await call_task_mcp('list_tasks', {
                    'status': 'all',
                    'related_event_id': id
                })
                linked_tasks = list_res['json']
                
                if linked_tasks:
                    task_updates = []
                    new_due_date = updated.get('start', {}).get('dateTime', '').split('T')[0]
                    for task in linked_tasks:
                        up_res = await call_task_mcp('update_task', {
                            'id': task['id'],
                            'due_date': new_due_date
                        })
                        task_updates.append(up_res['json'])
                    task_result = task_updates
                    auto_task_html = f"""
                    <div class="mcp-linked-action">
                      <div class="mcp-linked-icon"><i class="icon-link-flow"></i></div>
                      <div class="mcp-linked-content">
                        <h5>Linked Tasks Updated (Via Task MCP)</h5>
                        <p>Synchronized due dates for {len(linked_tasks)} task(s) to match new event time.</p>
                      </div>
                    </div>
                    """
                else:
                    auto_task_html = """
                    <div class="mcp-linked-action warning-action">
                      <p>No linked tasks were found to update.</p>
                    </div>
                    """
            except Exception as task_err:
                auto_task_html = f"""
                <div class="mcp-linked-action error-action">
                  <p>Failed to automatically update linked tasks: {str(task_err)}</p>
                </div>
                """
                
        html = f"""
        <div class="mcp-event-card info-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-event">Event Updated</span>
            <span class="mcp-id">{updated.get('id')}</span>
          </div>
          <h4 class="mcp-title">{updated.get('summary')}</h4>
          <div class="mcp-time-range">
            <div><strong>Start:</strong> {format_date_display(updated.get('start', {}).get('dateTime'))}</div>
            <div><strong>End:</strong> {format_date_display(updated.get('end', {}).get('dateTime'))}</div>
          </div>
          {f'<p class="mcp-description">{updated.get("description", "")}</p>' if updated.get("description") else ''}
          {auto_task_html}
        </div>
        """
        
        raw_result = {
            "event": {
                "id": updated.get('id'),
                "title": updated.get('summary'),
                "startTime": updated.get('start', {}).get('dateTime'),
                "endTime": updated.get('end', {}).get('dateTime'),
                "description": updated.get('description', '')
            },
            "taskResult": task_result
        }
        return build_response(raw_result, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error updating event</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
async def delete_event(id: str, auto_delete_task: bool = False) -> str:
    """
    Delete a Google Calendar Event by its unique ID.
    
    Args:
        id: Unique ID of the event to delete.
        auto_delete_task: If true, automatically delete all tasks linked to this event in Task MCP.
    """
    try:
        service = get_calendar_service()
        
        # Load event summary for confirmation message
        event = service.events().get(calendarId='primary', eventId=id).execute()
        service.events().delete(calendarId='primary', eventId=id).execute()
        
        task_result = None
        auto_task_html = ""
        
        if auto_delete_task:
            try:
                # Find linked tasks in Task MCP
                list_res = await call_task_mcp('list_tasks', {
                    'status': 'all',
                    'related_event_id': id
                })
                linked_tasks = list_res['json']
                
                if linked_tasks:
                    deleted_ids = []
                    for task in linked_tasks:
                        await call_task_mcp('delete_task', {'id': task['id']})
                        deleted_ids.append(task['id'])
                    task_result = deleted_ids
                    auto_task_html = f"""
                    <div class="mcp-linked-action">
                      <div class="mcp-linked-icon"><i class="icon-link-flow"></i></div>
                      <div class="mcp-linked-content">
                        <h5>Linked Tasks Deleted (Via Task MCP)</h5>
                        <p>Permanently deleted {len(linked_tasks)} task(s) linked to this event.</p>
                      </div>
                    </div>
                    """
                else:
                    auto_task_html = """
                    <div class="mcp-linked-action warning-action">
                      <p>No linked tasks were found to delete.</p>
                    </div>
                    """
            except Exception as task_err:
                auto_task_html = f"""
                <div class="mcp-linked-action error-action">
                  <p>Failed to automatically delete linked tasks: {str(task_err)}</p>
                </div>
                """
                
        html = f"""
        <div class="mcp-event-card delete-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-deleted">Deleted</span>
            <span class="mcp-id">{id}</span>
          </div>
          <h4 class="mcp-title">{event.get('summary')}</h4>
          <p class="mcp-feedback">Event has been permanently deleted from Google Calendar.</p>
          {auto_task_html}
        </div>
        """
        return build_response({"id": id, "deleted": True, "taskResult": task_result}, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error deleting event</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def get_events(date: str = "", query: str = "") -> str:
    """
    Get calendar events from Google Calendar, optionally filtered by date or query.
    
    Args:
        date: Filter events for a specific date (YYYY-MM-DD format or "today", "tomorrow").
        query: Search term to filter events by title or description.
    """
    try:
        service = get_calendar_service()
        
        # Calculate time range
        time_min = None
        time_max = None
        
        if date:
            resolved_date = resolve_date_time(date).split('T')[0]
            dt_min = datetime.strptime(resolved_date, '%Y-%m-%d')
            dt_max = dt_min + timedelta(days=1)
            
            time_min = dt_min.isoformat() + 'Z'
            time_max = dt_max.isoformat() + 'Z'
        else:
            # Default to list events starting from current moment
            time_min = datetime.utcnow().isoformat() + 'Z'
            
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            q=query or None,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        parsed_events = []
        for e in events:
            parsed_events.append({
                "id": e.get('id'),
                "title": e.get('summary'),
                "startTime": e.get('start', {}).get('dateTime') or e.get('start', {}).get('date'),
                "endTime": e.get('end', {}).get('dateTime') or e.get('end', {}).get('date'),
                "description": e.get('description', '')
            })
            
        if not parsed_events:
            list_html = '<p class="mcp-empty">No events found matching current filters.</p>'
        else:
            list_items = []
            for pe in parsed_events:
                list_items.append(f"""
                  <div class="mcp-list-item">
                    <div class="mcp-list-item-header">
                      <span class="mcp-badge badge-event">EVENT</span>
                      <span class="mcp-id-small">{pe['id']}</span>
                    </div>
                    <div class="mcp-list-item-body">
                      <strong>{pe['title']}</strong>
                      <p>{format_date_display(pe['startTime'])} - {format_date_display(pe['endTime'])}</p>
                      {f"<p class='mcp-list-item-desc'>{pe['description']}</p>" if pe['description'] else ''}
                    </div>
                  </div>
                """)
            list_html = f'<div class="mcp-list">{"".join(list_items)}</div>'
            
        html = f"""
        <div class="mcp-event-list-container">
          <h4 class="mcp-list-title">Google Calendar Events (Filter: {date or 'all'}{f', Search: "{query}"' if query else ''})</h4>
          {list_html}
        </div>
        """
        return build_response(parsed_events, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error listing events</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

@mcp.tool()
def set_reminder(event_id: str, minutes_before: int) -> str:
    """
    Set a popup reminder for a Google Calendar event.
    
    Args:
        event_id: The unique Google Calendar Event ID.
        minutes_before: Minutes before the event to trigger the reminder.
    """
    try:
        service = get_calendar_service()
        
        event_body = {
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': minutes_before}
                ]
            }
        }
        
        updated = service.events().patch(calendarId='primary', eventId=event_id, body=event_body).execute()
        
        html = f"""
        <div class="mcp-event-card info-card">
          <div class="mcp-card-header">
            <span class="mcp-badge badge-reminder">Reminder Set</span>
            <span class="mcp-id">{updated.get('id')}</span>
          </div>
          <h4 class="mcp-title">{updated.get('summary')}</h4>
          <p class="mcp-feedback"><i class="icon-bell"></i> A reminder has been set for <strong>{minutes_before} minutes</strong> before the start time.</p>
          <div class="mcp-time-range">
            <div><strong>Event Time:</strong> {format_date_display(updated.get('start', {}).get('dateTime'))}</div>
          </div>
        </div>
        """
        return build_response({
            "id": updated.get('id'),
            "title": updated.get('summary'),
            "reminderMinutes": minutes_before
        }, html)
        
    except Exception as e:
        error_html = f'<div class="mcp-error-card"><h4>Error setting reminder</h4><p>{str(e)}</p></div>'
        return build_response({"error": str(e)}, error_html)

# Express-like SSE Endpoint configuration
app = mcp.sse_app()

if __name__ == '__main__':
    # Run the server on port 3001
    print("[Calendar MCP] Starting Google Calendar MCP SSE server on port 3001...")
    uvicorn.run("server:app", host="0.0.0.0", port=3001, log_level="info")
