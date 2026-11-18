import os
import sys
import json
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.tool_registry import TOOLS_LIST, TOOL_FUNCTIONS
from memory.database import log_interaction, init_database
from memory.obsidian_sync import ObsidianSync
from brain.brain import call_llm, check_server, warm_up
from brain.prompts import build_system_prompt, describe_tools
from brain.router import route

load_dotenv()

MAX_INPUT_LENGTH = 1000
API_TIMEOUT = 30.0 

# Tools whose result is already a friendly sentence: skip the 2nd LLM call
DIRECT_TOOLS = {
    "get_time", "get_date", "remember", "recall",
    "add_task", "list_tasks", "complete_task", "get_history",
    "echo", # ✅ Added echo here to skip the second LLM call
}

@dataclass
class ToolCall:
    tool: str
    args: Dict[str, Any]


class ToolValidator:
    @staticmethod
    def validate(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, str]:
        tool_schema = next((t for t in TOOLS_LIST if t["name"] == tool_name), None)
        if not tool_schema:
            return False, f"Tool '{tool_name}' not found in registry"

        required = tool_schema.get("input_schema", {}).get("required", [])
        for prop_name in required:
            if prop_name not in tool_args:
                return False, f"Missing required argument '{prop_name}' for tool '{tool_name}'"

        return True, ""


class ToolCallParser:
    """Robust parser that uses JSON decoder to find tool calls anywhere in text."""
    @staticmethod
    def _as_calls(data) -> List[ToolCall]:
        items = data if isinstance(data, list) else [data]
        calls = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("tool"), str):
                # Handle both 'args' and 'arguments', and missing args
                args = item.get("args", item.get("arguments"))
                calls.append(ToolCall(tool=item["tool"], args=args if isinstance(args, dict) else {}))
        return calls

    @staticmethod
    def parse(response_text: str) -> List[ToolCall]:
        decoder = json.JSONDecoder()
        calls, i = [], 0
        while i < len(response_text):
            if response_text[i] in "[{":
                try:
                    data, end = decoder.raw_decode(response_text, i)
                    found = ToolCallParser._as_calls(data)
                    if found:
                        calls.extend(found)
                        i = end
                        continue
                except json.JSONDecodeError:
                    pass
            i += 1
        return calls


TYPE_CASTS = {"integer": int, "number": float, "string": str}

def clean_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Drop hallucinated args and cast values to the schema's types."""
    schema = next((t for t in TOOLS_LIST if t["name"] == tool_name), None)
    if not schema:
        return args
    props = schema["input_schema"].get("properties", {})
    cleaned = {}
    for name, value in args.items():
        if name not in props:
            continue
        cast = TYPE_CASTS.get(props[name].get("type"))
        try:
            cleaned[name] = cast(value) if cast and value is not None else value
        except (TypeError, ValueError):
            cleaned[name] = value
    return cleaned


class ToolBatcher:
    @staticmethod
    async def execute_tool_async(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Any]:
        try:
            # Clean and cast args before validating
            tool_args = clean_args(tool_name, tool_args)
            
            is_valid, error_msg = ToolValidator.validate(tool_name, tool_args)
            if not is_valid:
                return (tool_name, f"Error: {error_msg}")

            if tool_name in TOOL_FUNCTIONS:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
                return (tool_name, result)
            else:
                return (tool_name, f"Unknown tool '{tool_name}'")
        except Exception as e:
            return (tool_name, f"Error executing tool: {str(e)}")

    @staticmethod
    async def execute_tools_in_parallel(tool_calls: List[ToolCall]) -> List[Tuple[str, Any]]:
        # Return a list of tuples instead of a dict to prevent overwriting duplicate tools
        if not tool_calls:
            return []
        return list(await asyncio.gather(
            *[ToolBatcher.execute_tool_async(tc.tool, tc.args) for tc in tool_calls]
        ))


