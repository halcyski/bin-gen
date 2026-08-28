#!/usr/bin/env python3
import sys
import tomllib
import argparse 
from dataclasses import dataclass 
from pathlib import Path
from typing import Literal
import shlex 

SUPPORTED_FORMATS = {
        "elf",
        "bin",
        "ihex",
        "srec",
}

OBJCOPY_FORMATS = {
        "bin",
        "ihex",
        "srec",
}

@dataclass(frozen=True)
class LinkedFormatRule:
    ext: str
    kind: Literal["linked"] = "linked"

@dataclass(frozen=True)
class ObjcopyFormatRule:
    ext: str
    from_format: str
    objcopy_format: str
    kind: Literal["objcopy"] = "objcopy"

FormatRule = LinkedFormatRule | ObjcopyFormatRule

FORMAT_RULES: dict[str, FormatRule] = {
        "elf": LinkedFormatRule(ext=".elf"),
        "bin": ObjcopyFormatRule(from_format="elf", objcopy_format="binary", ext=".bin"),
        "ihex": ObjcopyFormatRule(from_format="elf",objcopy_format="ihex", ext=".hex"),
        "srec": ObjcopyFormatRule(from_format="elf", objcopy_format="srec", ext=".srec"),
}


@dataclass(frozen=True)
class Target:
    arch: str
    name: str 
    toolchain: str 
    sources: list[str]
    out: str
    formats: list[str]
    cflags: list[str]

@dataclass(frozen=True)
class Toolchain:
    name: str
    cc: str
    objcopy: str | None 
    readelf: str | None 

def expect_table(obj, path, errors):
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected table")
        return {}
    return obj

def expect_str(obj, key, path, errors):
    value = obj.get(key)
    if not isinstance(value, str) or not value: 
        errors.append(f"{path}.{key}: expected non-empty string")
        return ""
    return value

def expect_list_str(obj, key, path, errors):
    value = obj.get(key)
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value): 
        errors.append(f"{path}.{key}: expected list of non-empty strings")
        return []
    return value 

def load_toolchains(raw):
    errors = []
    results = {}
    
    table = expect_table(raw.get("toolchains"), "toolchains", errors)

    for name, conf in table.items():
        path = f"toolchains.{name}"
        conf = expect_table(conf, path, errors)

        cc = expect_str(conf, "cc", path, errors)

        objcopy = conf.get("objcopy")
        if objcopy is not None and not isinstance(objcopy, str):
            errors.append(f"{path}.objcopy: expected string")

        readelf = conf.get("readelf")
        if readelf is not None and not isinstance(readelf, str):
            errors.append(f"{path}.readelf: expected string")

        results[name] = Toolchain(
                name=name,
                cc=cc,
                objcopy=objcopy,
                readelf=readelf,
        )
    return results, errors 

def load_targets(raw, toolchains):
    errors = []
    results = []
    
    table = expect_table(raw.get("target"), "target", errors)

    for arch, arch_table in table.items():
        arch_path = f"target.{arch}"
        arch_table = expect_table(arch_table, arch_path, errors)

        for name, conf, in arch_table.items():
            path = f"{arch_path}.{name}"
            conf = expect_table(conf, path, errors)

            toolchain = expect_str(conf, "toolchain", path, errors)
            sources = expect_list_str(conf, "sources", path, errors)
            out = expect_str(conf, "out", path, errors)
            formats = expect_list_str(conf, "formats", path, errors)
            cflags = conf.get("cflags", [])

            if not isinstance(cflags, list) or not all(isinstance(x, str) for x in cflags):
                errors.append(f"{path}.cflags: expect list of strings")
                cflags = []
            if toolchain and toolchain not in toolchains:
                errors.append(f"{path}.toolchain: unkown toolchain {toolchain!r}")
            for format in formats:
                if format not in SUPPORTED_FORMATS:
                    errors.append(f"{path}.formats: unsupported/unknown format {format!r}")
            if any(format in OBJCOPY_FORMATS for format in formats):
                tc = toolchains.get(toolchain)
                if tc and not tc.objcopy:
                    errors.append(f"{path}: objcopy is required for this format, but toolchain {toolchain!r} has none")
            for source in sources:
                if not Path(source).is_file():
                    errors.append(f"{path}.sources: missing source file {source!r}")
            results.append(Target(
                arch=arch,
                name=name, 
                toolchain=toolchain,
                sources=sources,
                out=out,
                formats=formats,
                cflags=cflags,
            ))
    return results, errors


@dataclass(frozen=True)
class Command:
    argv: list[str]

    def shell(self) -> str:
        return shlex.join(self.argv)

