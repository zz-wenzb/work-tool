# models/yunxiao_models.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class Label(BaseModel):
    displayName: Optional[str] = None
    displayValue: Optional[str] = None
    extraMap: Optional[dict] = None
    name: Optional[str] = None
    namespace: Optional[str] = None
    value: Optional[str] = None

class PipelineConfigVo(BaseModel):
    settings: Optional[str] = None
    creator: Optional[str] = None
    gmtModified: Optional[int] = None
    webhook: Optional[str] = None
    sources: Optional[str] = None
    modifier: Optional[str] = None
    changeLog: Optional[str] = None
    gmtCreate: Optional[int] = None
    version: Optional[int] = None
    pipelineId: Optional[int] = None
    isDeleted: Optional[str] = None
    triggerVoList: Optional[List[Dict[str, Any]]] = None
    clone: Optional[bool] = None
    id: Optional[int] = None
    doValidate: Optional[bool] = None
    flow: Optional[str] = None

class Pipeline(BaseModel):
    pipelineConfigVo: Optional[PipelineConfigVo] = None
    creator: Optional[str] = None
    gmtModified: Optional[int] = None
    pipelineConfigId: Optional[int] = None
    modifier: Optional[str] = None
    pageSize: Optional[int] = None
    relType: Optional[str] = None
    gmtCreate: Optional[int] = None
    priority: Optional[int] = None
    pipelineId: Optional[int] = None
    extendInfoVo: Optional[Dict[str, Any]] = None
    pipelineName: Optional[str] = None
    pageOrder: Optional[str] = None
    isDeleted: Optional[str] = None
    regionId: Optional[int] = None
    pageStart: Optional[int] = None
    refObjectId: Optional[str] = None
    id: Optional[int] = None
    pipelineGmtRefresh: Optional[int] = None
    refObjectType: Optional[str] = None

class PipelineWrapper(BaseModel):
    pipeline: Optional[Pipeline] = None

class ReleaseStagePipeline(BaseModel):
    pipeline: Optional[PipelineWrapper] = None
    plugins: Optional[Any] = None
    engineType: Optional[str] = None
    engineSn: Optional[str] = None
    pipelineYaml: Optional[str] = None

class VariableGroup(BaseModel):
    name: Optional[str] = None
    displayName: Optional[str] = None
    type: Optional[str] = None
    sn: Optional[str] = None

class ReleaseStage(BaseModel):
    appName: Optional[str] = None
    name: Optional[str] = None
    sn: Optional[str] = None
    releaseWorkflowSn: Optional[str] = None
    order: Optional[str] = None
    labels: Optional[List[Label]] = None
    pipeline: Optional[ReleaseStagePipeline] = None
    variableGroups: Optional[List[VariableGroup]] = None

class ReleaseWorkflow(BaseModel):
    appName: Optional[str] = None
    sn: Optional[str] = None
    name: Optional[str] = None
    order: Optional[str] = None
    type: Optional[str] = None
    releaseStages: Optional[List[ReleaseStage]] = None
    note: Optional[str] = None


class AppInfo(BaseModel):
    appTemplateDisplayName: Optional[str] = None
    appTemplateName: Optional[str] = None
    creatorId: Optional[str] = None
    description: Optional[str] = None
    gmtCreate: Optional[str] = None
    name: Optional[str] = None

class AppListResponse(BaseModel):
    data: Optional[List[AppInfo]] = None
    nextToken: Optional[str] = None
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None
    requestId: Optional[str] = None