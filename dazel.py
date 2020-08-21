import hashlib
import logging
import os
import shutil
import subprocess
import sys
import collections

### IMPORTANT: These next values must be used in the docker compose file.

# A better way to do this would be for this script to set environment variables with these values
# when running docker-compose, and then use envvar substitution in docker-compose.yml
# (https://docs.docker.com/compose/environment-variables/). For now, this is left as an exercise for
# the reader.

# The container mount point for the repo being built. The build container must mount to this location.
CODE_MOUNT_POINT = "/code"
# The container's output base. The container must mount this directory for build results to be
# available outside of the container.
CONTAINER_OUTPUT_BASE = "/root/.cache/bazel/_bazel_dazel"
# The docker-compose file must set the `container_name` for the bazel container to this value.
BUILD_CONTAINER_NAME = "dazel_build"

### End shared constants


DAZEL_RC_FILENAME = ".dazelrc"
BAZEL_WORKSPACE_FILE = "WORKSPACE"

DEFAULT_DIRECTORY = os.getcwd()
DOCKER_COMPOSE_COMMAND = "docker-compose"
DOCKER_COMMAND = "docker"
DOCKER_COMPOSE_PROJECT_NAME = "dazel"

CONTAINER_OUTPUT_USER_ROOT = "/var/bazel/workspace/_bazel_dazel"
CONTAINER_BAZEL_BIN = "/usr/bin/bazel"

DEFAULT_PORTS = []
DEFAULT_ENV_VARS = []
DEFAULT_DOCKER_COMPOSE_FILE = ""
DEFAULT_USER = ""
DEFAULT_BAZEL_RC_FILE = ""
DEFAULT_DOCKER_RUN_PRIVILEGED = False


logging.basicConfig(level="DEBUG")
logger = logging.getLogger("dazel")

