from pathlib import Path
from enum import StrEnum 
from typing import TypeVar 
from collections.abc import Mapping
from dataclasses import dataclass
from .table_reader import (
        ConfigError, 
        TableReader, 
        decode_string_list,
        load_toml_file,
)

from .model import (
    ArtifactFormat,
    Environment,
    EnvironmentKind,
    GeneratorConfig,
    PackageManager,
    ProductKind,
    Source,
    SourceLanguage,
    Target,
    TargetsConfig,
    Tool,
    ToolCapability,
    ToolInterface,
    Toolchain,
    ToolchainsConfig,
)

@dataclass(frozen=True)
class ErrorCheckpoint:
    errors: list[str]
    initial_count: int

    @classmethod 
    def start(
            cls,
            errors: list[str],
            ) -> "ErrorCheckpoint":
        return cls(errors, len(errors))

    @property
    def failed(self) -> bool:
        return len(self.errors) != self.initial_count

EnumT = TypeVar("EnumT", bound=StrEnum)
ReferenceT = TypeVar("ReferenceT")

TOOLCHAINS_SCHEMA_VERSION = 1
TARGETS_SCHEMA_VERSION = 1

# schema specific decodes for enums and references 

def resolve_reference(
        values: Mapping[str, ReferenceT],
        name: str,
        path: str,
        kind: str,
        errors: list[str],) -> ReferenceT | None:
    if not name:
        return None
    value = values.get(name)

    if value is None:
        errors.append(
                f"{path}: unknown {kind} {name!r}"
                )
    return value 


def decode_enum_value(
        enum_type: type[EnumT],
        raw: str,
        path: str,
        errors: list[str],) -> EnumT | None:
    if not raw:
        return None

    try:
        return enum_type(raw)
    except ValueError:
        supported = ", ".join(
                repr(member.value)
                for member in enum_type
                )
        errors.append(
                f"{path}: unsupported value {raw!r}; expected one of {supported}")
        return None

def decode_required_enum(
        reader: TableReader,
        key: str,
        enum_type: type[EnumT],
        ) -> EnumT | None:
    raw = reader.required_str(key)

    return decode_enum_value(
            enum_type,
            raw,
            f"{reader.path}.{key}",
            reader.errors,)

def decode_enum_list(
        enum_type: type[EnumT],
        raw_values: tuple[str, ...],
        path: str,
        errors: list[str],
        ) -> tuple[EnumT, ...]:
    result: list[EnumT] = []

    for index, raw in enumerate(raw_values):
        value = decode_enum_value(
                enum_type,
                raw,
                f"{path}[{index}]",
                errors,)
        if value is not None:
            result.append(value)
    return tuple(result)


