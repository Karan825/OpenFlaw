import os
import re
import json
import time
import logging
from typing import Dict, List, Any, Tuple, Optional
import anthropic
import openai
from agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Token pricing rates (set to $0.0 for free tier models)
PRICING = {
    "claude-3-5-sonnet-20241022": {"input": 0.000003, "output": 0.000015},
    "claude-3-opus-20240229": {"input": 0.000015, "output": 0.000075},
    "gpt-4o": {"input": 0.0000025, "output": 0.000010},
    "gpt-4o-mini": {"input": 0.000000150, "output": 0.000000600},
    "gemini-1.5-flash": {"input": 0.0, "output": 0.0},
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
    "gemini-2.5-flash": {"input": 0.0, "output": 0.0},
    "qwen2.5-coder": {"input": 0.0, "output": 0.0},
    "qwen2.5-coder:7b": {"input": 0.0, "output": 0.0}
}

class AgentRunner:
    """
    Orchestrates the ReAct execution loop, handling LLM requests,
    tracking tokens, checking budgets, parsing commands, and executing tools.
    Supports Anthropic, OpenAI, Google Gemini, and Local Ollama providers.
    """
    def __init__(self, tools: Dict[str, Any], max_turns: int = 30, max_budget_usd: float = 20.0):
        self.tools = tools
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        
        self.provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
        self.model = os.environ.get("LLM_MODEL")
        
        if self.provider == "anthropic":
            self.model = self.model or "claude-3-5-sonnet-20241022"
            self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            
        elif self.provider == "openai":
            self.model = self.model or "gpt-4o"
            self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            
        elif self.provider == "gemini":
            self.model = self.model or "gemini-1.5-flash"
            # Using Google Gemini's OpenAI Compatibility Endpoint
            self.client = openai.OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=os.environ.get("GEMINI_API_KEY")
            )
            
        elif self.provider == "ollama":
            self.model = self.model or "qwen2.5-coder:7b"
            # Connecting to local Ollama running on your machine
            self.client = openai.OpenAI(
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key="ollama"  # Placeholder value required by the SDK
            )
            
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
            
        self.total_cost = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        rates = PRICING.get(self.model, {"input": 0.0, "output": 0.0})
        cost = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
        self.total_cost += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        return cost

    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Invokes the selected LLM API, tracking token usage and cost."""
        if self.provider == "anthropic":
            anth_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    continue
                anth_messages.append({"role": msg["role"], "content": msg["content"]})
                
            response = self.client.messages.create(
                model=self.model,
                system=SYSTEM_PROMPT,
                messages=anth_messages,
                max_tokens=4000,
                temperature=0.2
            )
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            self._calculate_cost(input_tokens, output_tokens)
            return response.content[0].text
            
        elif self.provider in ("openai", "gemini", "ollama"):
            # All these providers share the OpenAI client SDK structure
            openai_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=0.2
            )
            
            # Extract token usage if returned by the API
            input_tokens = 0
            output_tokens = 0
            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                
            self._calculate_cost(input_tokens, output_tokens)
            return response.choices[0].message.content
            
        return ""

    def _parse_action(self, text: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Parses the Action JSON block out of the model's text response."""
        # Try to find standard JSON markdown block first
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        json_str = match.group(1) if match else None
        
        if not json_str:
            # Fallback search for a JSON object in the "Action:" section
            action_idx = text.find("Action:")
            if action_idx != -1:
                sub_text = text[action_idx + 7:]
                start_idx = sub_text.find("{")
                end_idx = sub_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    json_str = sub_text[start_idx:end_idx + 1]
                    
        if json_str:
            try:
                data = json.loads(json_str)
                return data.get("name"), data.get("args", {})
            except json.JSONDecodeError:
                pass
        return None, None

    def run(self, issue_title: str, issue_body: str) -> Dict[str, Any]:
        """Executes the main ReAct agent execution loop."""
        logger.info(f"Starting agent run for issue: {issue_title}")
        start_time = time.time()
        
        user_prompt = (
            f"Issue Title: {issue_title}\n\n"
            f"Issue Body:\n{issue_body}\n\n"
            f"Please identify the cause of this issue, implement a fix, and run the test suite to verify your solution."
        )
        
        messages = [{"role": "user", "content": user_prompt}]
        turns = 0
        final_answer = None
        status = "running"
        history = []

        while turns < self.max_turns:
            if self.total_cost >= self.max_budget_usd:
                status = "budget_exceeded"
                logger.warning(f"Budget of ${self.max_budget_usd} exceeded.")
                break
                
            turns += 1
            logger.info(f"--- Turn {turns} ---")
            
            # Step 1: Call LLM
            try:
                # Rate limit guard: Sleep for 12 seconds if using Gemini to prevent 429 quota limits
                if turns > 1 and self.provider == "gemini":
                    logger.info("Rate limit guard: Sleeping for 12 seconds between turns...")
                    time.sleep(12)
                llm_response = self._call_llm(messages)
            except Exception as e:
                logger.error(f"LLM API call failed: {e}")
                status = "api_error"
                break
                
            # Add assistant response to history
            messages.append({"role": "assistant", "content": llm_response})
            history.append({"turn": turns, "role": "assistant", "content": llm_response})
            
            # Step 2: Check for Final Answer
            if "Final Answer:" in llm_response:
                final_answer_idx = llm_response.find("Final Answer:")
                final_answer = llm_response[final_answer_idx + 13:].strip()
                status = "success"
                logger.info("Agent reached a Final Answer.")
                break
                
            # Step 3: Parse tool Action
            tool_name, tool_args = self._parse_action(llm_response)
            if not tool_name:
                observation = (
                    "Error: No valid action block found. Please output your next step in the specified "
                    "Thought/Action format, or provide a Final Answer if you are finished."
                )
                logger.warning("No action parsed from response.")
            else:
                # Step 4: Execute tool
                logger.info(f"Invoking tool: {tool_name} with args {tool_args}")
                tool = self.tools.get(tool_name)
                if not tool:
                    observation = f"Error: Tool '{tool_name}' is not supported. Available tools are: {list(self.tools.keys())}."
                else:
                    try:
                        if tool_name == "repo_map":
                            res = tool.generate_map()
                            observation = f"Tool output:\n{res}"
                        elif tool_name == "ripgrep":
                            res = tool.search(**tool_args)
                            observation = f"Tool output (exit code {res['exit_code']}):\nStdout:\n{res['stdout']}\nStderr:\n{res['stderr']}"
                        elif tool_name == "read_file":
                            res = tool.read_file(**tool_args)
                            if res["success"]:
                                observation = f"Tool output (lines {res['start_line']}-{res['end_line']} of {res['total_lines']}):\n{res['content']}"
                            else:
                                observation = f"Tool output: Error: {res['error']}"
                        elif tool_name == "write_file":
                            res = tool.write_file(**tool_args)
                            if res["success"]:
                                observation = f"Tool output: {res['message']}"
                            else:
                                observation = f"Tool output: Error: {res['error']}"
                        elif tool_name == "edit_file":
                            res = tool.edit_file(**tool_args)
                            if res["success"]:
                                observation = f"Tool output: {res['message']}"
                            else:
                                observation = f"Tool output: Error: {res['error']}"
                        elif tool_name == "execute_command":
                            res = tool.run(**tool_args)
                            observation = f"Tool output (exit code {res['exit_code']}):\nStdout:\n{res['stdout']}\nStderr:\n{res['stderr']}"
                        else:
                            observation = f"Error: Tool execution logic not mapped for '{tool_name}'."
                    except Exception as e:
                        logger.error(f"Error executing tool '{tool_name}': {e}")
                        observation = f"Error executing tool: {str(e)}"

            # Format observation for agent context
            observation_formatted = f"Observation: {observation}"
            logger.info(f"Observation size: {len(observation_formatted)} chars")
            
            # Append observation to context
            messages.append({"role": "user", "content": observation_formatted})
            history.append({"turn": turns, "role": "observation", "content": observation_formatted})

        if status == "running" and turns >= self.max_turns:
            status = "max_turns_exceeded"
            logger.warning("Max turns reached without final answer.")

        execution_time = time.time() - start_time
        return {
            "status": status,
            "turns": turns,
            "total_cost_usd": round(self.total_cost, 4),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "execution_time_seconds": round(execution_time, 2),
            "final_answer": final_answer,
            "history": history
        }
