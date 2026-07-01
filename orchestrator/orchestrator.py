from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
import httpx
import anyio
from datetime import datetime
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

# Setup directories
current_dir = os.path.dirname(__file__)
workspace_root = os.path.abspath(os.path.join(current_dir, '..'))
frontend_dir = os.path.join(workspace_root, 'frontend')
logs_dir = os.path.join(workspace_root, 'logs')
config_path = os.path.join(workspace_root, 'config', 'config.json')

import os
os.environ["PORT"] = os.getenv("PORT", "3000")

import sys
sys.path.append(workspace_root)
from calendar_mcp.server import app as calendar_app
from task_mcp.server import app as task_app

# Create logs directory if it doesn't exist
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir, exist_ok=True)

# Load configuration
config = {
    "llmProvider": "ollama",
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "llama3.2"
    },
    "groq": {
        "host": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "apiKey": ""
    },
    "servers": {
        "calendar": {
            "port": 3001,
            "url": "http://localhost:3001"
        },
        "task": {
            "port": 3002,
            "url": "http://localhost:3002"
        }
    }
}

if os.path.exists(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("[Orchestrator] Configuration loaded successfully.")
    except Exception as err:
        print(f"[Orchestrator Warning] Error reading config, using defaults: {err}")

# Cached server tool lists
calendar_tools = []
task_tools = []
calendar_connected = False
task_connected = False

# FastAPI instantiation
app = FastAPI()

# Mount MCP sub-apps
app.mount("/calendar", calendar_app)
app.mount("/task", task_app)

# Dynamically route server URLs to mounted endpoints (supports single-port cloud deployment)
port = int(os.getenv("PORT", 3000))
base_url = f"http://localhost:{port}"
config['servers']['calendar']['url'] = f"{base_url}/calendar"
config['servers']['task']['url'] = f"{base_url}/task"

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def fetch_tools_from_server(sse_url: str):
    """Connect to SSE endpoint, list tools, and return them."""
    try:
        async with sse_client(f"{sse_url}/sse") as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                # Extract and dump schemas
                serializable_tools = []
                for tool in tools_result.tools:
                    serializable_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    })
                return serializable_tools
    except Exception as err:
        print(f"[Orchestrator Warning] Failed to connect to server at {sse_url}: {err}")
        raise err

async def update_mcp_status():
    """Retrieve and update cached status and tool definitions from both servers."""
    global calendar_tools, task_tools, calendar_connected, task_connected
    
    # Check Calendar
    try:
        calendar_tools = await fetch_tools_from_server(config['servers']['calendar']['url'])
        calendar_connected = True
        print(f"[Orchestrator] Connected to Calendar MCP. Loaded {len(calendar_tools)} tools.")
    except Exception:
        calendar_tools = []
        calendar_connected = False

    # Check Task
    try:
        task_tools = await fetch_tools_from_server(config['servers']['task']['url'])
        task_connected = True
        print(f"[Orchestrator] Connected to Task MCP. Loaded {len(task_tools)} tools.")
    except Exception:
        task_tools = []
        task_connected = False

# Startup Event
@app.on_event("startup")
async def startup_event():
    # Attempt initial connections in background after uvicorn starts up and binds
    import asyncio
    async def delayed_status_update():
        await asyncio.sleep(1.5)
        try:
            await update_mcp_status()
        except Exception as e:
            print(f"[Orchestrator Warning] Delayed status update failed: {e}")
            
    asyncio.create_task(delayed_status_update())

# Helper: Convert MCP Tool schema to OpenAI Function format
def mcp_tools_to_openai(tools_list):
    openai_tools = []
    for t in tools_list:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"]
            }
        })
    return openai_tools

# --- REST Endpoints ---

