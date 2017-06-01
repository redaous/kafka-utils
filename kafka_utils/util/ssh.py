# -*- coding: utf-8 -*-
# Copyright 2016 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import socket
import sys
import time
from contextlib import closing
from contextlib import contextmanager

from paramiko.agent import AgentRequestHandler
from paramiko.client import AutoAddPolicy
from paramiko.client import SSHClient

from kafka_utils.util.error import MaxConnectionAttemptsError


class Connection:
    """Represents a SSH connection with an SSH server.
    """

    def __init__(self, client, forward_agent, sudoable):
        self.transport = client.get_transport()
        self.forward_agent = forward_agent
        self.sudoable = sudoable

    def sudo_command(self, command, bufsize=-1):
        """Sudo a command on the SSH server.
        Delegates to :func`~ssh.Connection.exec_command`

        :param command: the command to execute
        :type command: str
        :param bufsize: interpreted the same way as by the built-in C{file()} function in python
        :type bufsize: int
        :returns the stdin, stdout, and stderr of the executing command
        :rtype: tuple(L{ChannelFile}, L{ChannelFile}, L{ChannelFile})

        :raises SSHException: if the server fails to execute the command
        """
        new_command = "sudo -S -p 'sudo password:' {0}".format(command)
        return self.exec_command(new_command, bufsize)

    def exec_command(self, command, bufsize=-1):
        """Execute a command on the SSH server while preserving underling
        agent forwarding and sudo privileges.
        https://github.com/paramiko/paramiko/blob/1.8/paramiko/client.py#L348

        :param command: the command to execute
        :type command: str
        :param bufsize: interpreted the same way as by the built-in C{file()} function in python
        :type bufsize: int
        :returns the stdin, stdout, and stderr of the executing command
        :rtype: tuple(L{ChannelFile}, L{ChannelFile}, L{ChannelFile})

        :raises SSHException: if the server fails to execute the command
        """
        channel = self.transport.open_session()

        if self.forward_agent:
            AgentRequestHandler(channel)
        if self.sudoable:
            channel.get_pty()

        channel.exec_command(command)

        stdin = channel.makefile('wb', bufsize)
        stdout = channel.makefile('rb', bufsize)
        stderr = channel.makefile_stderr('rb', bufsize)
        return (stdin, stdout, stderr)


@contextmanager
def ssh(host, forward_agent=False, sudoable=False, max_attempts=1, max_timeout=5):
    """Manages a SSH connection to the desired host.

    :param host: the server to connect to
    :type host: str
    :param forward_agent: forward the local agents
    :type forward_agent: bool
    :param sudoable: allow sudo commands
    :type sudoable: bool
    :param max_attempts: the maximum attempts to connect to the desired host
    :type max_attempts: int
    :param max_timeout: the maximum timeout in seconds to sleep between attempts
    :type max_timeout: int
    :returns a SSH connection to the desired host
    :rtype: Connection

    :raises MaxConnectionAttemptsError: Exceeded the maximum attempts
    to establish the SSH connection.
    """
    with closing(SSHClient()) as client:
        client.set_missing_host_key_policy(AutoAddPolicy())

        attempts = 0
        while attempts < max_attempts:
            try:
                attempts += 1
                client.connect(hostname=host, timeout=max_timeout)
                break
            except socket.error:
                if attempts < max_attempts:
                    time.sleep(max_timeout)
        else:
            raise MaxConnectionAttemptsError(
                "Exceeded max attempts to connect to host: {0}".format(max_attempts)
            )

        yield Connection(client, forward_agent, sudoable)


def report_stdout(host, stdout):
    """Take a stdout and print it's lines to output if lines are present.

    :param host: the host where the process is running
    :type host: str
    :param stdout: the std out of that process
    :type stdout: paramiko.channel.Channel
    """
    lines = stdout.readlines()
    if lines:
        print("STDOUT from {host}:".format(host=host))
        for line in lines:
            print(line.rstrip(), file=sys.stdout)


def report_stderr(host, stderr):
    """Take a stderr and print it's lines to output if lines are present.

    :param host: the host where the process is running
    :type host: str
    :param stderr: the std error of that process
    :type stderr: paramiko.channel.Channel
    """
    lines = stderr.readlines()
    if lines:
        print("STDERR from {host}:".format(host=host))
        for line in lines:
            print(line.rstrip(), file=sys.stderr)
