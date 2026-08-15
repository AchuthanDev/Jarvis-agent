# Tools

JARVIS uses typed tools instead of hardcoded voice-command branches. The model may request
one tool at a time with JSON:

```json
{"tool": "tool.name", "arguments": {"key": "value"}}
```

The agent loop validates the request before execution:

1. Tool exists in the registry.
2. Arguments match the tool's JSON Schema.
3. Permission policy allows the tool risk for the current user/device context.
4. Execution is bounded by the tool timeout.
5. Result, denial, validation error, or failure is recorded in `tool_calls` and `audit_logs`.

## Built-In Tools

| Tool | Risk | Purpose |
|---|---:|---|
| `current_time` | 0 | Server date/time, optionally for an IANA timezone. |
| `server.system_status` | 0 | Host CPU, memory, disk, uptime, platform details. |
| `web.search` | 0 | Lightweight web search result list. |
| `memory.remember` | 1 | Store a user-approved fact/preference/episodic note. |
| `memory.recall` | 0 | Retrieve stored memories, optionally by text query. |
| `devices.list` | 0 | List registered devices and live presence. |
| `windows.open_url` | 1 | Open a URL on a connected Windows companion. |
| `windows.open_app` | 1 | Open an allowlisted app on a connected Windows companion. |
| `windows.notification` | 1 | Show a notification on a connected Windows companion. |
| `windows.system_info` | 0 | Read basic info from a connected Windows companion. |

## Adding A Tool

Create a small async function that accepts typed arguments and `context: ToolContext`,
then register a `Tool` instance from a built-in module or plugin:

```python
Tool(
    name="example.lookup",
    description="Look up an example by ID.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "string", "minLength": 1}},
        "required": ["id"],
        "additionalProperties": False,
    },
    fn=lookup_example,
    risk=RISK_READ_ONLY,
    timeout=10.0,
)
```

Adding tools must not require changes to the agent loop. Device-specific actions belong in
device agents and are exposed centrally as validated tools.