class JarvisAgent:
    def __init__(self):
        # 1. Check if Ollama is running
        check_server()
        
        # 2. Initialize SQLite database
        init_database()
        
        # 3. 🔥 Load the model into VRAM so the first command is fast
        warm_up()
        
        # 4. Setup the parsers and prompts
        self.parser = ToolCallParser()
        self.batcher = ToolBatcher()
        self.system_prompt = build_system_prompt(describe_tools(TOOLS_LIST))
        logger.info("🦾 Jarvis Agent initialized")

    def _sanitize_input(self, user_input: str) -> Tuple[bool, str]:
        if not user_input:
            return False, "Input is empty"
        if len(user_input) > MAX_INPUT_LENGTH:
            return False, "Input too long"
        return True, user_input.strip()

    def process_command(self, user_input: str) -> str:
        is_valid, sanitized = self._sanitize_input(user_input)
        if not is_valid:
            return f"Invalid input: {sanitized}"

        logger.info(f"Processing command: {sanitized[:100]}...")

        # Router: zero LLM calls for simple commands
        local_result = route(sanitized)
        if local_result:
            logger.info("⚡ Handled by local router")
            log_interaction(command=sanitized, tool_called="router", result=local_result)
            return local_result

        # Ollama brain: for everything the router can't handle
        try:
            response_text = call_llm(sanitized, system=self.system_prompt, temperature=0.1)
            tool_calls = self.parser.parse(response_text)

            if tool_calls:
                try:
                    results = asyncio.run(asyncio.wait_for(
                        self._execute_tool_batch(tool_calls),
                        timeout=API_TIMEOUT
                    ))

                    tools_used = ', '.join([tc.tool for tc in tool_calls])
                    results_str = "\n".join(f"{tool}: {result}" for tool, result in results)

                    # ✅ Check if any tool failed and report it honestly!
                    failed = [r for _, r in results
                              if isinstance(r, str) and r.startswith(("Error", "Unknown tool", "❌"))]
                    if failed:
                        log_interaction(command=sanitized, tool_called=tools_used, result=results_str, error=failed[0])
                        return f"Sorry ma'am, that failed: {failed[0]}"

                    # Single simple tool: its result is already a clean sentence
                    if len(tool_calls) == 1 and tool_calls[0].tool in DIRECT_TOOLS:
                        final_response = str(results[0][1])
                    else:
                        final_prompt = f"""You executed tools and got results. Provide a natural response.
User asked: "{sanitized}"
Tools executed: {tools_used}
Tool results:
{results_str}
Give a concise, helpful response."""
                        final_response = call_llm(
                            final_prompt,
                            system="You are Jarvis. Address the user as 'ma'am'. Be brief.",
                            temperature=0.5,
                        )

                    log_interaction(command=sanitized, tool_called=tools_used, result=results_str, error=None)
                    return final_response

                except asyncio.TimeoutError:
                    log_interaction(command=sanitized, error="Tool timeout")
                    return "Tool execution timeout."
                except Exception as e:
                    log_interaction(command=sanitized, error=str(e))
                    return f"Error executing tools: {str(e)}"
            else:
                log_interaction(command=sanitized, result=response_text)
                return response_text

        except Exception as e:
            log_interaction(command=sanitized, error=str(e))
            return f"Error processing command: {str(e)}"

    async def _execute_tool_batch(self, tool_calls: List[ToolCall]) -> List[Tuple[str, Any]]:
        if not tool_calls:
            return []
        return await self.batcher.execute_tools_in_parallel(tool_calls)

    def run_interactive(self):
        print("🦾 Jarvis is online. Type 'exit' to quit.\n")
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Jarvis: Goodbye!")
                    try:
                        ObsidianSync().sync_all()
                    except Exception as e:
                        logger.error(f"Obsidian sync failed: {e}")
                    break

                response = self.process_command(user_input)
                print(f"Jarvis: {response}\n")

            except KeyboardInterrupt:
                print("\nJarvis: Interrupted. Goodbye!")
                try:
                    ObsidianSync().sync_all()
                except Exception as e:
                    logger.error(f"Obsidian sync failed: {e}")
                break
            except Exception as e:
                print(f"❌ Error: {str(e)}\n")


if __name__ == "__main__":
    try:
        agent = JarvisAgent()
        agent.run_interactive()
    except Exception as e:
        print(f"\n❌ FATAL STARTUP ERROR: {e}")
        # ✅ This line prevents the window from closing instantly so you can read the error!
        input("\nPress Enter to close this window...") 
        sys.exit(1)