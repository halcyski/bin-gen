from pathlib import Path
from enum import StrEnum 
from typing import TypeVar 

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


EnumT = TypeVar("EnumT", bound=StrEnum)

TOOLCHAINS_SCHEMA_VERSION = 1
TARGETS_SCHEMA_VERSION = 1

# schema specific decodes for enums and references 

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
            envs: dict[str, Environment],
            errors: list[str],
            ) -> Toolchain | None: 
        initial_error_count = len(errors)
        reader = TableReader(raw, path, errors)

        environment_raw = reader.required_str("environment")
        target_triple = reader.required_str("target_triple")
        tools_raw = reader.required_table("tools")

        reader.finish()

        try:
            environment = envs[environment_raw]
        except KeyError:
            errors.append(
                    f"{path}.environment: unknown environment")
            return None 


        tools: dict[ToolCapability, Tool] = {} 
        for capability_name, raw_tool in tools_raw.items():
            capability_path = f"{path}.tools.{capability_name}"
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
        
        if len(errors) != initial_error_count:
            return None 

        return Toolchain(
                name=name, 
                environment=environment,
                target_triple=target_triple,
                tools=tools,)


    def decode_environment(
            self,
            name: str,
            raw: object,
            path: str,
            errors: list[str],
            ) -> Environment | None:
        initial_error_count = len(errors)
        reader = TableReader(raw, path, errors)

        packages = reader.optional_strings("packages")
        kind = decode_required_enum(reader, "kind", EnvironmentKind)
        manager = decode_required_enum(reader, "package_manager", PackageManager)

        reader.finish()
         
        if len(errors) != initial_error_count:
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
        initial_error_count = len(errors)
        reader = TableReader(raw, path, errors)
        command = reader.required_strings("command", min_items=1,)
        interface = decode_required_enum(reader, "interface", ToolInterface)
        fixed_args = reader.optional_strings("fixed_args")

        reader.finish()
        if len(errors) != initial_error_count:
            return None
        assert interface is not None

        return Tool(
                interface=interface,
                command=command,
                fixed_args=fixed_args,)

class TargetSchemaDecoder:
    def __init__(self, toolchains: dict[str, Toolchain]):
        self.toolchains = toolchains 

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
        initial_error_count = len(errors)
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
        
        try:
            toolchain: Toolchain = self.toolchains[toolchain_raw]
        except KeyError:
            errors.append(
                    f"{path}.toolchain: unknown toolchain specified: {toolchain_raw!r}")
            return None 
    

        sources: list[Source] = []
        
        for index, raw_source in enumerate(sources_raw):
            source_path = f"{path}.sources[{index}]"
            source_error_count = len(errors)

            source_reader = TableReader(
                    raw=raw_source,
                    path=source_path,
                    errors=errors,
                    )
            path_raw = source_reader.required_str("path")
            language = decode_required_enum(
                    source_reader,
                    "language",
                    SourceLanguage,)
            source_reader.finish()

            if len(errors) != source_error_count or language is None:
                continue 
             
            sources.append(
                    Source(
                        path=Path(path_raw),
                        language=language,
                        ))

        tool_args: dict[ToolCapability, tuple[str, ...]] = {}
        for capability_name, flags_raw in tool_args_raw.items():
            capability_path = f"{path}.tool_args.{capability_name}"
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

            if capability not in toolchain.tools:
                errors.append(
                        f"{capability_path}: capability is not provided by toolchain {toolchain.name!r}")
                continue 

            tool_args[capability] = flags

        if initial_error_count != len(errors):
            return None

        assert product is not None

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
            dict(toolchains.toolchains),).decode_targets(targets_raw, str(targets_path),)

    return GeneratorConfig(
            targets=targets,
            toolchains=toolchains,
    )


