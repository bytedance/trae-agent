import subprocess
import time

import docker
import pexpect


class Sandbox:
    def __init__(self, namespace: str, name: str, tag: str, instance: dict, tools_path: str):
        self.namespace = namespace
        self.name = name
        self.tag = tag
        self.client = docker.from_env()
        self.commit_id = instance["base_commit"]
        self.instance_id = instance["instance_id"]
        self.container = None
        self.shell = None
        self.tools_path = tools_path

    def get_project_path(self):
        project_path = self.container.exec_run("pwd").output.decode().strip()
        return project_path

    def start_container(self):
        image = f"{self.namespace}/{self.name}:{self.tag}"
        host_path = "/tmp"
        container_path = "/tmp"
        self.container = self.client.containers.run(
            image,
            detach=True,
            tty=True,
            stdin_open=True,
            privileged=True,
            volumes={host_path: {"bind": container_path, "mode": "rw"}},
        )
        print(f"Container {self.container.short_id} started with image {image}")

        cmd = f"chmod -R 777 {self.tools_path} && docker cp {self.tools_path} {self.container.name}:/home/swe-bench/"
        subprocess.run(cmd, check=True, shell=True)

        checkout_res = self.container.exec_run(f"git checkout {self.commit_id}")
        print("checkout: ", checkout_res)

    def start_shell(self):
        if self.container:
            if self.shell and self.shell.isalive():
                self.shell.close(force=True)
            command = f"docker exec -it {self.container.id} /bin/bash"
            self.shell = pexpect.spawn(command, maxread=200000)
            self.shell.expect([r"\$ ", r"# "], timeout=10)
        else:
            raise Exception("Container not started. Call start_container() first.")

    def get_session(self):
        self.start_shell()

        class Session:
            def __init__(self, sandbox):
                self.sandbox = sandbox

            def execute(self, command, timeout=60):
                try:
                    if command[-1] != "&":
                        self.sandbox.shell.sendline(command + " && sleep 0.5")
                    else:
                        self.sandbox.shell.sendline(command)
                    self.sandbox.shell.before = b""
                    self.sandbox.shell.after = b""
                    self.sandbox.shell.buffer = b""
                    time.sleep(2)
                    self.sandbox.shell.expect([r"swe-bench@.*:.*\$ ", r"root@.*:.*# "], 60)
                    try:
                        output = (
                            self.sandbox.shell.before.decode("utf-8")
                            + self.sandbox.shell.after.decode("utf-8")
                            + self.sandbox.shell.buffer.decode("utf-8")
                        )
                    except Exception:
                        output = (
                            self.sandbox.shell.before.decode("utf-8", errors="replace")
                            + self.sandbox.shell.after.decode("utf-8", errors="replace")
                            + self.sandbox.shell.buffer.decode("utf-8", errors="replace")
                        )
                    output_lines = output.split("\r\n")
                    if len(output_lines) > 1:
                        output_lines = output_lines[1:-1]
                    result_message = "\n".join(output_lines).replace("\x1b[?2004l\r", "")
                    return result_message
                except pexpect.TIMEOUT:
                    partial_output = ""
                    if isinstance(self.sandbox.shell.before, bytes):
                        partial_output += self.sandbox.shell.before.decode("utf-8")
                    if isinstance(self.sandbox.shell.after, bytes):
                        partial_output += self.sandbox.shell.after.decode("utf-8")
                    if isinstance(self.sandbox.shell.buffer, bytes):
                        partial_output += self.sandbox.shell.buffer.decode("utf-8")
                    partial_output_lines = partial_output.split("\n")
                    if len(partial_output_lines) > 1:
                        partial_output_lines = partial_output_lines[1:-1]
                        partial_output = "\n".join(partial_output_lines)
                    return (
                        "### Observation: "
                        + f"Error: Command '{command}' timed out after {timeout} seconds. Partial output:\n + {partial_output}"
                    )

            def close(self):
                if self.sandbox.shell:
                    self.sandbox.shell.sendline("exit")
                    self.sandbox.shell.expect(pexpect.EOF)
                    self.sandbox.shell.close(force=True)
                    self.sandbox.shell = None

        return Session(self)

    def stop_container(self):
        if self.container:
            if self.shell and self.shell.isalive():
                self.shell.close(force=True)
                self.shell = None
            self.container.stop()
            self.container.remove()
            print(f"Container {self.container.short_id} stopped and removed")
            self.container = None
