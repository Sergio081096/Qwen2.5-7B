"""Validación de contratos; no atribuye corrección semántica."""
from jsonschema import Draft202012Validator
from qwen_gpsr.domain.goal_schema import validate_goals
from .common import REPO, read_json

DEFAULT_SCHEMA = read_json(REPO / 'chatgpt_planner/response_schema.json')
PLAN_SCHEMA = DEFAULT_SCHEMA['properties']['plan']


def schema_issues(value, schema):
    # Report location/validator, not exception text containing entire output.
    return [f'{"/".join(map(str, e.absolute_path)) or "$"}: {e.validator}'
            for e in Draft202012Validator(schema).iter_errors(value)]


def goals_issues(goals):
    if not isinstance(goals, list):
        return ['goals: expected list']
    return [str(issue) for issue in validate_goals(goals)]


def plan_issues(plan):
    issues = schema_issues(plan, PLAN_SCHEMA)
    if issues:
        return issues
    if not plan:
        return ['plan: empty executable plan']
    announcements = [p for p in plan if p['step'] < 1001]
    operations = [p for p in plan if p['step'] >= 1001]
    expected = list(range(1, len(announcements)+1)) + list(range(1001, 1001+len(operations)))
    if len(announcements) > 1000 or [p['step'] for p in plan] != expected:
        issues.append('plan: numbering out of order, duplicated or with gaps')
    if any(p['action'] != 'say' for p in announcements):
        issues.append('plan: announcement must be say')
    if any(len(p['params']) != 1 or not p['params'][0].strip() for p in plan):
        issues.append('plan: requires one nonempty parameter per step')
    if not operations or (operations[-1]['action'], operations[-1]['params']) != ('say', ['task completed']):
        issues.append('plan: missing completion step')
    return issues


def validate_gpt(result, schema):
    issues = schema_issues(result, schema)
    out = dict(response_schema_valid=not issues, goals_schema_valid=None,
               plan_contract_valid=None, issues=list(issues))
    if not isinstance(result, dict):
        return out
    status = result.get('status')
    if status == 'executable':
        gi = goals_issues(result.get('goals'))
        pi = plan_issues(result.get('plan'))
        out.update(goals_schema_valid=not gi, plan_contract_valid=not pi)
        out['issues'].extend(gi+pi)
        if result.get('message') != '' or result.get('start_note') != 'GPSR_START' or result.get('end_note') != 'GPSR_DONE':
            out['issues'].append('response: inconsistent executable fields')
            out['response_schema_valid'] = False
    elif status in ('clarification', 'rejected'):
        if (not isinstance(result.get('message'), str) or not result['message'].strip()
            or any(result.get(k) != [] for k in ('goals', 'plan'))
            or any(result.get(k) != '' for k in ('start_note', 'end_note'))):
            out['issues'].append('response: inconsistent clarification/rejection fields')
            out['response_schema_valid'] = False
    return out
