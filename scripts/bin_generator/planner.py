from pathlib import Path
from dataclasses import dataclass
from typing import Protocol

from .model import ArtifactFormat, Target

class PlanningError(Exception):
    ...


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]

@dataclass(frozen=True)
class PlannedFile:
    path: Path
    format: ArtifactFormat | None = None

@dataclass(frozen=True)
class StageResult:
    files: tuple[PlannedFile, ...]
    commands: tuple[Command, ...]

@dataclass(frozen=True)
class PlanningContext:
    root: Path
    target: Target 

@dataclass(frozen=True)
class BuildPlan:
    target: Target
    files: tuple[PlannedFile, ...]
    commands: tuple[Command, ...]

class SourceStage(Protocol):
    def plan_sources(self, context: PlanningContext) -> StageResult: 
        ...

class ProductStage(Protocol):
    def plan_product(
            self,
            context: PlanningContext,
            sources: StageResult,
            ) -> StageResult:
        ...

class ArtifactStage(Protocol):
    def plan_artifacts(
            self,
            context: PlanningContext,
            product: StageResult,
            ) -> StageResult:
        ...

