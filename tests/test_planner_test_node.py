import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from chatgpt_planner.planner_test_node import BASE, load_artifacts, run_request, validate_result


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.prompt, self.schema = load_artifacts()
        self.example = json.loads((BASE / 'example_outputs.jsonl').read_text().splitlines()[0])['response']

    def test_rejects_broken_contracts(self):
        for mutate in (
            lambda r: r.update(status='clarification', message='Where?'),
            lambda r: r['plan'][1].update(step=1),
            lambda r: r['plan'][4].update(params=[]),
            lambda r: r['plan'][-1].update(params=['unfinished']),
            lambda r: r.update(goals=['place(apple, on=table)']),
        ):
            result = copy.deepcopy(self.example)
            mutate(result)
            with self.subTest(result=result), self.assertRaises(ValueError):
                validate_result(result, self.schema)

    def test_deprecated_goals_rejected_but_executor_drop_allowed(self):
        validate_result(self.example, self.schema)
        for old_goal in ('drop(apple, on=table)', 'talk(about_yourself)'):
            result = copy.deepcopy(self.example)
            result['goals'][-1] = old_goal
            with self.subTest(goal=old_goal), self.assertRaisesRegex(ValueError, 'Goals obsoletos'):
                validate_result(result, self.schema)
        result = copy.deepcopy(self.example)
        result['goals'].append('tell(about_yourself)')
        validate_result(result, self.schema)

    def test_api_boundary_and_logging(self):
        for status, content, output_text, expected in (
            ('completed', [], json.dumps(self.example), True),
            ('incomplete', [], '', False),
            ('completed', [SimpleNamespace(type='refusal', refusal='Denied')], '', False),
            ('completed', [], '{broken', False),
        ):
            calls = []
            response = SimpleNamespace(status=status, output=[SimpleNamespace(content=content)], output_text=output_text,
                                       model_dump=lambda **kwargs: {'status': status, 'model': 'test-model'})
            def create(**kwargs):
                calls.append(kwargs)
                return response
            client = SimpleNamespace(responses=SimpleNamespace(create=create))
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'results.jsonl'
                record = run_request(client, 'test', 'test-model', self.prompt, self.schema, output, 8192)
                self.assertEqual(record['valid'], expected)
                self.assertEqual(json.loads(output.read_text()), record)
                self.assertEqual(calls[0]['input'][0]['content'], self.prompt)
                self.assertTrue(calls[0]['text']['format']['strict'])

    def test_transport_failure_is_logged_without_exception_text(self):
        def create(**kwargs):
            raise RuntimeError('sensitive error details')
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results.jsonl'
            record = run_request(client, 'test', 'test-model', self.prompt, self.schema, output, 8192)
            self.assertFalse(record['valid'])
            self.assertEqual(record['error'], 'RuntimeError')
            self.assertNotIn('sensitive', output.read_text())


if __name__ == '__main__':
    unittest.main()
