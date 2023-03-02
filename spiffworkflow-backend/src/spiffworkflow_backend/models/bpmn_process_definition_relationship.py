from __future__ import annotations
from sqlalchemy.orm import deferred
from sqlalchemy import ForeignKey
from spiffworkflow_backend.models.bpmn_process_definition import BpmnProcessDefinitionModel

from spiffworkflow_backend.models.db import db
from spiffworkflow_backend.models.db import SpiffworkflowBaseDBModel


class BpmnProcessDefinitionRelationshipModel(SpiffworkflowBaseDBModel):
    __tablename__ = "bpmn_process_definition_relationship"
    id: int = db.Column(db.Integer, primary_key=True)
    bpmn_process_definition_parent_id: int = db.Column(ForeignKey(BpmnProcessDefinitionModel.id), nullable=False)  # type: ignore
    bpmn_process_definition_child_id: int = db.Column(ForeignKey(BpmnProcessDefinitionModel.id), nullable=False)  # type: ignore