class ToolchainSchemaDecoder:

    def decode_toolchains(
            self,
            raw: object,
            path: Path,) -> ToolchainsConfig:
        errors: list[str] = [] 
        root_path = str(path)
        reader = TableReader(raw, root_path, errors)
        schema_version = reader.required_int("schema_version")
        environments_raw = reader.required_table("environments")
        toolchains_raw = reader.required_table("toolchains")

        reader.finish()

        if schema_version != TOOLCHAINS_SCHEMA_VERSION:
            errors.append(f"{path}.schema_version: version mismatch, expected: {TOOLCHAINS_SCHEMA_VERSION}, got {schema_version}")
            raise ConfigError(errors) 

        environments: dict[str, Environment] = {}

        for name, raw_environment in environments_raw.items():
            environment: Environment | None = self.decode_environment(
                    name=name,
                    raw=raw_environment,
                    path=f"{root_path}.environments.{name}",
                    errors=errors,)
            if environment is None: 
                continue 
            environments[name] = environment

        toolchains: dict[str, Toolchain] = {}
        for name, raw_toolchain in toolchains_raw.items():
            toolchain: Toolchain | None = self.decode_toolchain(
                    name=name,
                    raw=raw_toolchain,
                    path=f"{root_path}.toolchains.{name}",
                    envs=environments,
                    errors=errors,
                    )
            if toolchain is None:
                continue 
            toolchains[name] = toolchain

        if errors:
            raise ConfigError(errors)

        return ToolchainsConfig(
                schema_version=schema_version,
                environments=environments,
                toolchains=toolchains,)

    def decode_toolchain(
            self, 
            name: str,
            raw: object,
            path: str,
            envs: Mapping[str, Environment],
            errors: list[str],
            ) -> Toolchain | None: 
        checkpoint = ErrorCheckpoint.start(errors)
        reader = TableReader(raw, path, errors)

        environment_raw = reader.required_str("environment")
        target_triple = reader.required_str("target_triple")
        tools_raw = reader.required_table("tools")

        reader.finish()
        
        environment = resolve_reference(
                envs, 
                environment_raw,
                f"{path}.environment",
                "environment",
                errors,)

        tools = self.decode_tools(
                tools_raw,
                f"{path}.tools",
                errors,)
               
        if checkpoint.failed:
            return None 
        assert environment is not None

        return Toolchain(
                name=name, 
                environment=environment,
                target_triple=target_triple,
                tools=tools,)

    def decode_tools(
            self,
            raw: Mapping[str, object],
            path: str,
            errors: list[str],
            ) -> dict[ToolCapability, Tool]:
        tools: dict[ToolCapability, Tool] = {}

        for capability_name, raw_tool in raw.items():
            capability_path = f"{path}.{capability_name}"
            capability = decode_enum_value(
                    ToolCapability,
                    capability_name,
                    capability_path,
                    errors,)
            if capability is None:
                continue 
            tool = self.decode_tool(
                    raw=raw_tool,
                    path=capability_path,
                    errors=errors,)
            if tool is not None: 
                tools[capability] = tool 
        return tools

    def decode_environment(
            self,
            name: str,
            raw: object,
            path: str,
            errors: list[str],
            ) -> Environment | None:
        checkpoint = ErrorCheckpoint.start(errors)
        reader = TableReader(raw, path, errors)

        packages = reader.optional_strings("packages")
        kind = decode_required_enum(
                reader, 
                "kind", 
                EnvironmentKind,)
        manager = decode_required_enum(
                reader, 
                "package_manager", 
                PackageManager,)

        reader.finish()
         
        if checkpoint.failed:
            return None

        assert kind is not None
        assert manager is not None 

        return Environment(
                name=name,
                kind=kind,
                manager=manager,
                packages=packages)

    def decode_tool(
            self,
            raw: object, 
            path: str,
            errors: list[str]) -> Tool | None:
        checkpoint = ErrorCheckpoint.start(errors)
        reader = TableReader(raw, path, errors)
        command = reader.required_strings(
                "command", 
                min_items=1,)
        interface = decode_required_enum(
                reader, 
                "interface", 
                ToolInterface,)
        fixed_args = reader.optional_strings("fixed_args")

        reader.finish()
        if checkpoint.failed:
            return None
        assert interface is not None

        return Tool(
                interface=interface,
                command=command,
                fixed_args=fixed_args,)

