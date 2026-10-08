"""Las entradas del servicio deben encontrar sus datos desde otro directorio."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from qwen_gpsr.domain.command_normalizer import CommandNormalizer, DATA_DIR
from qwen_gpsr.domain.knowledge import parse_data
from qwen_gpsr.evaluation.evaluate_model import DEFAULT_BENCHMARK, load_benchmark


class RuntimePathTests(unittest.TestCase):
    def test_catalog_and_benchmark_work_outside_repository(self):
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                normalizer = CommandNormalizer(parse_data(DATA_DIR))
                self.assertEqual(
                    normalizer.normalize("please go to the kichen"),
                    "go to the kitchen",
                )
                self.assertTrue(load_benchmark(DEFAULT_BENCHMARK))
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
