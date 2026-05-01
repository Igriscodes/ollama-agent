#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
import fnmatch
import textwrap
import readline
import difflib
from pathlib import Path

def install_and_import(package):
    try:
        return __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])
        return __import__(package)

requests = install_and_import("requests")
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.formatters import TerminalFormatter
    HAS_PYGMENTS = True
except ImportError:
    try:
        install_and_import("pygments")
        from pygments import highlight
        from pygments.lexers import get_lexer_for_filename, TextLexer
        from pygments.formatters import TerminalFormatter
        HAS_PYGMENTS = True
    except:
        HAS_PYGMENTS = False

R    = "\033[0m"
BOLD = "\033[1m"
RED  = "\033[91m"
GRN  = "\033[92m"
YLW  = "\033[93m"
BLU  = "\033[94m"
CYN  = "\033[96m"
GRY  = "\033[90m"

def c(text, color): return f"{color}{text}{R}"

OLLAMA_BASE      = "http://localhost:11434"
MAX_HISTORY      = 20
MAX_DIR_FILES    = 60
MAX_STEPS        = 20
IGNORE_PATTERNS  = [".git", "__pycache__", "*.pyc", "node_modules", ".venv", "venv", "*.egg-info", ".DS_Store"]
ALLOW_WRITE_ALL  = False

SYSTEM_PROMPT_HEADER = """You are an autonomous coding agent running on the user's real filesystem.

Available tools:
  read_file(path)                         - read a file's full content
  write_file(path, content)               - write/overwrite a file
  replace_in_file(path, old, new)         - surgical edit: replaces exactly ONE occurrence of 'old' with 'new'
  list_files(directory)                   - list files in a directory
  run_command(command)                    - run a shell command
  search_files(query)                     - search file names and contents
  task_complete(summary)                  - call ONLY when the task is fully done

## Speculative Pipelining
You can emit MULTIPLE actions in one turn to be faster. 
Example: Write a file AND run it immediately to verify.

Example JSON:
{
  "thought": "I will create a hello world script and run it to verify.",
  "todo": ["Write hello.py", "Run hello.py"],
  "actions": [
    {"tool": "write_file", "args": {"path": "hello.py", "content": "print('hello')"}},
    {"tool": "run_command", "args": {"command": "python3 hello.py"}}
  ]
}
"""

SYSTEM_PROMPT_FOOTER = """
STRICT OUTPUT RULE: Respond ONLY with a single valid JSON object. No markdown fences, no prose.

JSON schema:
{
  "thought": "<concise reasoning>",
  "todo": ["<remaining steps>"],
  "actions": [
    {"tool": "<tool_name>", "args": {"<key>": "<value>"}}
  ]
}

CRITICAL RULES:
1. You MAY use multiple actions if they are part of a logical sequence (e.g. write then run).
2. NEVER call task_complete in the same response as other tools.
3. Call task_complete ONLY after you have seen the result of your actions.
4. NO PROSE: Respond only with JSON.
5. ONLY perform the task explicitly requested by the user. Do not invent new tasks or projects.
"""

def should_ignore(name: str) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)

def tree_summary(root: str = ".") -> str:
    lines = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_ignore(d)]
        rel = os.path.relpath(dirpath, root)
        for f in filenames:
            if should_ignore(f): continue
            prefix = "" if rel == "." else f"{rel}/"
            lines.append(f"  {prefix}{f}")
            count += 1
            if count >= MAX_DIR_FILES:
                lines.append("  ... (truncated)")
                return "\n".join(lines)
    return "\n".join(lines) or "  (empty)"

def render_code(path, content):
    if not HAS_PYGMENTS:
        print(c(content, GRY))
        return
    try:
        lexer = get_lexer_for_filename(path)
    except:
        lexer = TextLexer()
    print(highlight(content, lexer, TerminalFormatter()))

def tool_read_file(path: str) -> str:
    try:
        with open(path, "r", errors="replace") as fh:
            return fh.read()
    except Exception as e:
        return f"ERROR: {e}"

