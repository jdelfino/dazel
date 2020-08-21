# dazel

Run Google's bazel inside a docker container via a seamless proxy.

This is a heavily modified fork of https://github.com/nadirizr/dazel. See that repo for more
background, along with usage & installation instructions.

The main functional change on this fork is to run all containers, including the build container,
via `docker-compose`. This fork also removes a bunch of options I don't need.

## Configuration

You can configure dazel in two ways (or combine):
* A .dazelrc file in the workspace root (a sibling of the `WORKSPACE` file).
* Environment variables with the configuration parameters mentioned below.

Note that specific environment variables supercede the values in the .dazelrc file.

The possible parameters to set are (with their defaults):
```python
# REQUIRED: The path, relative to the WORKSPACE root, for the docker-compose file describing how to
# launch the build container and any supporting containers.
DAZEL_DOCKER_COMPOSE_FILE=""

# Add any ports you want to publish from the dazel container to the host, in the
# normal "interface:dockerport:hostport" (e.g. "0.0.0.0:80:80").
# This can be useful if you use the "dazel run //my/cool/webserver/target"
# command for example, and need to publish port 80.
DAZEL_PORTS=[]

# Add any environment variables you want to set in the dazel container
# They will be set via -e in the docker run command
# This can be a python iterable, or a comma-separated string.
DAZEL_ENV_VARS=[]

# Whether or not to run in privileged mode (fixes bazel sandboxing issues on some
# systems). Note that this can be a python boolean equivalent, so if setting
# this from the environment, simply set it to an empty string.
DAZEL_DOCKER_RUN_PRIVILEGED=False

# Path to custom .bazelrc file to use when running the bazel commands.
DAZEL_BAZEL_RC_FILE=""

# The user, in the same format as the --user option docker run and docker exec takes,
# to use when starting the container and executing commands inside of the container
DAZEL_USER = ""
```

## Working example docker-compose file

This example assumes you use the prebuilt dazel image (`image: dazel/dazel`), and that the
docker-compose.yml is found as a sibling of the `WORKSPACE` file. (the `- .:/code` volume).

```
version: '3.1'

services:

  db:
    image: postgres
    container_name: dazel_postgres
    restart: on-failure
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_USER: pguser
      POSTGRES_DB: mydb

  bazel:
    image: dazel/dazel
    container_name: dazel_build
    restart: on-failure
    command: /bin/bash
    tty: true
    volumes:
      - .:/code
      - ~/.cache/bazel/_bazel_dazel/external:/root/.cache/bazel/_bazel_dazel/external:delegated
      - ~/.cache/bazel/_bazel_dazel/execroot:/root/.cache/bazel/_bazel_dazel/execroot:delegated
      - ~/.cache/bazel/_bazel_dazel/action_cache:/root/.cache/bazel/_bazel_dazel/action_cache:delegated
```
