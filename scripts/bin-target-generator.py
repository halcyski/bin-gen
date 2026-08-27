#!/usr/bin/env python3
import sys
import tomllib
import argparse 
from dataclasses import dataclass 
from pathlib import Path

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


# input target.toml 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", type=str, help="path to targets.toml where binary generation specs are defined")
    parser.add_argument("toolchains", type=str, help="path to toolchains.toml")
    parser.add_argument("--binary", nargs='+', help="list specific binaries to be built")
    parser.add_argument("--family", nargs='*', help="list families of binaries to be built (i.e. riscv64)")

    args = parser.parse_args()
    
    if args.binary and args.family:
        print("cannot specify both family and binary")
        sys.exit(1)
        return  
    
    
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

    for target in targets:
        print(target.name)

    
 
if __name__ == '__main__':
    main()
