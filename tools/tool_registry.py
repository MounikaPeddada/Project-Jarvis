# tools/tool_registry.py

from tools.time_tools import get_time, echo, add_numbers
from memory.database import remember, recall, add_task, list_tasks, complete_task, get_history

TOOLS_LIST = [
    # ============================================================
    # PHASE 1: Basic Tools
    # ============================================================
    {
        "name": "get_time",
        "description": "Gets the current date and time. Use when the user asks for the time or date.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "echo",
        "description": "Repeats back whatever the user said. Use for testing or confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to repeat back"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "add_numbers",
        "description": "Adds two numbers together and returns the sum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The first number"},
                "b": {"type": "number", "description": "The second number"}
            },
            "required": ["a", "b"]
        }
    },
    
    # ============================================================
    # PHASE 2: Memory Tools
    # ============================================================
    {
        "name": "remember",
        "description": "Saves a fact to long-term memory. Use when the user says something they want remembered (e.g., 'Remember my name is Rahul').",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember (e.g., 'Name is Rahul')"},
                "category": {"type": "string", "description": "Optional category like 'personal', 'work', 'project'"}
            },
            "required": ["fact"]
        }
    },
    {
        "name": "recall",
        "description": "Retrieves facts from memory. Use when the user asks what you remember (e.g., 'What's my name?', 'What do you know about work?').",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category to filter memories"}
            }
        }
    },
    
    # ============================================================
    # PHASE 2: Task Management Tools
    # ============================================================
    {
        "name": "add_task",
        "description": "Adds a task to the to-do list. Use when the user mentions something they need to do.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task description"},
                "due_date": {"type": "string", "description": "Optional due date (e.g., 'Friday', '2026-09-15', 'tomorrow')"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "list_tasks",
        "description": "Lists all tasks. Use when the user asks about their tasks or to-do list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: 'pending', 'completed', 'cancelled', or 'all'"}
            }
        }
    },
    {
        "name": "complete_task",
        "description": "Marks a task as complete. Use when the user says they finished something.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The ID of the task to complete (from list_tasks)"}
            },
            "required": ["task_id"]
        }
    },
    
    # ============================================================
    # PHASE 2: History Tool
    # ============================================================
    {
        "name": "get_history",
        "description": "Retrieves recent interaction history. Use when the user asks what they did earlier, wants to see past commands, or asks for history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of entries to show (default: 100)"}
            }
        }
    }
]

# ============================================================
# TOOL FUNCTIONS MAPPING
# ============================================================
TOOL_FUNCTIONS = {
    # Phase 1
    "get_time": get_time,
    "echo": echo,
    "add_numbers": add_numbers,
    
    # Phase 2 - Memory
    "remember": remember,
    "recall": recall,
    
    # Phase 2 - Tasks
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    
    # Phase 2 - History
    "get_history": get_history
}
