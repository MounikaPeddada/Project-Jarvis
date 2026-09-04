import os
import sys
import json
import re
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.tool_registry import TOOLS_LIST, TOOL_FUNCTIONS
from brain.brain import call_gemini
from memory.database import log_interaction, remember, recall

# Load environment variables
load_dotenv()

# Constants
MAX_INPUT_LENGTH = 1000
API_TIMEOUT = 15.0

# System Prompt (Phase 1 + Phase 2)
SYSTEM_PROMPT = """
You are Jarvis, a helpful desktop assistant. Address the user as 'ma'am'.

When you need to use a tool, reply with ONLY the JSON object(s).
Do NOT add any extra text before or after the JSON.

For single tool: {"tool": "get_time", "args": {}}
For multiple tools: [{"tool": "tool1", "args": {}}, {"tool": "tool2", "args": {}}]

AVAILABLE TOOLS:
- get_time: Gets the current date and time.
- echo: Repeats back whatever the user said.
- add_numbers: Adds two numbers together.
- remember: Saves a fact to long-term memory.
- recall: Retrieves facts from memory.
- add_task: Adds a task to the to-do list.
- list_tasks: Lists all tasks.
- complete_task: Marks a task as complete.

If you don't need a tool, reply naturally without any JSON.
"""

@dataclass
class ToolCall:
    """Represents a parsed tool call."""
    tool: str
    args: Dict[str, Any]

