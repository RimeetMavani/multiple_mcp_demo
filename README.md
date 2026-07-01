# 🌐 Multi-MCP Agent System with Google Calendar & Google Tasks

A production-style implementation of the **Model Context Protocol (MCP)**, featuring two independent Python-based MCP servers integrated with the real **Google Calendar API** and **Google Tasks API**. 

The system leverages a local LLM (**Ollama/Groq**) inside an agentic orchestration loop and displays the entire tool execution timeline on a premium, dark-neon glassmorphic web dashboard.

---

## 🏗️ System Architecture & Data Flow

Below is the horizontal architecture mapping out the data flow from the User Interface, through the MCP Host, down to the LLM, the MCP servers, and the Google Cloud APIs:

```mermaid
graph LR
    %% Styling
    classDef main fill:#0f111a,stroke:#a259ff,stroke-width:2px,color:#fff;
    classDef orange fill:#221b1b,stroke:#ff6f43,stroke-width:1px,color:#fff;
    classDef blue fill:#18202b,stroke:#00e5ff,stroke-width:1px,color:#fff;
    classDef green fill:#0d1c16,stroke:#00e676,stroke-width:1px,color:#fff;

    Input([User Prompt Input]) -->|1. Submit text| Host

    subgraph Host ["MCP Host (Orchestrator - Port 3000)"]
        direction TB
        ServerStatus[Status Checker]
        LoopController[Agent Execution Loop]
        JSONLogger[(run_logs.json)]
    end
    class Host main;

    subgraph LLM ["LLM (Ollama / Groq)"]
        direction TB
        Reasoning[1. Understand request]
        ToolSelect[2. Select Tool & parameters]
    end
    class LLM main;

    Host <-->|2. Reasoning & Tool Selection| LLM

    subgraph CalServer ["Calendar MCP Server (Port 3001)"]
        direction TB
        c1["<b>create_event</b><br/>Args: title, start_time, end_time, auto_create_task<br/>Returns: Event JSON & HTML Card"]
        c2["<b>update_event</b><br/>Args: id, title, start_time, end_time, auto_update_task<br/>Returns: Updated Event JSON & HTML Card"]
        c3["<b>delete_event</b><br/>Args: id, auto_delete_task<br/>Returns: Confirmation JSON & HTML Card"]
        c4["<b>get_events</b><br/>Args: date, query<br/>Returns: Events List JSON & HTML"]
        c5["<b>set_reminder</b><br/>Args: event_id, minutes_before<br/>Returns: Event JSON & HTML Card"]
    end
    class CalServer orange;

    subgraph TaskServer ["Task MCP Server (Port 3002)"]
        direction TB
        t1["<b>create_task</b><br/>Args: title, due_date, description, related_event_id<br/>Returns: Task JSON & HTML Card"]
        t2["<b>update_task</b><br/>Args: id, title, due_date, description, status<br/>Returns: Updated Task JSON & HTML Card"]
        t3["<b>delete_task</b><br/>Args: id<br/>Returns: Deletion JSON & HTML Card"]
        t4["<b>list_tasks</b><br/>Args: status, related_event_id<br/>Returns: Tasks List JSON & HTML"]
        t5["<b>mark_task_complete</b><br/>Args: id<br/>Returns: Completed Task JSON & HTML Card"]
    end
    class TaskServer blue;

    Host -->|3a. Call Calendar Tool| CalServer
    Host -->|3b. Call Task Tool| TaskServer

    %% Server to Server SSE connection (Calendar server acting as Client to Task server)
    CalServer -.->|4. Server-to-Server Client Link<br/>(Calls: create_task, update_task, delete_task)| TaskServer

    subgraph Google ["Google Cloud APIs"]
        direction TB
        CalAPI[Google Calendar API]
        TasksAPI[Google Tasks API]
    end
    class Google green;

    c1 & c2 & c3 & c4 & c5 --->|Sync| CalAPI
    t1 & t2 & t3 & t4 & t5 --->|Sync| TasksAPI

    CalServer & TaskServer -->|5. Return JSON + HTML Card| Host
    Host -->|6. Render Timeline & Cards| DashboardOutput([Dashboard Output])
```

---

## ⚡ Key Features

* **Headless Google Authentication:** An standalone `auth_setup.py` script executes the OAuth 2.0 flow once, storing `config/token.json` for all servers.
* **Mock Mode Fallback:** If Google API credentials are not yet configured, the system transparently falls back to a mock in-memory database (`shared/mock_db.json`), making the system immediately runnable out of the box.
* **Server-to-Server Link (S2S):** Over an internal SSE transport client, the Calendar MCP Server makes direct, programmatic client calls to the Task MCP Server to create preparation tasks for meetings.
* **Local Ollama Tool Calling:** Integrates with local `llama3.2` or Groq endpoints to dynamically parse prompt tasks and invoke target tools.
* **HTML/CSS Timeline UI:** Beautiful frontend serving status displays, tool runs, collapsible JSON payloads, and formatted HTML widgets.

---

## 🔑 Google Cloud Setup

To sync with your Google Account, configure OAuth credentials:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and enable the **Google Calendar API** and **Google Tasks API**.
3. Configure the **OAuth Consent Screen** (Choose **External**, and add your Google email address under **Test Users**).
4. Go to **Credentials** $\rightarrow$ **Create Credentials** $\rightarrow$ **OAuth Client ID**.
5. Select **Desktop Application** as the application type, download the credentials JSON file.
6. Rename this file to `credentials.json` and save it to the `config/` directory:
   ```
   config/credentials.json
   ```

---

## 🚀 Installation & Running

### 1. Install Requirements
```bash
pip install -r requirements.txt
```

### 2. Run OAuth Authentication
```bash
python auth_setup.py
```
*This will open your default browser. Authorize the permissions requested, which will save the authorization token to `config/token.json`.*

### 3. Start the Servers
```bash
python start.py
```
*The launcher script will coordinate Task MCP, Calendar MCP, and the Orchestrator FastAPI process, printing unified, color-coded console logs.*

### 4. Open the Web Dashboard
Navigate your browser to:
```
http://localhost:3000
```
Submit prompts! Tasks will appear inside a task list called **MCP Tasks** in your Google Tasks, and meetings will be set on your primary **Google Calendar**.
