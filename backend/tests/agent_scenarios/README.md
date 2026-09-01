# Agent Harness Scenarios

The canonical agent eval inputs live outside pytest under `backend/scenarios/agent/`.
Pytest verifies that the scenario files load and remain mapped to the old e2e
coverage, but live LLM behavior is evaluated through `app.agent_harness.cli`.

## Scenario Sets

- `backend/scenarios/agent/*.json` — curated v2 regression scenarios for the
  most important agent behaviors.
- `backend/scenarios/agent/e2e/*.json` — migrated legacy e2e cases generated
  from `backend/tests/e2e/test_messages.py`. Each file has `source.suite =
  "legacy_e2e"`, `source.case_id`, and `source.language` metadata.

## Commands

Run schema/loader checks without calling the backend:

```bash
cd backend
./.venv/bin/pytest tests/test_agent_harness_scenario.py \
  tests/test_agent_harness_scenarios_exist.py \
  tests/test_agent_harness_trace_schema.py -q
```

Run curated local eval against a local backend:

```bash
cd backend
./.venv/bin/python -m app.agent_harness.cli eval scenarios/agent \
  --env dev \
  --report reports/agent-v2-report.json \
  --trace-dir reports/agent-v2-traces
```

Run migrated legacy e2e eval against a local backend:

```bash
cd backend
./.venv/bin/python -m app.agent_harness.cli eval scenarios/agent/e2e \
  --env dev \
  --report reports/legacy-e2e-report.json \
  --trace-dir reports/legacy-e2e-traces
```

Run the same suites against the deployed backend by changing `--env dev` to
`--env prod`.