@app.get('/api/status')
async def get_status():
    global calendar_connected, task_connected
    
    # Auto-reconnect if offline
    if not calendar_connected or not task_connected:
        try:
            await update_mcp_status()
        except Exception:
            pass

    return {
        "calendar": {
            "connected": calendar_connected,
            "url": config["servers"]["calendar"]["url"],
            "tools": [t["name"] for t in calendar_tools]
        },
        "task": {
            "connected": task_connected,
            "url": config["servers"]["task"]["url"],
            "tools": [t["name"] for t in task_tools]
        },
        "llm": {
            "provider": config["llmProvider"],
            "model": config["ollama"]["model"] if config["llmProvider"] == "ollama" else config["groq"]["model"]
        }
    }

@app.post('/api/reconnect')
async def reconnect_servers():
    print("[Orchestrator] Reconnecting MCP servers...")
    await update_mcp_status()
    return {
        "calendar": "Connected" if calendar_connected else "Offline",
        "task": "Connected" if task_connected else "Offline"
    }

@app.post('/api/config')
async def save_config(body: dict = Body(...)):
    global config
    provider = body.get('llmProvider')
    ollama_model = body.get('ollamaModel')
    groq_model = body.get('groqModel')
    groq_api_key = body.get('groqApiKey')
    
    if provider:
        config['llmProvider'] = provider
    if ollama_model:
        config['ollama']['model'] = ollama_model
    if groq_model:
        config['groq']['model'] = groq_model
    if groq_api_key is not None:
        config['groq']['apiKey'] = groq_api_key
        
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print("[Orchestrator] Config updated and saved.")
        return {"success": True, "config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_mcp_tool(server_url: str, tool_name: str, args: dict):
    """Connects to server, executes tool, and returns raw result string."""
    async with sse_client(f"{server_url}/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=args)
            return result.content[0].text

@app.post('/api/chat')
async def chat_handler(body: dict = Body(...)):
    prompt = body.get('prompt')
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    print(f"\n--- NEW PYTHON WORKFLOW: '{prompt}' ---")
    
    workflow_start_time = datetime.now()
    timeline = []
    execution_logs = []
    
    # Auto-reconnect if offline
    global calendar_connected, task_connected
    if not calendar_connected or not task_connected:
        try:
            await update_mcp_status()
        except Exception:
            pass
            
    active_tools = []
    active_tools.extend(calendar_tools)
    active_tools.extend(task_tools)
    
    system_content = f"""You are a helpful AI Calendar and Task Assistant. 
You have access to a Calendar MCP server and a Task MCP server.
You should decide which tools to call based on the user request.
Whenever you schedule a meeting, you can check if you need to create a task as well. 

Note on Tool Parameters:
- Calendar tools: create_event, update_event, delete_event, get_events, set_reminder
- Task tools: create_task, update_task, delete_task, list_tasks, mark_task_complete

If the user wants to perform related actions automatically in a single call (e.g. "Schedule a meeting and automatically create a preparation task"), you should call "create_event" with "auto_create_task: true". The Calendar server will handle calling the Task server internally.
Similarly:
- "Move my meeting and update the task deadline" -> Call "update_event" with "auto_update_task: true".
- "Delete the meeting and remove its preparation task" -> Call "delete_event" with "auto_delete_task: true".

CRITICAL: If a task has already been automatically created, updated, or deleted as part of an automatic Calendar tool call (e.g., via auto_create_task=true, auto_update_task=true, or auto_delete_task=true), you must NOT call the Task tools (create_task, update_task, delete_task) again in a subsequent step. The task has already been processed.

If the user requests BOTH explicitly in a way that requires separate custom parameters (e.g., specific custom titles or descriptions), call the tools sequentially.
Otherwise, use the automatic flags to demonstrate the MCP-to-MCP link.

Always try to respond to the user based on tool outputs. Current date-time reference: {datetime.now().isoformat()}"""

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt}
    ]

    timeline.append({
        "title": "User Prompt",
        "description": f"Received prompt: \"{prompt}\"",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type": "prompt"
    })

    loop_count = 0
    max_loops = 10
    final_response_text = ""
    final_json_responses = {}

    try:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            while loop_count < max_loops:
                loop_count += 1
                timeline.append({
                    "title": "LLM Decision",
                    "description": f"Running step {loop_count} to determine tool invocation or response.",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "type": "llm_decision"
                })

                # Prepare Payload
                openai_tools = mcp_tools_to_openai(active_tools)
                provider = config["llmProvider"]
                
                llm_response = None
                
                if provider == "ollama":
                    ollama_url = f"{config['ollama']['host']}/api/chat"
                    payload = {
                        "model": config["ollama"]["model"],
                        "messages": messages,
                        "stream": False
                    }
                    if openai_tools:
                        payload["tools"] = openai_tools
                        
                    print(f"[Orchestrator] Calling Ollama ({config['ollama']['model']})...")
                    res = await http_client.post(ollama_url, json=payload)
                    if res.status_code != 200:
                        raise Exception(f"Ollama request failed: {res.text}")
                    data = res.json()
                    llm_response = data["message"]
                    
                elif provider == "groq":
                    groq_url = f"{config['groq']['host']}/chat/completions"
                    api_key = config["groq"]["apiKey"] or os.getenv("GROQ_API_KEY")
                    if not api_key:
                        raise Exception("Groq API Key not found in config or env.")
                        
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": config["groq"]["model"],
                        "messages": messages,
                        "stream": False
                    }
                    if openai_tools:
                        payload["tools"] = openai_tools
                        
                    print(f"[Orchestrator] Calling Groq ({config['groq']['model']})...")
                    res = await http_client.post(groq_url, json=payload, headers=headers)
                    if res.status_code != 200:
                        raise Exception(f"Groq request failed: {res.text}")
                    data = res.json()
                    llm_response = data["choices"][0]["message"]
                else:
                    raise Exception(f"Unsupported LLM provider: {provider}")

                # Save response to chat history
                # Keep only fields compatible with completions payload
                history_message = {"role": "assistant", "content": llm_response.get("content") or ""}
                if "tool_calls" in llm_response and llm_response["tool_calls"]:
                    history_message["tool_calls"] = llm_response["tool_calls"]
                messages.append(history_message)

                # Process Tool Calls
                tool_calls = llm_response.get("tool_calls", [])
                if tool_calls:
                    print(f"[Orchestrator] LLM requested {len(tool_calls)} tool call(s).")
                    for tc in tool_calls:
                        fn = tc["function"]
                        tool_name = fn["name"]
                        args = fn["arguments"]
                        if isinstance(args, str):
                            args = json.loads(args)

                        timeline.append({
                            "title": f"Tool Requested: {tool_name}",
                            "description": f"LLM requested tool call with arguments: {json.dumps(args)}",
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "type": "tool_request"
                        })

                        # Identify server
                        is_calendar = any(t["name"] == tool_name for t in calendar_tools)
                        is_task = any(t["name"] == tool_name for t in task_tools)
                        
                        server_name = "Unknown"
                        server_url = ""
                        tool_description = ""
                        
                        if is_calendar:
                            server_name = "calendar-mcp"
                            server_url = config['servers']['calendar']['url']
                            tool_description = next((t["description"] for t in calendar_tools if t["name"] == tool_name), "")
                        elif is_task:
                            server_name = "task-mcp"
                            server_url = config['servers']['task']['url']
                            tool_description = next((t["description"] for t in task_tools if t["name"] == tool_name), "")

                        tool_start = datetime.now()
                        tool_result_str = ""
                        success = False
                        
                        try:
                            if not server_url:
                                raise Exception(f"Server for tool {tool_name} not found or offline.")
                            print(f"[Orchestrator] Invoking tool {tool_name} on {server_name}...")
                            tool_result_str = await execute_mcp_tool(server_url, tool_name, args)
                            success = True
                        except Exception as tool_err:
                            print(f"[Orchestrator] Tool execution error: {tool_err}")
                            tool_result_str = json.dumps({"error": str(tool_err)})
                            success = False

                        tool_duration = int((datetime.now() - tool_start).total_seconds() * 1000)
                        
                        # Parse Tool Response
                        parsed_res = {"json": {"error": "Invalid output format"}, "html": "<div>Error</div>"}
                        try:
                            parsed_res = json.loads(tool_result_str)
                        except Exception:
                            parsed_res = {"json": {"rawText": tool_result_str}, "html": f"<div>{tool_result_str}</div>"}

                        # Record log
                        execution_logs.append({
                            "mcpServer": server_name,
                            "toolName": tool_name,
                            "description": tool_description,
                            "inputParameters": args,
                            "output": parsed_res,
                            "startTime": tool_start.isoformat(),
                            "endTime": datetime.now().isoformat(),
                            "durationMs": tool_duration,
                            "success": success
                        })

                        if server_name not in final_json_responses:
                            final_json_responses[server_name] = []
                        final_json_responses[server_name].append(parsed_res.get("json"))

                        # Feed tool response back to LLM
                        messages.append({
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": tc.get("id") or f"call_{int(datetime.now().timestamp())}",
                            "content": tool_result_str
                        })

                        timeline.append({
                            "title": f"Tool Finished: {tool_name}",
                            "description": f"Completed in {tool_duration}ms. Status: {'Success' if success else 'Failure'}",
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "type": "tool_response"
                        })
                else:
                    # Final Text Response
                    print("[Orchestrator] LLM returned final text response.")
                    final_response_text = llm_response.get("content") or ""
                    timeline.append({
                        "title": "Combined Response Generated",
                        "description": "LLM generated final response integrating all tool execution results.",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "type": "final_response"
                    })
                    break
                    
    except Exception as workflow_err:
        print(f"[Orchestrator Error] Agent workflow crash: {workflow_err}")
        final_response_text = f"Error during workflow: {str(workflow_err)}"
        timeline.append({
            "title": "Workflow Error",
            "description": str(workflow_err),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "error"
        })

    duration_ms = int((datetime.now() - workflow_start_time).total_seconds() * 1000)

    # Save Log
    log_content = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "prompt": prompt,
        "provider": config["llmProvider"],
        "model": config["ollama"]["model"] if config["llmProvider"] == "ollama" else config["groq"]["model"],
        "totalDurationMs": duration_ms,
        "finalResponse": final_response_text,
        "timeline": timeline,
        "toolExecutions": execution_logs,
        "rawJsonResponsesByServer": final_json_responses,
        "fullConversationHistory": messages
    }
    
    log_filename = f"run_{int(datetime.now().timestamp())}_{os.urandom(2).hex()}.json"
    try:
        with open(os.path.join(logs_dir, log_filename), 'w', encoding='utf-8') as lf:
            json.dump(log_content, lf, indent=2)
        print(f"[Orchestrator] Saved run details to logs/{log_filename}")
    except Exception as log_err:
        print(f"[Orchestrator Error] Failed to write log file: {log_err}")

    return {
        "aiResponse": final_response_text,
        "timeline": timeline,
        "toolExecutions": execution_logs,
        "rawJsonResponses": final_json_responses,
        "totalDurationMs": duration_ms
    }

@app.get('/api/logs')
async def get_logs_list():
    try:
        files_list = []
        for f in os.listdir(logs_dir):
            if f.startswith('run_') and f.endswith('.json'):
                fpath = os.path.join(logs_dir, f)
                with open(fpath, 'r', encoding='utf-8') as lf:
                    content = json.load(lf)
                files_list.append({
                    "filename": f,
                    "timestamp": content.get("timestamp"),
                    "prompt": content.get("prompt"),
                    "durationMs": content.get("totalDurationMs"),
                    "toolsUsed": [t["toolName"] for t in content.get("toolExecutions", [])]
                })
        # Sort logs by timestamp descending
        files_list.sort(key=lambda x: x["timestamp"], reverse=True)
        return files_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/logs/{filename}')
async def get_single_log(filename: str):
    fpath = os.path.join(logs_dir, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        with open(fpath, 'r', encoding='utf-8') as lf:
            return json.load(lf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount Frontend dashboard Static files (Must be mounted last so API routes are parsed first!)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == '__main__':
    port = int(os.getenv("PORT", 3000))
    print(f"[Orchestrator] Launching FastAPI backend on port {port}...")
    uvicorn.run("orchestrator:app", host="0.0.0.0", port=port, log_level="info")
