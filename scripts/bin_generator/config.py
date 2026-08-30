from pathlib import Path

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
    Target,
    TargetsConfig,
    Tool,
    ToolCapability,
    Toolchain,
    ToolchainConvention,
    ToolchainsConfig,
)

TOOLCHAINS_SCHEMA_VERSION = 1
TARGETS_SCHEMA_VERSION = 1

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
        convention_raw = reader.required_str("convention")
        tools_raw = reader.required_table("tools")

        reader.finish()

        try:
            environment = envs[environment_raw]
        except KeyError:
            errors.append(
                    f"{path}.environment: unknown environment")
            return None 

        try:
            convention = ToolchainConvention(convention_raw)
        except ValueError:
            errors.append(f"{path}.convention: unknown convention: {convention_raw!r}")
            return None 


        tools: dict[ToolCapability, Tool] = {} 
        for capability_name, raw_tool in tools_raw.items():
            capability_path = f"{path}.tools.{capability_name}"
            try: 
                capability = ToolCapability(capability_name)
            except ValueError:
                errors.append(
                        f"{capability_path}: unknown tool capability")
                continue 
            tools[capability] = self.decode_tool(
                    raw=raw_tool,
                    path=capability_path,
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
                    f"{path}.package_manager: unsupported package manager {manager_raw!r}")
        
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
        product_raw = reader.required_str("product")
        sources_raw = reader.required_strings("sources")
        output = reader.required_str("output")
        formats_raw = reader.required_strings("formats")
        tool_args_raw = reader.optional_table("tool_args")
        
        reader.finish()
        
        try:
            toolchain: Toolchain = self.toolchains[toolchain_raw]
        except KeyError:
            errors.append(
                    f"{path}.toolchain: unknown toolchain specified: {toolchain_raw!r}")
            return None 
    
        try: 
            product = ProductKind(product_raw)
        except ValueError:
            errors.append(f"{path}.product: unknown product kind: {product_raw!r}")
        
        sources = tuple(Path(source) for source in sources_raw)
        
        formats: list[ArtifactFormat] = [] 
        for fmt in formats_raw:
            try: 
                format = ArtifactFormat(fmt)
            except ValueError:
                errors.append(f"{path}.formats: unknown format: {fmt!r}")
                continue 
            formats.append(format)

        tool_args: dict[ToolCapability, tuple[str, ...]] = {}
        for capability_raw, flags_raw in tool_args_raw.items():
            capability_path = f"{path}.tool_args.{capability_raw}"
            try:
                capability = ToolCapability(capability_raw)
            except ValueError:
                errors.append(
                        f"{capability_path}: unknown tool capability")
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

        return Target(
                arch=arch,
                name=name, 
                output=Path(output),
                toolchain=toolchain,
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


