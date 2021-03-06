# hooks.py -- for dealing with git hooks
# Copyright (C) 2012-2013 Jelmer Vernooij and others.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License or (at your option) a later version of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

"""Access to hooks.

FIXME:
Hooks are simply a bad idea. I understand the concept. That's no excuse for 
this type of code execution bullshit. Give an attacker remote code execution? 
No thank you.
"""

import os
#import subprocess
import sys
import tempfile

from dulwich.errors import (
    HookError,
)


class Hook(object):
    """Generic hook object."""

    def execute(self, *args):
        """Execute the hook with the given args

        :param args: argument list to hook
        :raise HookError: hook execution failure
        :return: a hook may return a useful value
        """
        raise NotImplementedError(self.execute)


class ShellHook(Hook):
    """Hook by executable file

    Implements standard githooks(5) [0]:

    [0] http://www.kernel.org/pub/software/scm/git/docs/githooks.html
    """

    def __init__(self, name, path, numparam,
                 pre_exec_callback=None, post_exec_callback=None):
        """Setup shell hook definition

        :param name: name of hook for error messages
        :param path: absolute path to executable file
        :param numparam: number of requirements parameters
        :param pre_exec_callback: closure for setup before execution
            Defaults to None. Takes in the variable argument list from the
            execute functions and returns a modified argument list for the
            shell hook.
        :param post_exec_callback: closure for cleanup after execution
            Defaults to None. Takes in a boolean for hook success and the
            modified argument list and returns the final hook return value
            if applicable
        """
        self.name = name
        self.filepath = path
        self.numparam = numparam

        self.pre_exec_callback = pre_exec_callback
        self.post_exec_callback = post_exec_callback

        if sys.version_info[0] == 2 and sys.platform == 'win32':
            # Python 2 on windows does not support unicode file paths
            # http://bugs.python.org/issue1759845
            self.filepath = self.filepath.encode(sys.getfilesystemencoding())

    def execute(self, *args):
        """Execute the hook with given args"""

        if len(args) != self.numparam:
            raise HookError("Hook %s executed with wrong number of args. \
                            Expected %d. Saw %d. args: %s"
                            % (self.name, self.numparam, len(args), args))

        if (self.pre_exec_callback is not None):
            args = self.pre_exec_callback(*args)

        try:
            # FIXME: Hooks are bad design. Replace them.
            #ret = subprocess.call([self.filepath] + list(args))
            ret = 0
            if ret != 0:
                if (self.post_exec_callback is not None):
                    self.post_exec_callback(0, *args)
                raise HookError("Hook %s exited with non-zero status"
                                % (self.name))
            if (self.post_exec_callback is not None):
                return self.post_exec_callback(1, *args)
        except OSError:  # no file. silent failure.
            if (self.post_exec_callback is not None):
                self.post_exec_callback(0, *args)


class PreCommitShellHook(ShellHook):
    """pre-commit shell hook"""

    def __init__(self, controldir):
        filepath = os.path.join(controldir, 'hooks', 'pre-commit')

        ShellHook.__init__(self, 'pre-commit', filepath, 0)


class PostCommitShellHook(ShellHook):
    """post-commit shell hook"""

    def __init__(self, controldir):
        filepath = os.path.join(controldir, 'hooks', 'post-commit')

        ShellHook.__init__(self, 'post-commit', filepath, 0)


class CommitMsgShellHook(ShellHook):
    """commit-msg shell hook

    :param args[0]: commit message
    :return: new commit message or None
    """

    def __init__(self, controldir):
        filepath = os.path.join(controldir, 'hooks', 'commit-msg')

        def prepare_msg(*args):
            """
            FIXME:
            More generally, the POSIX specification of mkstemp() does not say 
            anything about file modes, so the application should make sure its 
            file mode creation mask (see umask(2)) is set appropriately before 
            calling mkstemp() (and mkostemp())."""
            (fd, path) = tempfile.mkstemp()

            a0 = args[0]
            if type(a0) == str:
                a0 = args[0].encode('utf-8')
            with os.fdopen(fd, 'wb') as f:
                f.write(a0)

            return (path,)

        def clean_msg(success, *args):
            if success:
                with open(args[0], 'rb') as f:
                    new_msg = f.read()
                os.unlink(args[0])
                return new_msg
            os.unlink(args[0])

        ShellHook.__init__(self, 'commit-msg', filepath, 1,
                           prepare_msg, clean_msg)