class DockerInstance:
    """
    Handles configuring and launching the docker compose stack, and sending commands to the build
    container.
    """
    def __init__(self, workspace_root,
                       ports, env_vars,
                       docker_compose_file,
                       bazel_rc_file, docker_run_privileged,
                       user):
        self.workspace_root = workspace_root
        self.docker_compose_file = docker_compose_file
        self.bazel_rc_file = bazel_rc_file
        self.docker_run_privileged = docker_run_privileged
        self.user = user

        self._add_ports(ports)
        self._add_env_vars(env_vars)

    @classmethod
    def from_config(cls):
        config = cls._config_from_file()
        config.update(cls._config_from_environment())
        return DockerInstance(
                workspace_root=config.get("DAZEL_WORKSPACE_ROOT", None),
                ports=config.get("DAZEL_PORTS", DEFAULT_PORTS),
                env_vars=config.get("DAZEL_ENV_VARS", DEFAULT_ENV_VARS),
                docker_compose_file=config.get("DAZEL_DOCKER_COMPOSE_FILE",
                                               DEFAULT_DOCKER_COMPOSE_FILE),
                bazel_rc_file=config.get("DAZEL_BAZEL_RC_FILE", DEFAULT_BAZEL_RC_FILE),
                docker_run_privileged=config.get("DAZEL_DOCKER_RUN_PRIVILEGED",
                                                 DEFAULT_DOCKER_RUN_PRIVILEGED),
                user=config.get("DAZEL_USER", DEFAULT_USER),
        )


    def send_command(self, args):
        term_size = shutil.get_terminal_size()
        command = "%s exec -i -e COLUMNS=%s -e LINES=%s -e TERM=%s -w /code %s %s %s %s %s %s %s %s %s %s" % (
            DOCKER_COMMAND,
            term_size.columns,
            term_size.lines,
            os.environ.get("TERM", ""),
            self.env_vars,
            "-t" if sys.stdout.isatty() else "",
            "--privileged" if self.docker_run_privileged else "",
            ("--user=%s" % self.user if self.user else ""),
            BUILD_CONTAINER_NAME,
            CONTAINER_BAZEL_BIN,
            ("--bazelrc=%s/%s" % (CODE_MOUNT_POINT, self.bazel_rc_file)
             if self.bazel_rc_file else ""),
            "--output_user_root=%s" % CONTAINER_OUTPUT_USER_ROOT,
            "--output_base=%s" % CONTAINER_OUTPUT_BASE,
            '"%s"' % '" "'.join(args))
        logger.debug("Sending command: %s", command)
        return os.WEXITSTATUS(os.system(command))


    def start(self):
        """Starts the dazel docker container."""
        rc = 0

        # Verify that the docker executable exists.
        if not self._docker_compose_exists():
            logger.error("ERROR: docker-compose executable could not be found!")
            return 1

        return self._start_compose_services()


    def _run_silent_command(self, command):
        logger.debug("Running silent command: %s", command)
        return subprocess.call(command, stdout=sys.stderr, shell=True)


    def _start_compose_services(self):
        """Starts the docker-compose services."""
        if not self.docker_compose_file:
            return 0

        command = "COMPOSE_PROJECT_NAME=%s docker-compose -f %s up -d --remove-orphans" % (
            DOCKER_COMPOSE_PROJECT_NAME, os.path.join(self.workspace_root, self.docker_compose_file))
        return self._run_silent_command(command)


    def _add_ports(self, ports):
        """Add the given ports to the run string."""
        # This can only be intentional in code, so disregard.
        self.ports = ""
        if not ports:
            return

        # DAZEL_PORTS can be a python iterable or a comma-separated string.
        if isinstance(ports, str):
            ports = [p.strip() for p in ports.split(",")]
        elif ports and not isinstance(ports, collections.Iterable):
            raise RuntimeError("DAZEL_PORTS must be comma-separated string "
                               "or python iterable of strings")

        # calculate the ports string
        self.ports = '-p "%s"' % '" -p "'.join(ports)


    def _add_env_vars(self, env_vars):
        """Add the given env vars to the run string."""
        # This can only be intentional in code, so disregard.
        self.env_vars = ""
        if not env_vars:
            return

        # DAZEL_ENV_VARS can be a python iterable or a comma-separated string.
        if isinstance(env_vars, str):
            env_vars = [p.strip() for p in env_vars.split(",")]
        elif env_vars and not isinstance(env_vars, collections.Iterable):
            raise RuntimeError("DAZEL_ENV_VARS must be comma-separated string "
                               "or python iterable of strings")

        # calculate the env string
        self.env_vars = '-e "%s"' % '" -e "'.join(env_vars)


    def _docker_compose_exists(self):
        """Checks if the docker-compose executable exists."""
        return self._command_exists(DOCKER_COMPOSE_COMMAND)


    def _command_exists(self, cmd):
        """Checks if a command exists on the system."""
        command = "which %s >/dev/null 2>&1" % (cmd)
        rc = self._run_silent_command(command)
        return (rc == 0)


    @classmethod
    def _config_from_file(cls):
        """Creates a configuration from a .dazelrc file."""
        directory = cls._find_workspace_directory()
        dazelrc_path = os.path.join(directory, DAZEL_RC_FILENAME)

        config = { "DAZEL_WORKSPACE_ROOT": directory }

        if os.path.exists(dazelrc_path):
            with open(dazelrc_path, "r") as dazelrc:
                exec(dazelrc.read(), config)

        return config


    @classmethod
    def _config_from_environment(cls):
        """Creates a configuration from environment variables."""
        return { name: value
                 for (name, value) in os.environ.items()
                 if name.startswith("DAZEL_") }


    @classmethod
    def _find_workspace_directory(cls):
        """Find the workspace directory.

        This is done by traversing the directory structure from the given dazel
        directory until we find the WORKSPACE file.
        """
        directory = os.path.realpath(os.getcwd())
        while (directory and directory != "/" and
               not os.path.exists(os.path.join(directory, BAZEL_WORKSPACE_FILE))):
            directory = os.path.dirname(directory)
        return directory


def main():
    # Read the configuration either from .dazelrc or from the environment.
    di = DockerInstance.from_config()

    # Bring the stack up, using docker-compose
    rc = di.start()

    # Forward the command line arguments to the container.
    return di.send_command(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())