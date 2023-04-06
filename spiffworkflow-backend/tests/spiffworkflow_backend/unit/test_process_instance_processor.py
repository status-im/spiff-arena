"""Test_process_instance_processor."""
from uuid import UUID

import pytest
from flask import g
from flask.app import Flask
from flask.testing import FlaskClient
from SpiffWorkflow.task import Task as SpiffTask  # type: ignore
from SpiffWorkflow.task import TaskState
from tests.spiffworkflow_backend.helpers.base_test import BaseTest
from tests.spiffworkflow_backend.helpers.test_data import load_test_spec

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.bpmn_process import BpmnProcessModel
from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.group import GroupModel
from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
from spiffworkflow_backend.models.process_instance import ProcessInstanceStatus
from spiffworkflow_backend.models.task import TaskModel  # noqa: F401
from spiffworkflow_backend.models.task_definition import TaskDefinitionModel
from spiffworkflow_backend.models.user import UserModel
from spiffworkflow_backend.services.authorization_service import AuthorizationService
from spiffworkflow_backend.services.authorization_service import (
    UserDoesNotHaveAccessToTaskError,
)
from spiffworkflow_backend.services.process_instance_processor import (
    ProcessInstanceProcessor,
)
from spiffworkflow_backend.services.process_instance_service import (
    ProcessInstanceService,
)


