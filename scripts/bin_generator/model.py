from dataclasses import dataclass 
from collections.abc import Mapping 
from enum import StrEnum
from pathlib import Path

class EnvironmentKind(StrEnum):
    CONTAINER = "container"

class PackageManager(StrEnum):
    APT = "apt"

class ToolCapability(StrEnum):
    COMPILE_C = "compile_c"
    LINK = "link"
    CONVERT_OBJECT = "convert_object"
    INSPECT_ELF = "inspect_elf"

class ArtifactFormat(StrEnum):
    ELF = "elf"
    BINARY = "bin"
    INTEL_HEX = "ihex"
    S_RECORD = "srec"

class ProductKind(StrEnum):
    EXECUTABLE = "executable"

class ToolInterface(StrEnum):
    GNU_CC = "gnu-cc"
    GNU_OBJCOPY = "gnu-objcopy"
    GNU_READELF = "gnu-readelf"

class SourceLanguage(StrEnum):
    C = "c"
    CXX = "cxx"
    ASSEMBLY = "assembly"
    RUST = "rust"

@dataclass(frozen=True)
class Source:
    path: Path
    language: SourceLanguage


@dataclass(frozen=True)
class Tool:
    interface: ToolInterface 
    command: tuple[str, ...]
    fixed_args: tuple[str, ...]

@dataclass(frozen=True)
class Environment:
    name: str 
    kind: EnvironmentKind
    manager: PackageManager
    packages: tuple[str, ...]

@dataclass(frozen=True)
class Toolchain:
    name: str
    environment: Environment 
    target_triple: str 
    tools: Mapping[ToolCapability, Tool]

@dataclass(frozen=True)
class Target:
    arch: str
    name: str 
    toolchain: Toolchain
    pipeline: str
    product: ProductKind 
    sources: tuple[Source, ...]
    output: Path
    formats: tuple[ArtifactFormat, ...]
    tool_args: Mapping[ToolCapability, tuple[str, ...]]

    @property 
    def id(self) -> str:
        return f"{self.arch}.{self.name}"


@dataclass(frozen=True)
class TargetsConfig:
    schema_version: int
    root: Path
    targets: tuple[Target, ...]

@dataclass(frozen=True)
class ToolchainsConfig:
    schema_version: int 
    environments: Mapping[str, Environment]
    toolchains: Mapping[str, Toolchain]

@dataclass(frozen=True)
class GeneratorConfig:
    targets: TargetsConfig 
    toolchains: ToolchainsConfig


