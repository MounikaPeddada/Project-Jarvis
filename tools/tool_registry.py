from tools.time_tools import get_time, echo, add_numbers, get_date

TOOLS_LIST = [
    {
        "name": "get_time",
        "description": "Get the current time",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_date",
        "description": "Get the current date",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "echo",
        "description": "Echo back a message",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"}
            }
        }
    },
    {
        "name": "add_numbers",
        "description": "Add two numbers",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "get_time": get_time,
    "get_date": get_date,
    "echo": echo,
    "add_numbers": add_numbers,
}