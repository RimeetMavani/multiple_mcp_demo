import subprocess
import sys
import time
import os
import signal

# Process tracker
processes = []

def start_process(name, cwd, port, color_code):
    reset_color = '\033[0m'
    print(f"{color_code}[System] Starting {name} on port {port}...{reset_color}")
    
    # We run uvicorn programmatically or as shell sub-command
    # To run uvicorn from python: we spawn python uvicorn command
    cmd = [
        sys.executable, "-u", "-m", "uvicorn", 
        "server:app" if "mcp" in name.lower() else "orchestrator:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--log-level", "info"
    ]
    
    # Start subprocess
    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    processes.append((name, p))
    
    # Start thread to log output with prefix
    import threading
    def log_reader():
        for line in iter(p.stdout.readline, ''):
            if line:
                print(f"{color_code}[{name}]{reset_color} {line.strip()}", flush=True)
        p.stdout.close()
        
    t = threading.Thread(target=log_reader, daemon=True)
    t.start()
    return p

# Color codes
COLOR_TASK = '\033[96m' # Light Cyan
COLOR_CALENDAR = '\033[93m' # Light Yellow
COLOR_ORCH = '\033[95m' # Light Magenta
RESET = '\033[0m'

def shutdown_servers(signum=None, frame=None):
    print(f"\n{RESET}[System] Terminating all background servers...")
    for name, p in processes:
        try:
            print(f"[System] Killing {name} (PID: {p.pid})...")
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            p.kill()
    print("[System] All processes cleaned up. Exiting.")
    sys.exit(0)

# Bind termination signals
signal.signal(signal.SIGINT, shutdown_servers)
signal.signal(signal.SIGTERM, shutdown_servers)

def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("====================================================")
    print("    STARTING PYTHON MULTI-MCP AGENT DASHBOARD       ")
    print("====================================================")
    
    # Check if token.json exists
    token_path = os.path.join(current_dir, 'config', 'token.json')
    if not os.path.exists(token_path):
        print(f"\n{COLOR_CALENDAR}[System Warning] 'config/token.json' not found!{RESET}")
        print("Please make sure you run 'python auth_setup.py' to authenticate with Google")
        print("before submitting prompts on the dashboard, otherwise Google API calls will fail.")
        print("-" * 60 + "\n")

    # Start MCP Servers
    start_process("Task MCP", os.path.join(current_dir, 'task_mcp'), 3002, COLOR_TASK)
    start_process("Calendar MCP", os.path.join(current_dir, 'calendar_mcp'), 3001, COLOR_CALENDAR)
    
    print(f"\n[System] Waiting 2 seconds for MCP servers to initialize...")
    time.sleep(2)
    
    # Start Orchestrator
    start_process("Orchestrator", os.path.join(current_dir, 'orchestrator'), 3000, COLOR_ORCH)
    
    print("\n====================================================")
    print("System is up and running!")
    print("Open your browser and visit: http://localhost:3000")
    print("Press Ctrl+C to terminate all services.")
    print("====================================================\n")
    
    # Keep main thread alive
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            shutdown_servers()

if __name__ == '__main__':
    main()