class TargetCommandBuilder:
    def __init__(self, target: Target, toolchain: Toolchain):
        self.target = target 
        self.toolchain = toolchain
    
    def commands(self) -> list[Command]:
        commands = []

        if self.needs_elf():
            commands.append(self.link_command("elf"))
    
        for format in self.target.formats:
            if format == "elf":
                continue 

            rule = FORMAT_RULES[format]

            if rule.kind == "linked":
                commands.append(self.link_command(format))
            elif rule.kind == "objcopy":
                commands.append(self.objcopy_command(format))
            else:
                raise AssertionError(f"unkown rule kind: {rule.kind}")
        return commands

    def needs_elf(self):
        return ("elf" in self.target.formats 
                or any(FORMAT_RULES[format].kind == "objcopy" for format in self.target.formats)
                )
    def output_path(self, format: str) -> str: 
        return self.target.out + FORMAT_RULES[format].ext

    def link_command(self, format: str) -> Command:
        rule = FORMAT_RULES[format]

        if not isinstance(rule, LinkedFormatRule):
            raise TypeError(f"{format!r} is not a linked format")

        return Command([
            self.toolchain.cc,
            *self.target.cflags,
            *self.target.sources,
            "-o",
            self.output_path(format),
            ])

    def objcopy_command(self, format: str) -> Command: 
        rule = FORMAT_RULES[format]

        if not isinstance(rule, ObjcopyFormatRule):
            raise TypeError(f"{format!r} is not an objcopy format")

        if self.toolchain.objcopy is None:
            raise ValueError(f"{self.target.name}: format {format!r} requires objcopy")

        return Command([
            self.toolchain.objcopy,
            "-O",
            rule.objcopy_format,
            self.output_path(rule.from_format),
            self.output_path(format),
            ])


class DockerCommandBuilder:
    def __init__(self, image: str, workspace: Path):
        self.image = image
        self.workspace = workspace

    def wrap(self, command: Command) -> Command:
        return Command([
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.workspace}:/workspace",
            "-w",
            "/workspace",
            self.image,
            *command.argv,
        ])


# input target.toml 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", type=str, help="path to targets.toml where binary generation specs are defined")
    parser.add_argument("toolchains", type=str, help="path to toolchains.toml")
    parser.add_argument("--binary", nargs='+', help="list specific binaries to be built as arch.name, e.g. riscv64.bootloader")
    parser.add_argument("--family", nargs='+', help="list families of binaries to be built (i.e. riscv64)")
    parser.add_argument("--docker", action="store_true", help="if commands should be output to be run on docker")
    parser.add_argument("--image", type=str, help="the docker image the commands should be run on")
    
    args = parser.parse_args()
    
    if args.docker and not args.image:
        parser.error("You must specify an image if you configure for docker")
    
    with open(args.targets, "rb") as f:
        targets_config = tomllib.load(f) 
    
    with open(args.toolchains, "rb") as f:
        toolchains_config = tomllib.load(f)
    
    toolchains, toolchains_errors = load_toolchains(toolchains_config)
    targets, targets_errors = load_targets(targets_config, toolchains)

    errors = targets_errors + toolchains_errors 

    if errors:
        for error in errors:
            print(f"TOML parse error: {error}", file=sys.stderr)
        sys.exit(1)

    if not targets:
        raise AssertionError("No targets found")
    
    known_families = {target.arch for target in targets}
    known_binaries = {f"{target.arch}.{target.name}" for target in targets}
    
    if args.family is not None: 
        unknown = set(args.family) - known_families
        if unknown:
            print(f"Unknown family/families: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            print(f"Known families: {', '.join(sorted(known_families))}",
                  file=sys.stderr)
            sys.exit(1)
    
    if args.binary is not None:
        unknown = set(args.binary) - known_binaries
        if unknown:
            print(f"Unknown binary/binaries: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            print(f"Known binaries: {', '.join(sorted(known_binaries))}",
                  file=sys.stderr)
            sys.exit(1)

    selected_targets = []
    
    for target in targets:
        target_binary = f"{target.arch}.{target.name}"

        family_selected = args.family is not None and target.arch in args.family
        binary_selected = args.binary is not None and target_binary in args.binary 
        if (args.family is None and args.binary is None) or family_selected or binary_selected:
            selected_targets.append(target)

    if args.docker:
        docker_builder = DockerCommandBuilder(workspace=Path.cwd(), image=args.image)
 
    commands = []
    for target in selected_targets:
        toolchain = toolchains[target.toolchain]
        builder = TargetCommandBuilder(target, toolchain)

        for command in builder.commands():
            if args.docker:
                command = docker_builder.wrap(command)
            commands.append(command)

    for command in commands:
        print(command.shell())
    
    
 
if __name__ == '__main__':
    main()
