"""Selección de base desde el adaptador, sin cargar pesos."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qwen_gpsr.runtime import inference


class ModelVariantTests(unittest.TestCase):
    def test_adapter_selects_its_base_model(self):
        for size in ('3B','7B'):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                expected='Qwen/Qwen2.5-'+size
                (Path(directory)/'adapter_config.json').write_text(json.dumps({'base_model_name_or_path':expected}))
                with patch.object(inference,'BitsAndBytesConfig'), \
                     patch.object(inference,'load_model_config') as config, \
                     patch.object(inference.AutoModelForCausalLM,'from_pretrained') as base, \
                     patch.object(inference.PeftModel,'from_pretrained') as adapter:
                    inference.load_model('fixture-dtype',adapter_path=directory)
                    config.assert_called_once_with(expected)
                    self.assertEqual(base.call_args.args[0],expected)
                    adapter.assert_called_once_with(base.return_value,directory)
