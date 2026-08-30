from pathlib import Path
from dataclasses import dataclass
from typing import Mapping, Protocol

from .model import (
        ArtifactFormat,
        Source,
        SourceLanguage, 
        Target, 
        Tool,
        ToolCapability,
        ToolInterface,
)

ARTIFACT_EXTENSIONS = {
       ArtifactFormat.ELF: ".elf",
       ArtifactFormat.BINARY: ".bin",
       ArtifactFormat.INTEL_HEX: ".hex",
       ArtifactFormat.S_RECORD: ".srec",
}

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

def require_tool(context: PlanningContext, capability: ToolCapability) -> Tool:
    tools: Mapping[ToolCapability, Tool] = context.target.toolchain.tools 
    tool = tools.get(capability)
    if tool is None:
        raise PlanningError(
                f"{context.target.id}: toolchain {context.target.toolchain.name!r} does not provide capability {capability.value!r}")
    return tool 

def tool_args(context: PlanningContext, capability: ToolCapability) -> tuple[str, ...]: 
    return context.target.tool_args.get(capability, ())

def object_path(context: PlanningContext, source: Source) -> Path:
    return context.target.output.parent / "obj" / f"{source.path.stem}.o"

def artifact_path(context: PlanningContext, format: ArtifactFormat) -> Path: 
    return context.target.output.with_suffix(ARTIFACT_EXTENSIONS[format])

class GnuCcAdapter:
    def compile_c(
            self,
            tool: Tool,
            source: Path,
            output: Path,
            args: tuple[str, ...]
            ) -> Command:
        if tool.interface is not ToolInterface.GNU_CC:
            raise PlanningError(
                    f"tool interface {tool.interface!r} is incompatible with gnu-cc adapter"
                    )
        return Command((
            *tool.command,
            *tool.fixed_args,
            *args,
            "-c",
            str(source),
            "-o",
            str(output),))
         
    def link(
            self,
            tool: Tool,
            objects: tuple[Path, ...],
            output: Path,
            args: tuple[str, ...],
            ) -> Command:
        if tool.interface is not ToolInterface.GNU_CC:
            raise PlanningError(
                    f"tool interface {tool.interface!r} is incompatible with gnu-cc adapter"
                    )
        return Command((
            *tool.command,
            *tool.fixed_args,
            *args,
            *(str(path) for path in objects),
            "-o",
            str(output),))

class GnuObjcopyAdapter:
    def convert_object(
            self,
            tool: Tool,
            source: Path,
            output: Path,
            output_format: str, 
            args: tuple[str, ...]
            ) -> Command:
        if tool.interface is not ToolInterface.GNU_OBJCOPY:
            raise PlanningError(
                    f"tool interface {tool.interface!r} is incompatible with gnu-objcopy adapter"
                    )
        return Command((
            *tool.command,
            *tool.fixed_args,
            *args,
            "-O",
            output_format,
            str(source),
            str(output),))

ADAPTERS = {
    ToolInterface.GNU_CC: GnuCcAdapter(),
    ToolInterface.GNU_OBJCOPY: GnuObjcopyAdapter(),
}

class CompileStage:
    def plan_sources(self, context: PlanningContext) -> StageResult:
        tool = require_tool(context, ToolCapability.COMPILE_C)
        args = tool_args(context, ToolCapability.COMPILE_C)
        
        files: list[PlannedFile] = []
        commands: list[Command] = []

        for source in context.target.sources:
                if source.language is not SourceLanguage.C:
                    raise PlanningError(
                            f"{context.target.id}: unsupported source language {source.language.value!r} for {source.path}")
                output = object_path(context, source)
                adapter = ADAPTERS.get(tool.interface)
                if not isinstance(adapter, GnuCcAdapter):
                    raise PlanningError("{context.target.id}: capability {ToolCapability.COMPILE_C.value!r} requires gnu-cc compatible adapter, got {tool.interface.value!r}")
                command = adapter.compile_c(
                        tool,
                        source.path,
                        output,
                        args,)

                files.append(PlannedFile(output))
                commands.append(command)

        return StageResult(tuple(files), tuple(commands))