def tool_write_file(path: str, content: str) -> str:
    global ALLOW_WRITE_ALL
    existing = tool_read_file(path)
    if not existing.startswith("ERROR"):
        print(c(f"\n  --- DIFF FOR: {path} ---", CYN + BOLD))
        diff = list(difflib.unified_diff(
            existing.splitlines(), content.splitlines(),
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=''
        ))
        for line in diff:
            if line.startswith('+'): print(c(line, GRN), end='\n')
            elif line.startswith('-'): print(c(line, RED), end='\n')
            else: print(line)
    else:
        print(c(f"\n  --- NEW FILE: {path} ---", CYN + BOLD))
        render_code(path, content)
    print(c("  " + "-" * (len(path) + 20), CYN))
    if not ALLOW_WRITE_ALL:
        ans = input(c(f"  Write to '{path}'? [y]es / [n]o / [a]lways: ", YLW)).strip().lower()
        if ans == 'a': ALLOW_WRITE_ALL = True
        elif ans != 'y': return "ERROR: Permission denied by user."
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)
        return f"Written: {path} ({len(content)} bytes)"
    except Exception as e:
        return f"ERROR: {e}"

def tool_replace_in_file(path: str, old: str, new: str) -> str:
    content = tool_read_file(path)
    if content.startswith("ERROR"): return content
    count = content.count(old)
    if count == 0: return f"ERROR: String '{old}' not found in {path}"
    if count > 1: return f"ERROR: String '{old}' found {count} times. Be more specific."
    new_content = content.replace(old, new)
    return tool_write_file(path, new_content)

def tool_list_files(directory: str = ".") -> str:
    try:
        entries = sorted(os.listdir(directory))
        lines = []
        for e in entries:
            if should_ignore(e): continue
            tag = "/" if os.path.isdir(os.path.join(directory, e)) else ""
            lines.append(f"  {e}{tag}")
        return "\n".join(lines) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"