class ToolValidator:
    """Validates tool arguments against schema."""
    
    @staticmethod
    def validate(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate tool arguments.
        Returns: (is_valid, error_message)
        """
        # Find tool schema
        tool_schema = None
        for tool in TOOLS_LIST:
            if tool["name"] == tool_name:
                tool_schema = tool
                break
        
        if not tool_schema:
            return False, f"Tool '{tool_name}' not found in registry"
        
        # Get properties
        properties = tool_schema.get("input_schema", {}).get("properties", {})
        
        # Check for missing required arguments
        required = tool_schema.get("input_schema", {}).get("required", [])
        for prop_name in required:
            if prop_name not in tool_args:
                return False, f"Missing required argument '{prop_name}' for tool '{tool_name}'"
        
        # Check for unexpected arguments
        for arg_name in tool_args:
            if arg_name not in properties:
                logger.warning(f"Unexpected argument '{arg_name}' for tool '{tool_name}'")
        
        return True, ""

class ToolCallParser:
    """Robust JSON extractor that searches anywhere in the response."""
    
    JSON_PATTERN = re.compile(r'\[\s*\{[^[\]]*\}\s*(?:,\s*\{[^[\]]*\})*\s*\]|\{[^{}]*"tool"[^{}]*"args"[^{}]*\}')
    
    @staticmethod
    def parse(response_text: str) -> List[ToolCall]:
        """Extract tool call(s) from response (supports single or batch)."""
        tool_calls = []
        match = ToolCallParser.JSON_PATTERN.search(response_text)
        
        if match:
            json_str = match.group(0)
            try:
                data = json.loads(json_str)
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "tool" in item and "args" in item:
                            tool_calls.append(ToolCall(tool=item["tool"], args=item["args"]))
                elif isinstance(data, dict) and "tool" in data and "args" in data:
                    tool_calls.append(ToolCall(tool=data["tool"], args=data["args"]))
                
                logger.debug(f"Parsed {len(tool_calls)} tool call(s)")
                return tool_calls
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parsing failed: {str(e)}")
        
        # Fallback: brace matching
        return ToolCallParser._parse_with_braces(response_text)
    
    @staticmethod
    def _parse_with_braces(response_text: str) -> List[ToolCall]:
        """Fallback parser using brace matching."""
        tool_calls = []
        start = response_text.find('{')
        
        while start != -1:
            brace_count = 0
            for i in range(start, len(response_text)):
                if response_text[i] == '{':
                    brace_count += 1
                elif response_text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            json_str = response_text[start:i+1]
                            data = json.loads(json_str)
                            if "tool" in data and "args" in data:
                                tool_calls.append(ToolCall(tool=data["tool"], args=data["args"]))
                        except json.JSONDecodeError:
                            pass
                        start = response_text.find('{', i+1)
                        break
            else:
                break
        
        return tool_calls

class ToolBatcher:
    """Handles batching and parallel execution of tools."""
    
    @staticmethod
    async def execute_tool_async(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Any]:
        """Execute single tool asynchronously with validation."""
        try:
            # Validate arguments first
            is_valid, error_msg = ToolValidator.validate(tool_name, tool_args)
            if not is_valid:
                logger.error(f"Validation error for tool '{tool_name}': {error_msg}")
                return (tool_name, f"Error: {error_msg}")
            
            if tool_name in TOOL_FUNCTIONS:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
                logger.info(f"✅ Tool '{tool_name}' executed successfully")
                return (tool_name, result)
            else:
                logger.error(f"Tool '{tool_name}' not found in TOOL_FUNCTIONS")
                return (tool_name, f"Unknown tool '{tool_name}'")
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {str(e)}", exc_info=True)
            return (tool_name, f"Error executing tool: {str(e)}")
    
    @staticmethod
    async def execute_tools_in_parallel(tool_calls: List[ToolCall]) -> Dict[str, Any]:
        """Execute multiple tools in parallel."""
        if not tool_calls:
            return {}
        
        tasks = [
            ToolBatcher.execute_tool_async(tc.tool, tc.args)
            for tc in tool_calls
        ]
        
        results = await asyncio.gather(*tasks)
        return {tool_name: result for tool_name, result in results}

class JarvisAgent:
    """Main Jarvis AI Agent with improved error handling."""
    
    def __init__(self):
        self.parser = ToolCallParser()
        self.batcher = ToolBatcher()
        self._build_tool_descriptions()
        logger.info("🦾 Jarvis Agent initialized")
    
    def _build_tool_descriptions(self):
        """Pre-build tool descriptions."""
        self.tool_descriptions = "\n".join([
            f"- {t['name']}: {t['description']} (args: {t['input_schema']['properties']})"
            for t in TOOLS_LIST
        ])
    
    def _sanitize_input(self, user_input: str) -> Tuple[bool, str]:
        """
        Sanitize user input.
        Returns: (is_valid, sanitized_input)
        """
        if not user_input:
            return False, "Input is empty"
        
        if len(user_input) > MAX_INPUT_LENGTH:
            return False, f"Input too long (max {MAX_INPUT_LENGTH} characters)"
        
        return True, user_input.strip()
    
    def process_command(self, user_input: str) -> str:
        """Process a user command, log everything, and return a response."""
        
        # Sanitize input
        is_valid, sanitized = self._sanitize_input(user_input)
        if not is_valid:
            error_msg = f"Invalid input: {sanitized}"
            logger.warning(error_msg)
            log_interaction(command=user_input, error=error_msg)
            return error_msg
        
        logger.info(f"Processing command: {sanitized[:100]}...")
        
        decision_prompt = f"""{SYSTEM_PROMPT}

AVAILABLE TOOLS:
{self.tool_descriptions}

User command: {sanitized}
"""
        
        try:
            # Step 1: Get decision from Brain
            response_text = call_gemini(decision_prompt)
            tool_calls = self.parser.parse(response_text)
            
            if tool_calls:
                try:
                    # Step 2: Execute tools in parallel with timeout protection
                    results = asyncio.run(asyncio.wait_for(
                        self._execute_tool_batch(tool_calls),
                        timeout=API_TIMEOUT
                    ))
                    
                    tools_used = ', '.join([tc.tool for tc in tool_calls])
                    results_str = "\n".join([f"{tool}: {result}" for tool, result in results.items()])
                    
                    # Step 3: Get final reply from Brain
                    final_prompt = f"""You executed tools and got results. Provide a natural response.

User asked: "{sanitized}"
Tools executed: {tools_used}
Tool results:
{results_str}

Give a concise, helpful response based on these results."""
                    
                    final_response = call_gemini(final_prompt)
                    
                    # Step 4: LOG EVERYTHING to history
                    log_interaction(
                        command=sanitized,
                        tool_called=tools_used,
                        result=results_str,
                        error=None
                    )
                    
                    logger.info(f"✅ Command processed successfully")
                    return final_response
                
                except asyncio.TimeoutError:
                    error_msg = f"Tool execution timeout (max {API_TIMEOUT}s)"
                    logger.error(error_msg)
                    log_interaction(command=sanitized, error=error_msg)
                    return error_msg
                except Exception as e:
                    error_msg = f"Error executing tools: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    log_interaction(command=sanitized, error=error_msg)
                    return error_msg
            else:
                # No tool called — just reply naturally
                logger.info("No tools needed for this command")
                log_interaction(
                    command=sanitized,
                    tool_called=None,
                    result=response_text,
                    error=None
                )
                return response_text
        
        except Exception as e:
            error_msg = f"Error processing command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            log_interaction(command=sanitized, error=error_msg)
            return error_msg
    
    async def _execute_tool_batch(self, tool_calls: List[ToolCall]) -> Dict[str, Any]:
        """Execute batch of tools in parallel."""
        if not tool_calls:
            return {}
        
        logger.info(f"🔧 Executing {len(tool_calls)} tool(s): {', '.join(tc.tool for tc in tool_calls)}")
        return await self.batcher.execute_tools_in_parallel(tool_calls)
    
    def run_interactive(self):
        """Run interactive mode."""
        print("🦾 Jarvis is online. Type 'exit' to quit.\n")
        logger.info("Agent started in interactive mode")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Jarvis: Goodbye!")
                    logger.info("Agent shutdown requested by user")
                    break
                
                response = self.process_command(user_input)
                print(f"Jarvis: {response}\n")
                
            except KeyboardInterrupt:
                print("\nJarvis: Interrupted. Goodbye!")
                logger.info("Agent interrupted by user (KeyboardInterrupt)")
                break
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                print(f"{error_msg}\n")
                logger.error(error_msg, exc_info=True)

if __name__ == "__main__":
    try:
        agent = JarvisAgent()
        agent.run_interactive()
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        print(f"❌ Fatal error: {str(e)}")
