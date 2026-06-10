# Tool Audit — 2026-06-10

**`tool_schemas.py` ISAAC_SIM_TOOLS:** 441 tools
**`tool_executor.py` monolith size:** 557 lines
**Dead handlers (registered but no schema):** 0

**Status counts:**
- `none_explicit`: 12
- `real`: 429

## `none_explicit` (12)

| name | in DATA | DATA callable | in CODE_GEN | CODE_GEN callable |
|---|---|---|---|---|
| `explain_error` | True | False | False | False |
| `ros2_call_service` | True | False | False | False |
| `ros2_connect` | True | False | False | False |
| `ros2_get_message_type` | True | False | False | False |
| `ros2_get_node_details` | True | False | False | False |
| `ros2_get_topic_type` | True | False | False | False |
| `ros2_list_nodes` | True | False | False | False |
| `ros2_list_services` | True | False | False | False |
| `ros2_list_topics` | True | False | False | False |
| `ros2_publish` | True | False | False | False |
| `ros2_publish_sequence` | True | False | False | False |
| `ros2_subscribe_once` | True | False | False | False |

## `real` (429)

(table omitted for brevity — these are healthy entries)

## Allowlist (`tests/fixtures/no_handler_tools.json`)

Schema names whose handler value is intentionally `None` (handled inline by the LLM, special-cased in the orchestrator, or stubbed pending integration work).

- `explain_error`
- `ros2_call_service`
- `ros2_connect`
- `ros2_get_message_type`
- `ros2_get_node_details`
- `ros2_get_topic_type`
- `ros2_list_nodes`
- `ros2_list_services`
- `ros2_list_topics`
- `ros2_publish`
- `ros2_publish_sequence`
- `ros2_subscribe_once`

