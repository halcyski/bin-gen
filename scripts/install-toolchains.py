#!/usr/bin/env python3 
import subprocess
import sys
import tomllib

def main():
    # lol why is there no argc
    if len(sys.argv) < 2:
        print("please provide a path to to targets TOML")
        return 
    # also no sys path appending bc it will just live in 
    # docker root directory 
    path = sys.argv[1]

    with open(path, "rb") as f:
        config = tomllib.load(f)

    packages = []
   
    
    # get all packages defined in toolchains for each target
    for toolchain in config["toolchains"].values():
        packages.extend(toolchain.get("packages", []))
    
    packages = sorted(set(packages))

    if not packages:
        print("no toolchain packages found, please define in toolchains.toml")
        return

    command = [
            "apt-get",
            "install",
            "-y",
            "--no-install-recommends",
            "-q", 
            *packages,
        ]

    print("+", " ".join(command))
    subprocess.run(command, check=True)




if __name__ == '__main__':
    main()