class TestProcessInstanceProcessor(BaseTest):
    """TestProcessInstanceProcessor."""

    # it's not totally obvious we want to keep this test/file
    def test_script_engine_takes_data_and_returns_expected_results(
        self,
        app: Flask,
        with_db_and_bpmn_file_cleanup: None,
    ) -> None:
        """Test_script_engine_takes_data_and_returns_expected_results."""
        app.config["THREAD_LOCAL_DATA"].process_model_identifier = "hey"
        app.config["THREAD_LOCAL_DATA"].process_instance_id = 0
        script_engine = ProcessInstanceProcessor._script_engine

        result = script_engine._evaluate("a", {"a": 1})
        assert result == 1
        app.config["THREAD_LOCAL_DATA"].process_model_identifier = None
        app.config["THREAD_LOCAL_DATA"].process_instance_id = None

    def test_script_engine_can_use_custom_scripts(
        self,
        app: Flask,
        with_db_and_bpmn_file_cleanup: None,
    ) -> None:
        """Test_script_engine_takes_data_and_returns_expected_results."""
        app.config["THREAD_LOCAL_DATA"].process_model_identifier = "hey"
        app.config["THREAD_LOCAL_DATA"].process_instance_id = 0
        script_engine = ProcessInstanceProcessor._script_engine
        result = script_engine._evaluate("fact_service(type='norris')", {})
        assert result == "Chuck Norris doesn’t read books. He stares them down until he gets the information he wants."
        app.config["THREAD_LOCAL_DATA"].process_model_identifier = None
        app.config["THREAD_LOCAL_DATA"].process_instance_id = None

    def test_sets_permission_correctly_on_human_task(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        """Test_sets_permission_correctly_on_human_task."""
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user = self.find_or_create_user("testuser2")
        assert initiator_user.principal is not None
        assert finance_user.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/model_with_lanes",
            bpmn_file_name="lanes.bpmn",
            process_model_source_directory="model_with_lanes",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)

        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == initiator_user

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, finance_user, human_task)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id == finance_group.id
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == finance_user

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, finance_user, human_task)
        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == initiator_user

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        assert process_instance.status == ProcessInstanceStatus.complete.value

    def test_sets_permission_correctly_on_human_task_when_using_dict(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        """Test_sets_permission_correctly_on_human_task_when_using_dict."""
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user_three = self.find_or_create_user("testuser3")
        finance_user_four = self.find_or_create_user("testuser4")
        testadmin1 = self.find_or_create_user("testadmin1")
        assert initiator_user.principal is not None
        assert finance_user_three.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/model_with_lanes",
            bpmn_file_name="lanes_with_owner_dict.bpmn",
            process_model_source_directory="model_with_lanes",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)

        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == initiator_user

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, finance_user_three, human_task)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)
        assert human_task.completed_by_user_id == initiator_user.id

        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 2
        assert human_task.potential_owners == [finance_user_three, finance_user_four]

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        g.user = finance_user_three
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, finance_user_three, human_task)
        assert human_task.completed_by_user_id == finance_user_three.id
        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == finance_user_four

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, finance_user_four, human_task)
        assert human_task.completed_by_user_id == finance_user_four.id
        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        assert human_task.lane_assignment_id is None
        assert len(human_task.potential_owners) == 1
        assert human_task.potential_owners[0] == initiator_user

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)

        assert len(process_instance.active_human_tasks) == 1
        human_task = process_instance.active_human_tasks[0]
        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task.task_name, processor.bpmn_process_instance
        )
        with pytest.raises(UserDoesNotHaveAccessToTaskError):
            ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, testadmin1, human_task)

        assert process_instance.status == ProcessInstanceStatus.complete.value

    def test_can_load_up_processor_after_running_model_with_call_activities(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        """Test_does_not_recreate_human_tasks_on_multiple_saves."""
        initiator_user = self.find_or_create_user("initiator_user")

        process_model = load_test_spec(
            process_model_id="test_group/call_activity_nested",
            process_model_source_directory="call_activity_nested",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)

        # ensure this does not raise
        processor = ProcessInstanceProcessor(process_instance)

        # this task will be found within subprocesses
        spiff_task = processor.__class__.get_task_by_bpmn_identifier("do_nothing", processor.bpmn_process_instance)
        assert spiff_task is not None
        assert spiff_task.state == TaskState.COMPLETED

    def test_properly_resets_process_to_given_task(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user_three = self.find_or_create_user("testuser3")
        assert initiator_user.principal is not None
        assert finance_user_three.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/manual_task",
            process_model_source_directory="manual_task",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)
        assert len(process_instance.active_human_tasks) == 1
        initial_human_task_id = process_instance.active_human_tasks[0].id

        # save again to ensure we go attempt to process the human tasks again
        processor.save()

        assert len(process_instance.active_human_tasks) == 1
        assert initial_human_task_id == process_instance.active_human_tasks[0].id

        processor = ProcessInstanceProcessor(process_instance)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task_one.task_name, processor.bpmn_process_instance
        )
        assert spiff_manual_task is not None

        processor.suspend()
        ProcessInstanceProcessor.reset_process(process_instance, str(spiff_manual_task.parent.id))

        process_instance = ProcessInstanceModel.query.filter_by(id=process_instance.id).first()
        processor = ProcessInstanceProcessor(process_instance)
        processor.resume()
        processor.do_engine_steps(save=True)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)
        assert process_instance.status == "complete"

    def test_properly_resets_process_to_given_task_with_call_activity(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user_three = self.find_or_create_user("testuser3")
        assert initiator_user.principal is not None
        assert finance_user_three.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/manual_task_with_subprocesses",
            process_model_source_directory="manual_task_with_subprocesses",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)
        assert len(process_instance.active_human_tasks) == 1
        initial_human_task_id = process_instance.active_human_tasks[0].id
        assert len(process_instance.active_human_tasks) == 1
        assert initial_human_task_id == process_instance.active_human_tasks[0].id

        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)

        processor.suspend()
        task_model_to_reset_to = (
            TaskModel.query.join(TaskDefinitionModel)
            .filter(TaskDefinitionModel.bpmn_identifier == "top_level_subprocess_script")
            .order_by(TaskModel.id.desc())  # type: ignore
            .first()
        )
        assert task_model_to_reset_to is not None
        ProcessInstanceProcessor.reset_process(process_instance, task_model_to_reset_to.guid)

        # make sure sqlalchemy session matches current db state
        db.session.expire_all()
        process_instance = ProcessInstanceModel.query.filter_by(id=process_instance.id).first()
        processor = ProcessInstanceProcessor(process_instance)

        # make sure we reset to the task we expected
        ready_or_waiting_tasks = processor.get_all_ready_or_waiting_tasks()
        top_level_subprocess_script_spiff_task = next(
            task for task in ready_or_waiting_tasks if task.task_spec.name == "top_level_subprocess_script"
        )
        assert top_level_subprocess_script_spiff_task is not None
        processor.resume()
        processor.do_engine_steps(save=True)

        assert len(process_instance.active_human_tasks) == 1
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)

        assert process_instance.status == "complete"

    def test_properly_saves_tasks_when_running(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user_three = self.find_or_create_user("testuser3")
        assert initiator_user.principal is not None
        assert finance_user_three.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/manual_task_with_subprocesses",
            process_model_source_directory="manual_task_with_subprocesses",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)
        assert len(process_instance.active_human_tasks) == 1
        initial_human_task_id = process_instance.active_human_tasks[0].id

        # save again to ensure we go attempt to process the human tasks again
        processor.save()

        assert len(process_instance.active_human_tasks) == 1
        assert initial_human_task_id == process_instance.active_human_tasks[0].id

        processor = ProcessInstanceProcessor(process_instance)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task_one.task_name, processor.bpmn_process_instance
        )
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)

        process_instance = ProcessInstanceModel.query.filter_by(id=process_instance.id).first()
        processor = ProcessInstanceProcessor(process_instance)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)
        human_task_one = process_instance.active_human_tasks[0]
        spiff_manual_task = processor.bpmn_process_instance.get_task_from_id(UUID(human_task_one.task_id))
        ProcessInstanceService.complete_form_task(processor, spiff_manual_task, {}, initiator_user, human_task_one)

        # recreate variables to ensure all bpmn json was recreated from scratch from the db
        process_instance_relookup = ProcessInstanceModel.query.filter_by(id=process_instance.id).first()
        processor_final = ProcessInstanceProcessor(process_instance_relookup)
        assert process_instance_relookup.status == "complete"

        data_set_1 = {"set_in_top_level_script": 1}
        data_set_2 = {
            **data_set_1,
            **{"set_in_top_level_subprocess": 1, "we_move_on": False},
        }
        data_set_3 = {
            **data_set_2,
            **{
                "set_in_test_process_to_call_subprocess_subprocess_script": 1,
                "set_in_test_process_to_call_subprocess_script": 1,
            },
        }
        data_set_4 = {
            **data_set_3,
            **{
                "set_in_test_process_to_call_script": 1,
            },
        }
        data_set_5 = {**data_set_4, **{"a": 1, "we_move_on": True}}
        data_set_6 = {**data_set_5, **{"set_top_level_process_script_after_gate": 1}}
        data_set_7 = {**data_set_6, **{"validate_only": False, "set_top_level_process_script_after_gate": 1}}
        expected_task_data = {
            "top_level_script": {"data": data_set_1, "bpmn_process_identifier": "top_level_process"},
            "top_level_manual_task_one": {"data": data_set_1, "bpmn_process_identifier": "top_level_process"},
            "top_level_manual_task_two": {"data": data_set_1, "bpmn_process_identifier": "top_level_process"},
            "top_level_subprocess_script": {
                "data": data_set_2,
                "bpmn_process_identifier": "top_level_subprocess",
            },
            "top_level_subprocess": {"data": data_set_2, "bpmn_process_identifier": "top_level_process"},
            "test_process_to_call_subprocess_script": {
                "data": data_set_3,
                "bpmn_process_identifier": "test_process_to_call_subprocess",
            },
            "top_level_call_activity": {"data": data_set_4, "bpmn_process_identifier": "top_level_process"},
            "top_level_manual_task_two_second": {
                "data": data_set_4,
                "bpmn_process_identifier": "top_level_process",
            },
            "top_level_subprocess_script_second": {
                "data": data_set_5,
                "bpmn_process_identifier": "top_level_subprocess",
            },
            "top_level_subprocess_second": {"data": data_set_5, "bpmn_process_identifier": "top_level_process"},
            "test_process_to_call_subprocess_script_second": {
                "data": data_set_5,
                "bpmn_process_identifier": "test_process_to_call_subprocess",
            },
            "top_level_call_activity_second": {
                "data": data_set_5,
                "bpmn_process_identifier": "top_level_process",
            },
            "end_event_of_manual_task_model": {"data": data_set_6, "bpmn_process_identifier": "top_level_process"},
        }

        spiff_tasks_checked: list[str] = []

        # TODO: also check task data here from the spiff_task directly to ensure we hydrated spiff correctly
        def assert_spiff_task_is_in_process(spiff_task: SpiffTask) -> None:
            spiff_task_identifier = spiff_task.task_spec.name
            if spiff_task_identifier in expected_task_data:
                bpmn_process_identifier = expected_task_data[spiff_task_identifier]["bpmn_process_identifier"]
                expected_task_data_key = spiff_task_identifier
                if spiff_task_identifier in spiff_tasks_checked:
                    expected_task_data_key = f"{spiff_task.task_spec.name}_second"

                assert expected_task_data_key not in spiff_tasks_checked

                spiff_tasks_checked.append(expected_task_data_key)

                expected_python_env_data = expected_task_data[expected_task_data_key]["data"]

                base_failure_message = (
                    f"Failed on {bpmn_process_identifier} - {spiff_task_identifier} - task data key"
                    f" {expected_task_data_key}."
                )

                count_failure_message = (
                    f"{base_failure_message} There are more than 2 entries of this task in the db."
                    " There should only ever be max 2."
                )
                task_models_with_bpmn_identifier_count = (
                    TaskModel.query.join(TaskDefinitionModel)
                    .filter(TaskModel.process_instance_id == process_instance_relookup.id)
                    .filter(TaskDefinitionModel.bpmn_identifier == spiff_task.task_spec.name)
                    .count()
                )
                assert task_models_with_bpmn_identifier_count < 3, count_failure_message
                task_model = TaskModel.query.filter_by(guid=str(spiff_task.id)).first()

                assert task_model.start_in_seconds is not None
                assert task_model.end_in_seconds is not None
                assert task_model.task_definition_id is not None

                task_definition = task_model.task_definition
                assert task_definition.bpmn_identifier == spiff_task_identifier
                assert task_definition.bpmn_name == spiff_task_identifier.replace("_", " ").title()
                assert (
                    task_definition.bpmn_process_definition.bpmn_identifier == bpmn_process_identifier
                ), base_failure_message

                message = (
                    f"{base_failure_message} Expected: {sorted(expected_python_env_data)}. Received:"
                    f" {sorted(task_model.json_data())}"
                )
                # TODO: if we split out env data again we will need to use it here instead of json_data
                # assert task_model.python_env_data() == expected_python_env_data, message
                assert task_model.json_data() == expected_python_env_data, message

        all_spiff_tasks = processor_final.bpmn_process_instance.get_tasks()
        assert len(all_spiff_tasks) > 1
        for spiff_task in all_spiff_tasks:
            if spiff_task.task_spec.name == "our_boundary_event":
                assert spiff_task.state == TaskState.CANCELLED
                spiff_tasks_checked.append(spiff_task.task_spec.name)
                continue

            assert spiff_task.state == TaskState.COMPLETED
            assert_spiff_task_is_in_process(spiff_task)

            if spiff_task.task_spec.name == "top_level_call_activity":
                # the task id / guid of the call activity gets used as the guid of the bpmn process that it calls
                bpmn_process = BpmnProcessModel.query.filter_by(guid=str(spiff_task.id)).first()
                assert bpmn_process is not None
                bpmn_process_definition = bpmn_process.bpmn_process_definition
                assert bpmn_process_definition is not None
                assert bpmn_process_definition.bpmn_identifier == "test_process_to_call"
                assert bpmn_process_definition.bpmn_name == "Test Process To Call"
                spiff_tasks_checked.append(spiff_task.task_spec.name)

            # Check that the direct parent of the called activity subprocess task is the
            #   name of the process that was called from the activity.
            if spiff_task.task_spec.name == "test_process_to_call_subprocess_script":
                task_model = TaskModel.query.filter_by(guid=str(spiff_task.id)).first()
                assert task_model is not None
                bpmn_process = task_model.bpmn_process
                assert bpmn_process is not None
                bpmn_process_definition = bpmn_process.bpmn_process_definition
                assert bpmn_process_definition is not None
                assert bpmn_process_definition.bpmn_identifier == "test_process_to_call_subprocess"
                assert bpmn_process.direct_parent_process_id is not None
                direct_parent_process = BpmnProcessModel.query.filter_by(
                    id=bpmn_process.direct_parent_process_id
                ).first()
                assert direct_parent_process is not None
                assert direct_parent_process.bpmn_process_definition.bpmn_identifier == "test_process_to_call"
                spiff_tasks_checked.append(spiff_task.task_spec.name)

        expected_task_identifiers = list(expected_task_data.keys()) + [
            "our_boundary_event",
            "test_process_to_call_subprocess_script",
            "top_level_call_activity",
        ]
        for task_bpmn_identifier in expected_task_identifiers:
            message = (
                f"Expected to have seen a task with a bpmn_identifier of {task_bpmn_identifier} but did not. "
                f"Only saw {sorted(spiff_tasks_checked)}"
            )
            assert task_bpmn_identifier in spiff_tasks_checked, message

        task_models_that_are_predicted_count = (
            TaskModel.query.filter(TaskModel.process_instance_id == process_instance_relookup.id)
            .filter(TaskModel.state.in_(["LIKELY", "MAYBE"]))  # type: ignore
            .count()
        )
        assert task_models_that_are_predicted_count == 0

        assert processor.get_data() == data_set_7

    def test_does_not_recreate_human_tasks_on_multiple_saves(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        """Test_does_not_recreate_human_tasks_on_multiple_saves."""
        self.create_process_group_with_api(client, with_super_admin_user, "test_group", "test_group")
        initiator_user = self.find_or_create_user("initiator_user")
        finance_user_three = self.find_or_create_user("testuser3")
        assert initiator_user.principal is not None
        assert finance_user_three.principal is not None
        AuthorizationService.import_permissions_from_yaml_file()

        finance_group = GroupModel.query.filter_by(identifier="Finance Team").first()
        assert finance_group is not None

        process_model = load_test_spec(
            process_model_id="test_group/model_with_lanes",
            bpmn_file_name="lanes_with_owner_dict.bpmn",
            process_model_source_directory="model_with_lanes",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)
        assert len(process_instance.active_human_tasks) == 1
        initial_human_task_id = process_instance.active_human_tasks[0].id

        # save again to ensure we go attempt to process the human tasks again
        processor.save()

        assert len(process_instance.active_human_tasks) == 1
        assert initial_human_task_id == process_instance.active_human_tasks[0].id

    def test_it_can_loopback_to_previous_bpmn_task_with_gateway(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
    ) -> None:
        initiator_user = self.find_or_create_user("initiator_user")
        process_model = load_test_spec(
            process_model_id="test_group/loopback_to_manual_task",
            bpmn_file_name="loopback.bpmn",
            process_model_source_directory="loopback_to_manual_task",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)

        assert len(process_instance.active_human_tasks) == 1
        assert len(process_instance.human_tasks) == 1
        human_task_one = process_instance.active_human_tasks[0]

        spiff_task = processor.__class__.get_task_by_bpmn_identifier(
            human_task_one.task_name, processor.bpmn_process_instance
        )
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task_one)

        assert len(process_instance.active_human_tasks) == 1
        assert len(process_instance.human_tasks) == 2
        human_task_two = process_instance.active_human_tasks[0]

        assert human_task_two.task_id != human_task_one.task_id

    def test_it_can_loopback_to_previous_bpmn_subprocess_with_gateway(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
    ) -> None:
        initiator_user = self.find_or_create_user("initiator_user")
        process_model = load_test_spec(
            process_model_id="test_group/loopback_to_subprocess",
            process_model_source_directory="loopback_to_subprocess",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=initiator_user
        )
        processor = ProcessInstanceProcessor(process_instance)
        processor.do_engine_steps(save=True)

        assert len(process_instance.active_human_tasks) == 1
        assert len(process_instance.human_tasks) == 1
        human_task_one = process_instance.active_human_tasks[0]

        spiff_task = processor.get_task_by_guid(human_task_one.task_id)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task_one)

        processor = ProcessInstanceProcessor(process_instance)
        assert len(process_instance.active_human_tasks) == 1
        assert len(process_instance.human_tasks) == 2
        human_task_two = process_instance.active_human_tasks[0]
        spiff_task = processor.get_task_by_guid(human_task_two.task_id)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task_two)

        # ensure this does not raise a KeyError
        processor = ProcessInstanceProcessor(process_instance)
        assert len(process_instance.active_human_tasks) == 1
        assert len(process_instance.human_tasks) == 3
        human_task_three = process_instance.active_human_tasks[0]
        spiff_task = processor.get_task_by_guid(human_task_three.task_id)
        ProcessInstanceService.complete_form_task(processor, spiff_task, {}, initiator_user, human_task_three)

    def test_task_data_is_set_even_if_process_instance_errors(
        self,
        app: Flask,
        client: FlaskClient,
        with_db_and_bpmn_file_cleanup: None,
        with_super_admin_user: UserModel,
    ) -> None:
        """Test_task_data_is_set_even_if_process_instance_errors."""
        process_model = load_test_spec(
            process_model_id="group/error_with_task_data",
            bpmn_file_name="script_error_with_task_data.bpmn",
            process_model_source_directory="error",
        )
        process_instance = self.create_process_instance_from_process_model(
            process_model=process_model, user=with_super_admin_user
        )

        processor = ProcessInstanceProcessor(process_instance)
        with pytest.raises(ApiError):
            processor.do_engine_steps(save=True)

        process_instance_final = ProcessInstanceModel.query.filter_by(id=process_instance.id).first()
        processor_final = ProcessInstanceProcessor(process_instance_final)

        spiff_task = processor_final.get_task_by_bpmn_identifier(
            "script_task_two", processor_final.bpmn_process_instance
        )
        assert spiff_task is not None
        assert spiff_task.state == TaskState.WAITING
        assert spiff_task.data == {"my_var": "THE VAR"}
