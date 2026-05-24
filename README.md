# Ollama Agent

A lightweight, autonomous coding agent that runs locally using [Ollama](https://ollama.com/). It interacts directly with your real filesystem to read, write, patch, search, and execute code based on natural language instructions.

![RAG](https://www.bandt.com.au/information/uploads/2025/05/ChatGPT-Image-May-22-2025-10_32_44-AM-860x573.png)

## Features
- **Autonomous Execution**: Step-by-step reasoning with tool usage until task completion.
- **Speculative Pipelining**: Emit multiple actions in a single turn (e.g., write a file and run it immediately for verification).
- **Filesystem Tools**: Read, write, surgical edits, directory listing, content searching, and shell command execution.
- **Safe by Design**: File writes show a `diff` preview and require explicit user confirmation (`y`/`n`/`a`).
- **Model Agnostic**: Automatically discovers available Ollama models or accepts a specific model via CLI.
- **Syntax Highlighting**: Optional pretty-printing for file outputs via `pygments`.
- **Interactive CLI**: Built with `readline` history and example starter prompts.

## Prerequisites
- Python 3.8+
- [Ollama](https://ollama.com/) installed and running locally on `http://localhost:11434`
- At least one code-capable model pulled (e.g., `llama3`, `qwen3`, `exaone3.5`, etc.)

## Quick Start

1. **Ensure Ollama is running:**
   ```bash
   ollama serve
   ```

2. **Pull a model:**
   ```bash
   ollama pull llama3.2
   # or
   ollama pull exaone3.5:2.4b
   ```

3. **Run the agent:**
   ```bash
   python agent.py
   ```

Once started, the agent will prompt you for a task. Example prompts:
- `create a python script that prints 'hello from agent'`
- `list files in the current directory`
- `fix the bug in app.py`

## Available Tools
The agent uses a JSON-based tool-calling loop. Available tools include:

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read a file's full content |
| `write_file(path, content)` | Write/overwrite a file (with diff preview & confirmation) |
| `replace_in_file(path, old, new)` | Surgical edit: replaces exactly one occurrence |
| `list_files(directory)` | List files in a directory (auto-truncates large dirs) |
| `run_command(command)` | Execute a shell command (60s timeout) |
| `search_files(query)` | Search filenames and file contents |
| `task_complete(summary)` | Mark task as done and exit loop |

## Configuration & Flags
| Flag | Description |
|------|-------------|
| `-m, --model <name>` | Specify the Ollama model to use |
| `-C, --cwd <path>` | Set the working directory for the agent (default: `.`) |

## Safety & Notes
- **Real Filesystem Access**: This agent modifies actual files on your machine. Always review the `diff` previews before confirming writes.
- **JSON-Only Output**: The system prompt enforces strict JSON responses for reliable parsing.
- **Guardrails**: Max `20` steps per task, `20` message history context, and `60` files per directory listing to prevent runaway execution or context overflow.
- **Allow All Writes**: During execution, typing `a` (always) will bypass future write confirmations for the session.

## License
[GNU Lesser General Public License v2.1](LICENSE) - Feel free to use and modify
