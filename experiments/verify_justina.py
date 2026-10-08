"""Compara el adaptador y planes locales con las fuentes de Justina sin ROS."""
import ast
from dataclasses import asdict
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from .common import ROOT, REPO, digest, read_json, read_jsonl, INITIAL_STATE
from .symbolic import SymbolicPlanner
from .vendor.goal_adapter import GoalParser, ClipsGoalFactBuilder


def classes_from_source(path, names, imports, extras=None):
    text=Path(path).read_text()
    nodes=[n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name in names]
    if {n.name for n in nodes}!=set(names):raise ValueError('Clases de Justina no encontradas')
    module=ModuleType('_justina_verification_'+Path(path).stem)
    sys.modules[module.__name__]=module
    if extras:module.__dict__.update(extras)
    exec(imports,module.__dict__)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),module.__dict__)
    return module,text


def verify(workspace, cases_path=None):
    base=Path(workspace)/'src/Planning/clips/clips_node'
    original,text=classes_from_source(base/'clips_node/goals_to_clips_node.py',
        ['ParsedGoal','GoalParser','ClipsGoalFactBuilder'],
        'import json, re, shlex\nfrom dataclasses import dataclass\nfrom typing import Dict,List,Optional,Tuple')
    extractor,_=classes_from_source(base/'clips_node/clips_components.py',['PlanExtractor'],
        'from typing import List, Optional',{'ClipsEngine':object})
    original_rules=base/'clips_rules/goals_planning.clp'
    provenance=read_json(ROOT/'vendor/provenance.json')
    rules_equal=digest(original_rules)==provenance['rules_sha256']
    def class_ast(source):
        return [ast.dump(n,include_attributes=False) for n in ast.parse(source).body
                if isinstance(n,ast.ClassDef) and n.name in provenance['classes']]
    adapter_equal=class_ast(text)==class_ast((ROOT/'vendor/goal_adapter.py').read_text())
    rows=read_jsonl(cases_path or REPO/'data/development/desarrollo_60_referencias.jsonl')
    goals=[r.get('goals_ref',r.get('goals')) for r in rows]
    goals=[g for g in goals if g is not None]
    goals.extend([['go(kitchen)'],['find(Water, kind=object)'],
                  ['go(bed)','find(apple, kind=object)','take(apple)','place(apple, at=cabinet)']])
    local=SymbolicPlanner([ROOT/'vendor/goals_planning.clp'])
    integrated=SymbolicPlanner([original_rules])
    failures=[]
    try:
        for i,g in enumerate(goals):
            parsed=original.GoalParser().parse_many(json.dumps({'goals':g}))
            expected_facts=original.ClipsGoalFactBuilder().build(parsed)
            adapted,facts=local.adapt(g)
            if facts!=expected_facts or adapted!=[asdict(x) for x in parsed]:
                failures.append({'case_index':i,'stage':'adaptation'})
            fired=local.plan(facts,INITIAL_STATE)
            plan,details=local.extract(fired)
            integrated.plan(expected_facts,INITIAL_STATE)
            # Exercise the actual PlanExtractor class, including sorting and note placement.
            lines=extractor.PlanExtractor(SimpleNamespace(_env=integrated.env)).extract()
            if details['clips_plan_raw']!='\n'.join(lines):failures.append({'case_index':i,'stage':'plan'})
    finally:
        local.close();integrated.close()
    return {'adapter_ast_equal':adapter_equal,'rules_sha256_equal':rules_equal,
            'cases_checked':len(goals),'failures':failures,
            'equivalent':adapter_equal and rules_equal and not failures}
