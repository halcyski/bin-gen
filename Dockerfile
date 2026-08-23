FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY toolchains.toml /tmp/toolchains.toml
COPY /scripts/install-toolchains.py /tmp/install-toolchains.py 

RUN apt-get update \ 
	&& apt-get install -y --no-install-recommends python3
	&& python3 /tmp/install-toolchains.py /tmp/toolchains.toml
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /workspace 

