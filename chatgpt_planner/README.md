# ChatGPT direct GPSR planner

This directory defines the experimental baseline in which one OpenAI model performs both jobs currently split between Qwen and CLIPS:

```text
GPSR command -> semantic goals -> executor-compatible plan
```

Files:

- `system_prompt.md`: static English system prompt, version 1.0.
- `response_schema.json`: strict JSON Schema for Structured Outputs.
- `example_outputs.jsonl`: executable, clarification, and rejection examples.

The executable response preserves two auditable artifacts: normalized semantic `goals` and CLIPS-compatible plan steps. `status/message` are a safety extension for inputs that should not be forced into a plan.

## Responses API sketch

The exact model must be selected and frozen before the thesis experiment. Record its snapshot, prompt hash, parameters, token usage, latency, and API date for every run.

```python
import json
from pathlib import Path

from openai import OpenAI

base = Path("chatgpt_planner")
system_prompt = (base / "system_prompt.md").read_text(encoding="utf-8")
schema = json.loads((base / "response_schema.json").read_text(encoding="utf-8"))

client = OpenAI()
response = client.responses.create(
    model="PINNED_MODEL_SNAPSHOT",
    input=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "go to the kitchen and find an apple"},
    ],
    text={
        "format": {
            "type": "json_schema",
            "name": "gpsr_direct_plan",
            "strict": True,
            "schema": schema,
        }
    },
)

result = json.loads(response.output_text)
print(result)
print(response.usage)
```

Structured Outputs constrains the shape, types, required fields, and action enum. It does not prove that a plan is semantically correct. Validate the returned plan with a deterministic checker before simulation or robot execution.

## Compatibility target and known discrepancy

The prompt follows the behavior documented in both repository READMEs and in `docs/goals_planning_rules.md`, with manipulation enabled. Executable plans target the `ros-message` contract consumed by `PlanExtractor`.

There is currently one material inconsistency to resolve before the thesis benchmark: `goal_schema.py`, `dataset_evaluation.py`, `command_goals.py`, and the documentation support `place(object, at=destination)`, but the runtime `ClipsGoalFactBuilder` in `goals_to_clips_node.py` does not include `at` when it builds the CLIPS destination. Consequently, a Qwen command such as “bring an apple from the bed to the cabinet” can lose `cabinet` in the live ROS path even though the offline validator accepts it. This prompt implements the documented/intended behavior and keeps the destination. Fix the runtime adapter or explicitly version that difference before comparing systems.

## Experimental controls

Use the same command set for Qwen+CLIPS, ChatGPT+CLIPS, and ChatGPT-direct. For the direct planner, run multiple repetitions per command and preserve the raw response. Compare goal correctness, final-state satisfaction, invalid actions, precondition violations, consistency, latency, tokens, and cost.

The prompt is static and intentionally written in English. English is not guaranteed to use fewer tokens for every model or passage; measure `input_tokens` rather than assuming a fixed saving. Keep the static prefix byte-identical between requests so provider-side prompt caching can be evaluated separately.

## Local artifact validation

The schema and bundled examples can be checked without making an API request:

```bash
python - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

base = Path("chatgpt_planner")
schema = json.loads((base / "response_schema.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
for line in (base / "example_outputs.jsonl").read_text().splitlines():
    validator.validate(json.loads(line)["response"])
print("schema and examples: OK")
PY
```
