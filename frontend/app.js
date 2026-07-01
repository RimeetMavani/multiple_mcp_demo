// --- Multi-MCP Agent Dashboard Frontend Logic ---

document.addEventListener('DOMContentLoaded', () => {
  // UI Elements
  const promptInput = document.getElementById('prompt-input');
  const submitBtn = document.getElementById('submit-prompt-btn');
  const reconnectBtn = document.getElementById('reconnect-btn');
  const loader = document.getElementById('loader');
  const loaderStatus = document.getElementById('loader-status');
  const loaderElapsed = document.getElementById('loader-elapsed');
  const resultsContainer = document.getElementById('results-container');
  
  const calendarStatus = document.getElementById('calendar-status');
  const taskStatus = document.getElementById('task-status');
  const llmStatus = document.getElementById('llm-status');
  
  const workflowDuration = document.getElementById('workflow-duration');
  const workflowModel = document.getElementById('workflow-model');
  const workflowToolCount = document.getElementById('workflow-tool-count');
  
  const aiResponseText = document.getElementById('ai-response-text');
  const executionTimeline = document.getElementById('execution-timeline');
  const toolExecutionsList = document.getElementById('tool-executions-list');
  
  const calendarHtmlOutput = document.getElementById('calendar-html-output');
  const taskHtmlOutput = document.getElementById('task-html-output');
  const calendarJsonOutput = document.getElementById('calendar-json-output');
  const taskJsonOutput = document.getElementById('task-json-output');
  
  const historyList = document.getElementById('history-list');
  
  // Settings Panel Elements
  const settingsToggle = document.getElementById('settings-toggle-btn');
  const settingsPanel = document.getElementById('settings-panel');
  const settingsClose = document.getElementById('settings-close-btn');
  const providerSelect = document.getElementById('provider-select');
  const ollamaGroup = document.getElementById('ollama-settings-group');
  const groqGroup = document.getElementById('groq-settings-group');
  const ollamaModelInput = document.getElementById('ollama-model-input');
  const groqModelSelect = document.getElementById('groq-model-select');
  const groqApiKeyInput = document.getElementById('groq-api-key-input');
  const saveConfigBtn = document.getElementById('save-config-btn');
  
  // Variables for tracking execution
  let timerInterval = null;
  let startTime = 0;

  // --- Initialize app ---
  checkSystemStatus();
  loadLogsHistory();

  // --- Event Listeners ---
  submitBtn.addEventListener('click', submitPrompt);
  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitPrompt();
  });
  
  reconnectBtn.addEventListener('click', reconnectServers);
  
  // Tab Switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      
      e.target.classList.add('active');
      const tabId = e.target.getAttribute('data-tab');
      document.getElementById(`tab-${tabId}`).classList.add('active');
    });
  });

  // Sample chips click helper
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      promptInput.value = chip.textContent;
      promptInput.focus();
    });
  });

  // Settings Panel Toggle
  settingsToggle.addEventListener('click', () => {
    settingsPanel.classList.toggle('hidden');
    // Fetch and prefill configuration values when opened
    fetch('/api/status')
      .then(res => res.json())
      .then(data => {
        providerSelect.value = data.llm.provider;
        toggleSettingsFields(data.llm.provider);
        if (data.llm.provider === 'ollama') {
          ollamaModelInput.value = data.llm.model;
        } else {
          groqModelSelect.value = data.llm.model;
        }
      });
  });
  
  settingsClose.addEventListener('click', () => {
    settingsPanel.classList.add('hidden');
  });

  providerSelect.addEventListener('change', (e) => {
    toggleSettingsFields(e.target.value);
  });

  saveConfigBtn.addEventListener('click', saveConfiguration);

  // --- functions ---

  function toggleSettingsFields(provider) {
    if (provider === 'ollama') {
      ollamaGroup.classList.remove('hidden');
      groqGroup.classList.add('hidden');
    } else {
      ollamaGroup.classList.add('hidden');
      groqGroup.classList.remove('hidden');
    }
  }

  // Fetch status of servers and LLM from backend
  async function checkSystemStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      
      updateServerStatusBadge(calendarStatus, data.calendar.connected);
      updateServerStatusBadge(taskStatus, data.task.connected);
      
      llmStatus.textContent = `${data.llm.provider.toUpperCase()} (${data.llm.model})`;
      llmStatus.className = 'badge badge-online';
    } catch (err) {
      console.error('Error fetching system status:', err);
      updateServerStatusBadge(calendarStatus, false);
      updateServerStatusBadge(taskStatus, false);
      llmStatus.textContent = 'Disconnected';
      llmStatus.className = 'badge badge-offline';
    }
  }

  function updateServerStatusBadge(element, isConnected) {
    if (isConnected) {
      element.textContent = 'Online';
      element.className = 'badge badge-online';
    } else {
      element.textContent = 'Offline';
      element.className = 'badge badge-offline';
    }
  }

  // Request orchestrator to reconnect to MCP servers
  async function reconnectServers() {
    reconnectBtn.disabled = true;
    reconnectBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Reconnecting...';
    
    try {
      const res = await fetch('/api/reconnect', { method: 'POST' });
      const data = await res.json();
      console.log('Reconnect response:', data);
    } catch (err) {
      console.error('Failed to reconnect servers:', err);
    } finally {
      await checkSystemStatus();
      reconnectBtn.disabled = false;
      reconnectBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Reconnect Servers';
    }
  }

  // Save updated config to file
  async function saveConfiguration() {
    const provider = providerSelect.value;
    const body = {
      llmProvider: provider,
      ollamaModel: ollamaModelInput.value,
      groqModel: groqModelSelect.value,
      groqApiKey: groqApiKeyInput.value
    };

    saveConfigBtn.disabled = true;
    saveConfigBtn.textContent = 'Saving...';

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.success) {
        alert('LLM configuration updated successfully!');
        settingsPanel.classList.add('hidden');
      } else {
        alert('Failed to save config: ' + data.error);
      }
    } catch (err) {
      alert('Error updating configuration: ' + err.message);
    } finally {
      saveConfigBtn.disabled = false;
      saveConfigBtn.textContent = 'Save Configuration';
      checkSystemStatus();
    }
  }

  // Load execution runs history
  async function loadLogsHistory() {
    try {
      const res = await fetch('/api/logs');
      const logs = await res.json();
      
      if (logs.length === 0) {
        historyList.innerHTML = '<div class="history-empty">No runs recorded yet</div>';
        return;
      }
      
      historyList.innerHTML = logs.map(log => {
        const date = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const toolsText = log.toolsUsed.length > 0 ? log.toolsUsed.join(', ') : 'No tools used';
        return `
          <div class="history-item" data-file="${log.filename}">
            <div class="history-prompt">${escapeHtml(log.prompt)}</div>
            <div class="history-meta">
              <span>${date} (${(log.durationMs / 1000).toFixed(1)}s)</span>
              <span>Tools: ${log.toolsUsed.length}</span>
            </div>
          </div>
        `;
      }).join('');
      
      // Bind click handlers to history items
      document.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', (e) => {
          document.querySelectorAll('.history-item').forEach(hi => hi.classList.remove('active'));
          const currentItem = e.currentTarget;
          currentItem.classList.add('active');
          loadWorkflowDetails(currentItem.getAttribute('data-file'));
        });
      });
    } catch (err) {
      console.error('Error loading history list:', err);
    }
  }

  // Fetch full details of a specific log file and populate dashboard
  async function loadWorkflowDetails(filename) {
    try {
      resultsContainer.classList.add('hidden');
      loader.classList.remove('hidden');
      loaderStatus.textContent = 'Loading execution logs from file...';
      loaderElapsed.textContent = '';
      
      const res = await fetch(`/api/logs/${filename}`);
      if (!res.ok) throw new Error('Failed to retrieve log details');
      
      const data = await res.json();
      populateResults(data);
    } catch (err) {
      alert('Error reading details: ' + err.message);
    } finally {
      loader.classList.add('hidden');
    }
  }

  // Submit new prompt
  async function submitPrompt() {
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    // Reset layout
    submitBtn.disabled = true;
    resultsContainer.classList.add('hidden');
    loader.classList.remove('hidden');
    loaderStatus.textContent = 'Initializing agent orchestration...';
    
    // Start elapsed timer
    startTime = Date.now();
    loaderElapsed.textContent = 'Elapsed: 0.0s';
    timerInterval = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      loaderElapsed.textContent = `Elapsed: ${elapsed.toFixed(1)}s`;
      
      // Dynamic updates to mock intelligence progress
      if (elapsed > 1.5 && elapsed < 4) {
        loaderStatus.textContent = 'LLM is analyzing query & choosing tools...';
      } else if (elapsed >= 4 && elapsed < 7) {
        loaderStatus.textContent = 'Calling MCP Server tools & running executions...';
      } else if (elapsed >= 7) {
        loaderStatus.textContent = 'Consolidating responses and generating final summary...';
      }
    }, 100);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || res.statusText);
      }

      const result = await res.json();
      populateResults(result);
      loadLogsHistory(); // Update history list in sidebar
    } catch (err) {
      console.error('Error submitting prompt:', err);
      alert('Error running workflow: ' + err.message);
    } finally {
      clearInterval(timerInterval);
      loader.classList.add('hidden');
      submitBtn.disabled = false;
    }
  }

  // Populate all visual widgets in the UI with a run details
  function populateResults(data) {
    resultsContainer.classList.remove('hidden');
    
    // Top banner statistics
    workflowDuration.textContent = `${data.totalDurationMs || data.durationMs} ms`;
    workflowModel.textContent = data.model || 'llama3.2';
    
    const executions = data.toolExecutions || [];
    workflowToolCount.textContent = executions.length;

    // 1. Render AI Response
    aiResponseText.innerHTML = formatMarkdown(data.finalResponse || data.aiResponse);

    // 2. Render Timeline
    const timeline = data.timeline || [];
    renderTimeline(timeline);

    // 3. Render Tool Executions list (Viewer)
    renderToolExecutions(executions);

    // 4. Render HTML and JSON outputs in inspect tabs
    renderServerOutputs(executions, data.rawJsonResponses);
  }

  // Render execution timeline steps
  function renderTimeline(timeline) {
    if (timeline.length === 0) {
      executionTimeline.innerHTML = '<p class="mcp-empty">No timeline steps recorded.</p>';
      return;
    }

    executionTimeline.innerHTML = timeline.map(step => {
      const icon = getTimelineIcon(step.type);
      const time = step.timestamp ? new Date(step.timestamp).toLocaleTimeString([], { hour12: false }) : '';
      return `
        <div class="timeline-step ${step.type}">
          <div class="timeline-marker">
            <i class="${icon}"></i>
          </div>
          <div class="timeline-content">
            <span class="timeline-time">${time}</span>
            <h4>${escapeHtml(step.title)}</h4>
            <p>${escapeHtml(step.description)}</p>
          </div>
        </div>
      `;
    }).join('');
  }

  function getTimelineIcon(type) {
    switch (type) {
      case 'prompt': return 'fa-solid fa-comment-dots';
      case 'llm_decision': return 'fa-solid fa-brain';
      case 'tool_request': return 'fa-solid fa-sign-in-alt';
      case 'tool_response': return 'fa-solid fa-sign-out-alt';
      case 'final_response': return 'fa-solid fa-check-circle';
      case 'error': return 'fa-solid fa-circle-exclamation';
      default: return 'fa-solid fa-chevron-right';
    }
  }

  // Render tool executions list with collapsible details
  function renderToolExecutions(executions) {
    if (executions.length === 0) {
      toolExecutionsList.innerHTML = '<div class="empty-state">No tools were invoked during this run.</div>';
      return;
    }

    toolExecutionsList.innerHTML = executions.map((exe, index) => {
      const isSuccess = exe.success;
      const statusIcon = isSuccess ? 'fa-circle-check text-success' : 'fa-circle-xmark text-error';
      const badgeClass = exe.mcpServer === 'calendar-mcp' ? 'calendar' : 'task';
      
      return `
        <div class="tool-exe-item">
          <div class="tool-exe-header" data-target="body-${index}">
            <div class="tool-exe-header-left">
              <i class="fa-solid ${statusIcon}"></i>
              <span class="tool-exe-badge ${badgeClass}">${exe.mcpServer}</span>
              <span class="tool-exe-title">${exe.toolName}</span>
            </div>
            <div class="tool-exe-header-right">
              <span>Duration: <strong>${exe.durationMs || exe.durationMs || 0}ms</strong></span>
              <i class="fa-solid fa-chevron-down arrow-toggle"></i>
            </div>
          </div>
          <div id="body-${index}" class="tool-exe-body hidden">
            <p><strong>Description:</strong> ${escapeHtml(exe.description || 'No description available.')}</p>
            <div class="tool-grid">
              <div class="tool-grid-item">
                <h5>Input Parameters</h5>
                <pre><code>${JSON.stringify(exe.inputParameters || exe.parameters, null, 2)}</code></pre>
              </div>
              <div class="tool-grid-item">
                <h5>Tool JSON Output</h5>
                <pre><code>${JSON.stringify(exe.output.json || exe.output, null, 2)}</code></pre>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Bind click events for collapsible tool headers
    document.querySelectorAll('.tool-exe-header').forEach(header => {
      header.addEventListener('click', (e) => {
        const targetId = header.getAttribute('data-target');
        const body = document.getElementById(targetId);
        const arrow = header.querySelector('.arrow-toggle');
        
        body.classList.toggle('hidden');
        arrow.classList.toggle('fa-chevron-up');
        arrow.classList.toggle('fa-chevron-down');
      });
    });
  }

  // Populate Server HTML and JSON responses tabs
  function renderServerOutputs(executions, rawJsonResponses) {
    // Clear outputs
    calendarHtmlOutput.innerHTML = '';
    taskHtmlOutput.innerHTML = '';
    
    // Separate HTML content by server
    const calendarExes = executions.filter(e => e.mcpServer === 'calendar-mcp');
    const taskExes = executions.filter(e => e.mcpServer === 'task-mcp');

    // 1. Render HTML outputs
    if (calendarExes.length > 0) {
      calendarHtmlOutput.innerHTML = calendarExes.map(e => e.output.html || `<div>${JSON.stringify(e.output.json)}</div>`).join('');
    } else {
      calendarHtmlOutput.innerHTML = '<div class="empty-state">No Calendar tools invoked during this run.</div>';
    }

    if (taskExes.length > 0) {
      taskHtmlOutput.innerHTML = taskExes.map(e => e.output.html || `<div>${JSON.stringify(e.output.json)}</div>`).join('');
    } else {
      taskHtmlOutput.innerHTML = '<div class="empty-state">No Task tools invoked during this run.</div>';
    }

    // 2. Render JSON outputs
    const calendarJson = rawJsonResponses && rawJsonResponses['calendar-mcp'] ? rawJsonResponses['calendar-mcp'] : null;
    const taskJson = rawJsonResponses && rawJsonResponses['task-mcp'] ? rawJsonResponses['task-mcp'] : null;
    
    calendarJsonOutput.textContent = calendarJson ? JSON.stringify(calendarJson, null, 2) : '{}';
    taskJsonOutput.textContent = taskJson ? JSON.stringify(taskJson, null, 2) : '{}';
  }

  // --- Utility Helpers ---
  
  function escapeHtml(text) {
    if (!text) return '';
    if (typeof text !== 'string') return String(text);
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Simple formatter to parse bold and lists in LLM responses
  function formatMarkdown(text) {
    if (!text) return '';
    let formatted = escapeHtml(text);
    
    // Bold: **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Bullet points: * text or - text
    formatted = formatted.replace(/^(?:\*|-)\s+(.*)$/gm, '<li>$1</li>');
    formatted = formatted.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    
    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');
    
    return formatted;
  }
});
