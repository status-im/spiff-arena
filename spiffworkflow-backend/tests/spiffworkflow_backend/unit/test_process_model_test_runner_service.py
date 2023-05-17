import os
from typing import Any

import pytest
from flask import current_app
from flask import Flask
from pytest_mock import MockerFixture
from tests.spiffworkflow_backend.helpers.base_test import BaseTest

from spiffworkflow_backend.models.task import TaskModel  # noqa: F401
from spiffworkflow_backend.services.file_system_service import FileSystemService
from spiffworkflow_backend.services.process_model_test_runner_service import ProcessModelTestRunnerService


class TestProcessModelTestRunnerService(BaseTest):
    def test_can_test_a_simple_process_model(
        self,
        app: Flask,
        with_db_and_bpmn_file_cleanup: None,
        with_mocked_root_path: Any,
    ) -> None:
        test_runner_service = ProcessModelTestRunnerService(
            os.path.join(FileSystemService.root_path(), "basic_script_task")
        )
        test_runner_service.run()
        assert test_runner_service.process_model_test_runner.all_test_cases_passed()

    def test_can_test_multiple_process_models(
        self,
        app: Flask,
        with_db_and_bpmn_file_cleanup: None,
        with_mocked_root_path: Any,
    ) -> None:
        test_runner_service = ProcessModelTestRunnerService(FileSystemService.root_path())
        test_runner_service.run()
        assert test_runner_service.process_model_test_runner.all_test_cases_passed() is False

    @pytest.fixture()
    def with_mocked_root_path(self, mocker: MockerFixture) -> None:
        path = os.path.join(
            current_app.instance_path,
            "..",
            "..",
            "tests",
            "data",
            "bpmn_unit_test_process_models",
        )
        mocker.patch.object(FileSystemService, attribute="root_path", return_value=path)
