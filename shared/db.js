import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dbPath = path.join(__dirname, 'data.json');

// Initialize database file if it doesn't exist
if (!fs.existsSync(dbPath)) {
  fs.writeFileSync(dbPath, JSON.stringify({ events: [], tasks: [] }, null, 2), 'utf-8');
}

function readDb() {
  try {
    const data = fs.readFileSync(dbPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error reading database:', error);
    return { events: [], tasks: [] };
  }
}

function writeDb(data) {
  try {
    fs.writeFileSync(dbPath, JSON.stringify(data, null, 2), 'utf-8');
  } catch (error) {
    console.error('Error writing to database:', error);
  }
}

export const db = {
  // Calendar Events
  getEvents() {
    return readDb().events;
  },
  
  saveEvents(events) {
    const data = readDb();
    data.events = events;
    writeDb(data);
  },
  
  createEvent(event) {
    const data = readDb();
    const newEvent = {
      id: 'evt_' + Math.random().toString(36).substr(2, 9),
      createdAt: new Date().toISOString(),
      ...event
    };
    data.events.push(newEvent);
    writeDb(data);
    return newEvent;
  },
  
  updateEvent(id, updates) {
    const data = readDb();
    const index = data.events.findIndex(e => e.id === id);
    if (index === -1) return null;
    
    data.events[index] = {
      ...data.events[index],
      ...updates,
      updatedAt: new Date().toISOString()
    };
    writeDb(data);
    return data.events[index];
  },
  
  deleteEvent(id) {
    const data = readDb();
    const index = data.events.findIndex(e => e.id === id);
    if (index === -1) return false;
    
    data.events.splice(index, 1);
    writeDb(data);
    return true;
  },

  // Tasks
  getTasks() {
    return readDb().tasks;
  },
  
  saveTasks(tasks) {
    const data = readDb();
    data.tasks = tasks;
    writeDb(data);
  },
  
  createTask(task) {
    const data = readDb();
    const newTask = {
      id: 'task_' + Math.random().toString(36).substr(2, 9),
      status: 'pending',
      createdAt: new Date().toISOString(),
      ...task
    };
    data.tasks.push(newTask);
    writeDb(data);
    return newTask;
  },
  
  updateTask(id, updates) {
    const data = readDb();
    const index = data.tasks.findIndex(t => t.id === id);
    if (index === -1) return null;
    
    data.tasks[index] = {
      ...data.tasks[index],
      ...updates,
      updatedAt: new Date().toISOString()
    };
    writeDb(data);
    return data.tasks[index];
  },
  
  deleteTask(id) {
    const data = readDb();
    const index = data.tasks.findIndex(t => t.id === id);
    if (index === -1) return false;
    
    data.tasks.splice(index, 1);
    writeDb(data);
    return true;
  }
};
