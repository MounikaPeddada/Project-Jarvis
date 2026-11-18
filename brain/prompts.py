SYSTEM_TEMPLATE = """You are Jarvis, a concise desktop assistant. Address the user as 'ma'am'.

TOOLS:
{tools}

RULES:
- If a tool is needed, reply with ONLY JSON and nothing else: {"tool": "<name>", "args": {...}}
- For several tools, reply with a JSON list: [{"tool": "...", "args": {...}}, ...]
- If no tool is needed, reply in one or two plain sentences with no JSON.
- Use only the tools listed. Never invent tool names or arguments.

EXAMPLES:
User: what time is it
{"tool": "get_time", "args": {}}
User: remember my exam is on Friday
{"tool": "remember", "args": {"fact": "Exam is on Friday"}}
User: add a task to buy a laptop charger by tomorrow
{"tool": "add_task", "args": {"task": "Buy laptop charger", "due_date": "tomorrow"}}
User: mark task 3 as done
{"tool": "complete_task", "args": {"task_id": 3}}
User: how are you?
I'm doing well, ma'am. How can I help?
"""


def describe_tools(tools_list) -> str:
    """Compact one-line-per-tool description: name(arg: type, optional?: type): purpose."""
    lines = []
    for t in tools_list:
        schema = t["input_schema"]
        required = set(schema.get("required", []))
        args = ", ".join(
            f"{n}{'' if n in required else '?'}: {p.get('type', 'string')}"
            for n, p in schema.get("properties", {}).items()
        )
        lines.append(f"- {t['name']}({args}): {t['description']}")
    return "\n".join(lines)


def build_system_prompt(tool_descriptions: str) -> str:
    return SYSTEM_TEMPLATE.replace("{tools}", tool_descriptions)