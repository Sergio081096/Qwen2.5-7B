"""Planificador local con las reglas y el adaptador versionados de Justina."""
from dataclasses import asdict
import json
import time

from .common import ROOT, INITIAL_STATE
from .vendor.goal_adapter import GoalParser, ClipsGoalFactBuilder


class SymbolicPlanner:
    def __init__(self, rules):
        import clips
        self.env = clips.Environment()
        self.router = self._router(clips)
        self.env.add_router(self.router)
        start = time.perf_counter()
        for path in rules:
            self.env.load(str(path))
        self.load_ms = (time.perf_counter()-start)*1000
        self.parser = GoalParser()
        self.builder = ClipsGoalFactBuilder()

    @staticmethod
    def _router(clips):
        class Capture(clips.Router):
            def __init__(self):
                super().__init__('experiment-capture', 30)
                self.messages = []

            def query(self, name):
                return name in ('stdout', 'stderr', 'stdwrn')

            def write(self, name, message):
                self.messages.append({'stream': name, 'text': message})
        return Capture()

    def adapt(self, goals):
        parsed = self.parser.parse_many(json.dumps({'goals': goals}))
        facts = self.builder.build(parsed)
        # Both original expressions and adapted objects are kept; no inverse serialization.
        return [asdict(g) for g in parsed], facts

    def plan(self, facts, initial_state):
        # The imported rules initialize these values themselves. Reject unsupported states.
        if initial_state != INITIAL_STATE:
            raise ValueError('Las reglas requieren el estado inicial documentado')
        self.router.messages.clear()
        self.env.reset()
        for fact in facts:
            self.env.assert_string(fact)
        self.env.assert_string('(start (name action-planning))')
        return self.env.run()

    def extract(self, rules_fired):
        plan, pending, notes, raw = [], [], [], []
        for fact in self.env.facts():
            name = fact.template.name
            if name == 'ros-message':
                plan.append({'step': int(fact['step']), 'robot': str(fact['robot']),
                             'action': str(fact['action']),
                             'params': [str(p) for p in fact['params']]})
                raw.append(str(fact))
            elif name == 'gpsr-goal':
                pending.append(str(fact))
            elif name == 'plan-note':
                notes.append({'robot': str(fact['robot']), 'state': str(fact['state'])})
        plan.sort(key=lambda p: p['step'])
        lines = [f"=={n['robot']} {n['state']}==" for n in notes if 'START' in n['state']]
        lines += [f"Paso {p['step']}: {p['robot']} {p['action']} {' '.join(p['params'])}".strip() for p in plan]
        lines += [f"=={n['robot']} {n['state']}==" for n in notes if 'START' not in n['state'] and 'DONE' not in n['state']]
        lines += [f"=={n['robot']} {n['state']}==" for n in notes if 'DONE' in n['state']]
        unsupported = any('I do not know how to execute goal' in ' '.join(p['params']) for p in plan)
        return plan, dict(clips_plan_raw='\n'.join(lines), ros_message_facts=raw,
                          plan_notes=notes, rules_fired=rules_fired,
                          planning_done=any(n['state'] == 'GPSR_DONE' for n in notes),
                          remaining_goals=pending, unsupported_goal=unsupported,
                          diagnostics=list(self.router.messages))

    def close(self):
        self.env.clear()