def tool_run_command(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        parts = []
        if result.stdout.strip(): parts.append(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip(): parts.append(f"STDERR:\n{result.stderr.strip()}")
        parts.append(f"EXIT: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return "ERROR: Timed out (60s)"
    except Exception as e:
        return f"ERROR: {e}"

def tool_search_files(query: str, root: str = ".") -> str:
    results = []
    q = query.lower()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_ignore(d)]
        for fname in filenames:
            if should_ignore(fname): continue
            full = os.path.join(dirpath, fname)
            rel  = os.path.relpath(full, root)
            if q in fname.lower():
                results.append(f"[name]    {rel}")
                continue
            try:
                with open(full, "r", errors="replace") as fh:
                    for i, line in enumerate(fh, 1):
                        if q in line.lower():
                            results.append(f"[content] {rel}:{i}: {line.strip()[:120]}")
                            break
            except Exception: pass
        if len(results) >= 30: break
    return "\n".join(results) if results else "No matches found."

def list_ollama_models() -> list:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []

def stream_ollama(model: str, messages: list) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={"model": model, "messages": messages, "stream": True, "format": "json"},
            stream=True, timeout=180,
        )
        resp.raise_for_status()
    except Exception as e:
        print(c(f"\nERROR: {e}", RED))
        return ""
    full = []
    for raw in resp.iter_lines():
        if not raw: continue
        try:
            chunk = json.loads(raw)
            delta = chunk.get("message", {}).get("content", "")
            if delta: full.append(delta)
            if chunk.get("done"): break
        except json.JSONDecodeError: continue
    return "".join(full)

def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end   = -1 if lines[-1].strip() == "```" else len(lines)
        text  = "\n".join(lines[1:end])
    start = text.find("{")
    if start == -1: return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":   depth += 1
        elif ch == "}": depth -= 1
        if depth == 0:
            try: return json.loads(text[start:i+1])
            except: return None
    return None

def render_plan(parsed: dict):
    if thought := parsed.get("thought", ""):
        print(c(f"\n  ■ {thought}", BLU + BOLD))
    if todo := parsed.get("todo", []):
        print(c("\n  TODO:", YLW + BOLD))
        for i, item in enumerate(todo, 1):
            print(c(f"    {i}. {item}", YLW))

def get_action_summary(actions: list) -> str:
    summaries = []
    for action in actions:
        tool = action.get("tool", "")
        args = action.get("args", {})
        if isinstance(args, str): args = {"value": args}
        elif not isinstance(args, dict): args = {}
        if tool == "read_file": summaries.append(f"Reading: {args.get('path', 'file')}")
        elif tool == "write_file": summaries.append(f"Writing: {args.get('path', 'file')}")
        elif tool == "replace_in_file": summaries.append(f"Patching: {args.get('path', 'file')}")
        elif tool == "list_files": summaries.append(f"Listing: {args.get('directory', '.')}")
        elif tool == "run_command": summaries.append(f"Exec: {args.get('command', '')[:40]}")
        elif tool == "search_files": summaries.append(f"Search: {args.get('query', '')[:30]}")
        elif tool == "task_complete": summaries.append("Done")
        else: summaries.append(f"Tool: {tool}")
    return " | ".join(summaries) or "Working..."

def execute_actions(actions: list, cwd: str) -> tuple:
    observations = []
    for action in actions:
        tool = action.get("tool", "")
        args = action.get("args", {})
        if isinstance(args, str):
            mapping = {"read_file": "path", "list_files": "directory", "run_command": "command", "search_files": "query", "write_file": "path"}
            args = {mapping.get(tool, "value"): args}
        elif not isinstance(args, dict): args = {}
        if tool == "read_file": out = tool_read_file(os.path.join(cwd, args.get("path", "")))
        elif tool == "write_file": out = tool_write_file(os.path.join(cwd, args.get("path", "")), args.get("content", ""))
        elif tool == "replace_in_file": out = tool_replace_in_file(os.path.join(cwd, args.get("path", "")), args.get("old", ""), args.get("new", ""))
        elif tool == "list_files": out = tool_list_files(os.path.join(cwd, args.get("directory", ".")))
        elif tool == "run_command": out = tool_run_command(args.get("command", ""))
        elif tool == "search_files": out = tool_search_files(args.get("query", ""), cwd)
        elif tool == "task_complete":
            print(c(f"\n  ✓ {args.get('summary', 'Task complete.')}", GRN + BOLD))
            return "", True
        else: out = f"ERROR: Unknown tool '{tool}'"
        observations.append(f"[{tool}] result:\n{out}")
    return "\n\n".join(observations), False

def run_agent(model: str, cwd: str):
    memory: list = []
    
    STARTER_PROMPTS = [
        "list files in the current directory",
        "create a python script that prints 'hello from agent'",
        "run 'ls -la' to see hidden files",
    ]
    for prompt in STARTER_PROMPTS:
        readline.add_history(prompt)

    def system():
        return f"{SYSTEM_PROMPT_HEADER}\nWorking directory: {cwd}\nProject files:\n{tree_summary(cwd)}\n{SYSTEM_PROMPT_FOOTER}"
    
    print(c(f"\n  Agent active | model: {model}", GRN))
    print(c("  (Press ↑ to explore example prompts)\n", GRY))
    
    while True:
        try: user_input = input(c("▶ ", BLU + BOLD)).strip()
        except (KeyboardInterrupt, EOFError): break
        if not user_input or user_input.lower() in ("exit", "quit"): break
        messages = [{"role": "system", "content": system()}] + memory + [{"role": "user", "content": user_input}]
        step = 0
        task_done = False
        while step < MAX_STEPS and not task_done:
            step += 1
            print(c(f"  Step {step} Thinking...", YLW), end="\r", flush=True)
            raw = stream_ollama(model, messages)
            print(" " * 40, end="\r")
            if not raw: break
            parsed = extract_json(raw)
            if not parsed:
                messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": "Invalid JSON."}]
                continue
            render_plan(parsed)
            actions = parsed.get("actions", [])
            if not actions:
                messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": "No actions."}]
                continue
            print(c(f"  → {get_action_summary(actions)}", GRY), flush=True)
            observation, task_done = execute_actions(actions, cwd)
            if task_done:
                memory += [{"role": "user", "content": user_input}, {"role": "assistant", "content": raw}]
                break
            messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": f"OBSERVATION:\n{observation}\n\nIf the task is fully complete, call task_complete. Otherwise, continue with the next step."}]
        print()

def pick_model(arg_model: str) -> str:
    if arg_model: return arg_model
    models = list_ollama_models()
    if not models: return "llama3"
    print(c("\nModels:", BLU + BOLD))
    for i, m in enumerate(models, 1): print(c(f"  {i}. {m}", GRY))
    ans = input(c(f"\nSelect [1-{len(models)}]: ", BLU)).strip()
    if ans.isdigit() and 1 <= int(ans) <= len(models): return models[int(ans)-1]
    return models[0] if models else "llama3"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", "-m")
    parser.add_argument("--cwd", "-C", default=".")
    args = parser.parse_args()
    cwd = os.path.abspath(args.cwd)
    print(c("""
  ╔══════════════════════════════════════╗
  ║     Ollama Coding Agent              ║
  ╚══════════════════════════════════════╝""", BLU + BOLD))
    run_agent(pick_model(args.model), cwd)

if __name__ == "__main__":
    main()
