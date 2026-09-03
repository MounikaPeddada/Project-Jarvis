import os
import sys
import json
import re
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

# Add parent directory to path so we can import tools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import google.genai as genai  # NEW: use google.genai instead
from tools.tool_registry import TOOLS_LIST, TOOL_FUNCTIONS

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise Exception("❌ GEMINI_API_KEY not found in .env file!")

client = genai.Client(api_key=api_key)


SYSTEM_PROMPT = """
You are Jarvis, a helpful desktop assistant. Address the user as 'ma'am'.

When you need to use a tool, reply with ONLY the JSON object(s).
Do NOT add any extra text before or after the JSON.

For single tool: {"tool": "get_time", "args": {}}
For multiple tools: [{"tool": "tool1", "args": {}}, {"tool": "tool2", "args": {}}]

If you don't need a tool, reply naturally without any JSON.
"""

DEFAULT_MAX_TOKENS = 500
FINAL_RESPONSE_TOKENS = 300

@dataclass
class ToolCall:
    """Represents a parsed tool call."""
    tool: str
    args: Dict[str, Any]

class ToolCallParser:
    """Optimized tool call parser with support for batch tool calls."""
    
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
                
                return tool_calls
            except json.JSONDecodeError:
                pass
        
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
        """Execute single tool asynchronously."""
        try:
            if tool_name in TOOL_FUNCTIONS:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
                return (tool_name, result)
            else:
                return (tool_name, f"Unknown tool '{tool_name}'")
        except Exception as e:
            return (tool_name, f"Error: {str(e)}")
    
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
    """Main Jarvis AI Agent."""
    
    def __init__(self):
        self.parser = ToolCallParser()
        self.batcher = ToolBatcher()
        self._build_tool_descriptions()
        self.chat=client.chats.create(model="gemini-3.7-flash")  # Create a chat session for tool use
    
    def _build_tool_descriptions(self):
        """Pre-build tool descriptions."""
        self.tool_descriptions = "\n".join([
            f"- {t['name']}: {t['description']} (args: {t['input_schema']['properties']})"
            for t in TOOLS_LIST
        ])
    
    def _call_gemini(self, prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        """Call Gemini API with retry logic."""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                #create a chat session for tool use
                start=time.time()
                response = self.chat.send_message(
                    prompt,
                    config={
                        "max_output_tokens":max_tokens,

                    }
                )
                elapsed = time.time() - start
                print(f"⏱️ API call took {elapsed:.2f} seconds")

                return response.text
            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                else:
                    raise Exception(f"❌ API Error: {str(e)}")
    
    async def _execute_tool_batch(self, tool_calls: List[ToolCall]) -> Dict[str, Any]:
        """Execute batch of tools in parallel."""
        if not tool_calls:
            return {}
        
        print(f"🔧 Executing {len(tool_calls)} tool(s): {', '.join(tc.tool for tc in tool_calls)}")
        return await self.batcher.execute_tools_in_parallel(tool_calls)
    
    def process_command(self, user_input: str) -> str:
        """Process a user command and execute tools if needed."""
        
        decision_prompt = f"""{SYSTEM_PROMPT}

AVAILABLE TOOLS:
{self.tool_descriptions}

User command: {user_input}
"""
        
        response_text = self._call_gemini(decision_prompt)
        tool_calls = self.parser.parse(response_text)
        
        if tool_calls:
            try:
                results = asyncio.run(self._execute_tool_batch(tool_calls))
                
                results_str = "\n".join([f"{tool}: {result}" for tool, result in results.items()])
                
                final_prompt = f"""You executed tools and got results. Provide a natural response.

User asked: "{user_input}"
Tools executed: {', '.join([tc.tool for tc in tool_calls])}
Tool results:
{results_str}

Give a concise, helpful response."""
                
                final_response = self._call_gemini(final_prompt, FINAL_RESPONSE_TOKENS)
                return final_response
                
            except Exception as e:
                return f"Error executing tools: {str(e)}"
        else:
            return response_text
    
    def run_interactive(self):
        """Run interactive mode."""
        print("🦾 Jarvis is online. Type 'exit' to quit.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("Jarvis: Goodbye!")
                    break
                
                response = self.process_command(user_input)
                print(f"Jarvis: {response}\n")
                
            except KeyboardInterrupt:
                print("\nJarvis: Interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {str(e)}\n")

if __name__ == "__main__":
    agent = JarvisAgent()
    agent.run_interactive()