class TargetSchemaDecoder:
    def __init__(self, toolchains: Mapping[str, Toolchain]):
        self.toolchains = toolchains

    def decode_source(
            self,
            raw: object,
            path: str,
            errors: list[str],
            ) -> Source | None:
        checkpoint = ErrorCheckpoint.start(errors)
        reader = TableReader(raw, path, errors)

        source_path = reader.required_str("path")
        language = decode_required_enum(
                reader,
                "language",
                SourceLanguage,)
        reader.finish()

        if checkpoint.failed:
            return None

        assert language is not None 

        return Source(
                path=Path(source_path),
                language=language,)

    def decode_targets(
            self, 
            raw: object, 
            path: str,
            ) -> TargetsConfig: 
        errors: list[str] = [] 
        root_path = str(path)
        reader = TableReader(raw, root_path, errors)
        schema_version = reader.required_int("schema_version")
        targets_raw = reader.required_table("target")

        reader.finish()
        
        if schema_version != TARGETS_SCHEMA_VERSION:
            errors.append(f"{path}.schema_version: version mismatch, expected: {TARGETS_SCHEMA_VERSION}, got {schema_version}")
            raise ConfigError(errors) 
        
        targets: list[Target] = []
        for arch, arch_targets in targets_raw.items():
            arch_path = f"{root_path}.target.{arch}"

            if not isinstance(arch_targets, dict):
                errors.append(f"{arch_path}: expected table")
                continue 
            
            for target_name, raw_target in arch_targets.items():
                target: Target | None = self.decode_target(
                        arch=arch,
                        name=target_name,
                        path=f"{arch_path}.{target_name}",
                        raw=raw_target,
                        errors=errors,)
                if target is None:
                    continue 
                targets.append(target)

        if errors:
            raise ConfigError(errors)
        
        return TargetsConfig(
                schema_version=schema_version,
                root=Path(root_path).parent,
                targets=tuple(targets),
                )

    def decode_target(
            self,
            arch: str,
            name: str,
            path: str,
            raw: object,
            errors: list[str]) -> Target | None:
        checkpoint = ErrorCheckpoint.start(errors)
        reader = TableReader(raw, path, errors)
        
        toolchain_raw = reader.required_str("toolchain")
        product = decode_required_enum(
                reader,
                "product", 
                ProductKind,)
        pipeline = reader.required_str("pipeline")
        sources_raw = reader.required_table_list("sources")
        output = reader.required_str("output")
        formats = decode_enum_list(
                ArtifactFormat,
                reader.required_strings("formats"),
                f"{path}.formats",
                errors,)
        tool_args_raw = reader.optional_table("tool_args")
         
        reader.finish()
        toolchain = resolve_reference(
                self.toolchains,
                toolchain_raw,
                f"{path}.toolchain",
                "toolchain",
                errors,) 
    
        sources: list[Source] = []
        
        for index, raw_source in enumerate(sources_raw):
            source_path = f"{path}.sources[{index}]"
            
            source = self.decode_source(
                    raw_source,
                    path=source_path,
                    errors=errors,)

            if source is None:
                continue 

            sources.append(source)

        tool_args = self.decode_tool_args(
                raw=tool_args_raw,
                path=f"{path}.tool_args",
                toolchain=toolchain, 
                errors=errors,) 

        if checkpoint.failed:
            return None

        assert product is not None
        assert toolchain is not None

        return Target(
                arch=arch,
                name=name, 
                output=Path(output),
                toolchain=toolchain,
                pipeline=pipeline,
                product=product,
                sources=tuple(sources),
                formats=tuple(formats),
                tool_args=tool_args,)

    def decode_tool_args(
            self,
            raw: Mapping[str, object],
            path: str,
            toolchain: Toolchain | None,
            errors: list[str],
            ) -> dict[ToolCapability, tuple[str, ...]]:

        tool_args: dict[ToolCapability, tuple[str, ...]] = {}
        for capability_name, flags_raw in raw.items():
            capability_path = f"{path}.{capability_name}"
            capability = decode_enum_value(
                    ToolCapability, 
                    capability_name, 
                    capability_path, 
                    errors,)

            if capability is None:
                continue

            flags = decode_string_list(
                    flags_raw,
                    capability_path,
                    errors,)
            
            if toolchain is None:
                continue 

            if capability not in toolchain.tools:
                errors.append(
                        f"{capability_path}: capability is not provided by toolchain {toolchain.name!r}")
                continue 

            tool_args[capability] = flags
        return tool_args

def load_generator_config(
        targets_path: Path,
        toolchains_path: Path,
        ) -> GeneratorConfig:
    toolchains_raw = load_toml_file(str(toolchains_path))
    toolchains = ToolchainSchemaDecoder().decode_toolchains(
            toolchains_raw,
            toolchains_path,)
    targets_raw = load_toml_file(str(targets_path))
    targets = TargetSchemaDecoder(
            toolchains.toolchains
            ).decode_targets(targets_raw, str(targets_path),)

    return GeneratorConfig(
            targets=targets,
            toolchains=toolchains,
    )


