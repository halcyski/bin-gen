from pathlib import Path

from .table_reader import ConfigError, TableReader
from .model import (
    ArtifactFormat,
    Environment,
    EnvironmentKind,
    PackageManager,
    Target,
    Tool,
    ToolCapability,
    Toolchain,
    ToolchainsConfig,
)

TOOLCHAINS_SCHEMA_VERSION = 1
TARGETS_SCHEMA_VERSION = 1

class ToolchainSchemaDecoder:

    def decode_toolchains(
            self,
            raw: object,
            path: Path,) -> ToolchainsConfig | None:
        errors: list[str] = [] 
        root_path = str(path)
        reader = TableReader(raw, root_path, errors)
        schema_version = reader.required_int("schema_version")
        environments_raw = reader.requried_table("environments")
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
        convention = reader.required_str("convention")
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
            try: 
                capability = ToolCapability(capability_name)
            except ValueError:
                errors.append(
                        f"{path}.{capability_name}: unknown tool capability")
                continue 
            tools[capability] = self.decode_tool(
                    raw=raw_tool,
                    path=f"{path}.{capability_name}",
                    errors=errors,)

        if len(errors) != initial_error_count:
            return None 

        return Toolchain(
                name=name, 
                environment=environment,
                target_triple=target_triple,
                convention=convention,
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

        kind_raw = reader.required_str("kind")
        manager_raw = reader.required_str("package_manager")
        packages = reader.optional_strings("packages")
        reader.finish()

        kind: EnvironmentKind | None = None
        manager: PackageManager | None = None 
        
        try:
            kind = EnvironmentKind(kind_raw)
        except ValueError:
            errors.append(
                    f"{path}.kind: unsupported environment kind: {kind_raw!r}")

        try:
            manager = PackageManager(manager_raw)
        except ValueError: 
            errors.append(
                    f"{path}.manager: unsupported package manager {manager_raw!r}")
        
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
            errors: list[str]) -> Tool:
        reader = TableReader(raw, path, errors)
        command = reader.required_strings("command", min_items=1,)
        fixed_args = reader.optional_strings("fixed_args")
        reader.finish()
        return Tool(
                command=command,
                fixed_args=fixed_args,)

class TargetSchemaDecoder:
    def __init__(self, toolchains: dict[str, Toolchain]):
        self.toolchains = toolchains 
    
    def decode_target(
            self,
            path: str,
            raw: object,
            errors: list[str]) -> Target:
        reader = TableReader(raw, path, errors)
        
        toolchain = self.decode_toolchain(raw, path, errors)

        sources_raw = reader.required_strings("sources")
        out_raw = reader.required_str("out")
        formats_raw = reader.required_strings("formats")

        tool_args = self.decode_tool_args(raw, path, errors)
        reader.finish()
        

        
