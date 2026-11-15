import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend import DesignGeneration
from backend import Workspace


class DesignGenerationTests(unittest.TestCase):
    def test_provider_config_uses_existing_cohere_credentials(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                DesignGeneration,
                "dotenv_values",
                return_value={
                    "CohereApiKey": "cohere-test-key",
                    "CohereModel": "cohere-test-model",
                },
            ),
        ):
            config = DesignGeneration._provider_config()

        self.assertEqual(config, ("cohere-test-key", "cohere-test-model"))

    def test_provider_config_defaults_to_a_live_cohere_model(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(DesignGeneration, "dotenv_values", return_value={}),
        ):
            config = DesignGeneration._provider_config()

        self.assertEqual(config, (None, "command-a-03-2025"))

    def test_generation_uses_the_configured_model_and_validates_parts(self):
        expected_parts = [{
            "name": "Rocket Body",
            "shape": "cylinder",
            "position": [0.0, 0.0, 1.0],
            "size": [0.8, 0.8, 2.0],
        }]
        completion = SimpleNamespace(message=SimpleNamespace(content=[
            SimpleNamespace(text=json.dumps({"parts": expected_parts}))
        ]))
        client = Mock()
        client.chat.return_value = completion
        prompt = "a small rocket with fins"

        with (
            patch.object(
                DesignGeneration,
                "_provider_config",
                return_value=("test-key", "test-model"),
            ),
            patch.object(
                DesignGeneration.cohere, "ClientV2", return_value=client
            ) as client_factory,
        ):
            parts = DesignGeneration.generate_design_parts(prompt)

        self.assertEqual(parts, expected_parts)
        client_factory.assert_called_once_with(
            api_key="test-key",
            timeout=45,
            max_retries=0,
        )
        request = client.chat.call_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertEqual(request["messages"][1]["content"], prompt)

    def test_generation_rejects_missing_provider_configuration(self):
        with (
            patch.object(
                DesignGeneration,
                "_provider_config",
                return_value=(None, "test-model"),
            ),
            self.assertRaisesRegex(RuntimeError, "requires CohereApiKey"),
        ):
            DesignGeneration.generate_design_parts("a rocket")

    def test_generation_reports_an_incompatible_cohere_sdk(self):
        client = Mock()
        client.chat.side_effect = TypeError(
            "unexpected keyword argument 'response_format'"
        )
        with (
            patch.object(
                DesignGeneration,
                "_provider_config",
                return_value=("test-key", "test-model"),
            ),
            patch.object(DesignGeneration.cohere, "ClientV2", return_value=client),
            self.assertRaisesRegex(RuntimeError, "Update dependencies"),
        ):
            DesignGeneration.generate_design_parts("a rocket")

    def test_generation_rejects_invalid_or_unbounded_geometry(self):
        invalid_responses = (
            '{"parts":[]}',
            '{"parts":[{"name":"bad","shape":"mesh","position":[0,0,0],"size":[1,1,1]}]}',
            '{"parts":[{"name":"bad","shape":"box","position":[11,0,0],"size":[1,1,1]}]}',
        )
        for response in invalid_responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                DesignGeneration._validate_generated_parts(response)

    def test_workspace_saves_generated_geometry_and_builds_a_mesh(self):
        generated_parts = [
            {"name": "Hull", "shape": "box", "position": [0, 0, 0],
             "size": [2, 1, 0.5]},
            {"name": "Dome", "shape": "sphere", "position": [0, 0, 0.5],
             "size": [0.6, 0.6, 0.6]},
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Workspace"
            with (
                patch.object(Workspace, "WORKSPACE_ROOT", root),
                patch.object(
                    Workspace,
                    "generate_design_parts",
                    return_value=generated_parts,
                ) as generate,
            ):
                project = Workspace.create_design("a toy submarine")
                design = Workspace.load_design(project)
                mesh = Workspace.load_mesh(project)

        generate.assert_called_once_with("a toy submarine")
        self.assertEqual(len(design["parts"]), 2)
        self.assertGreater(len(mesh), 12)


if __name__ == "__main__":
    unittest.main()
