# patch.py -- For dealing with packed-style patches.
# Copyright (C) 2009-2013 Jelmer Vernooij <jelmer@samba.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License or (at your option) a later version.
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

"""Classes for dealing with git am-style patches.

These patches are basically unified diffs with some extra metadata tacked
on.
"""

from io import BytesIO
from difflib import SequenceMatcher
import email.parser
import time

from dulwich.objects import (
    Commit,
    S_ISGITLINK,
    )

FIRST_FEW_BYTES = 8000


def write_commit_patch(f, commit, contents, progress, version=None):
    """Write a individual file patch.

    :param commit: Commit object
    :param progress: Tuple with current patch number and total.
    :return: tuple with filename and contents
    """
    (num, total) = progress
    f.write("From %s %s\n" % (commit.id, time.ctime(commit.commit_time)))
    f.write("From: %s\n" % commit.author)
    f.write("Date: %s\n" % time.strftime("%a, %d %b %Y %H:%M:%S %Z"))
    f.write("Subject: [PATCH %d/%d] %s\n" % (num, total, commit.message))
    f.write("\n")
    f.write("---\n")
    try:
        # FIXME: path manipulation
        import subprocess
        p = subprocess.Popen(["diffstat"], stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE)
    except (ImportError, OSError):
        pass # diffstat not available?
    else:
        (diffstat, _) = p.communicate(contents)
        f.write(diffstat)
        f.write("\n")
    f.write(contents)
    f.write("-- \n")
    if version is None:
        from dulwich import __version__ as dulwich_version
        f.write("Dulwich %d.%d.%d\n" % dulwich_version)
    else:
        f.write("%s\n" % version)


def get_summary(commit):
    """Determine the summary line for use in a filename.

    :param commit: Commit
    :return: Summary string
    """
    return commit.message.splitlines()[0].replace(" ", "-")


def unified_diff(a, b, fromfile='', tofile='', n=3):
    """difflib.unified_diff that doesn't write any dates or trailing spaces.

    Based on the same function in Python2.6.5-rc2's difflib.py
    """
    started = False
    for group in SequenceMatcher(None, a, b).get_grouped_opcodes(n):
        if not started:
            yield b'--- ' + fromfile + b'\n'
            yield b'+++ ' + tofile + b'\n'
            started = True
        i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
        yield ("@@ -%d,%d +%d,%d @@\n" % (i1+1, i2-i1, j1+1, j2-j1)).encode('ascii')
        for tag, i1, i2, j1, j2 in group:
            if tag == 'equal':
                for line in a[i1:i2]:
                    yield b' ' + line
                continue
            if tag == 'replace' or tag == 'delete':
                for line in a[i1:i2]:
                    if not line[-1] == '\n':
                        line += b'\n\\ No newline at end of file\n'
                    yield '-' + line
            if tag == 'replace' or tag == 'insert':
                for line in b[j1:j2]:
                    if not line[-1] == '\n':
                        line += b'\n\\ No newline at end of file\n'
                    yield b'+' + line


def is_binary(content):
    """See if the first few bytes contain any null characters.
    NOTE: This is not a very trustworthy function.
    :param content: Bytestring to check for binary content
    """
    return b'\0' in content[:FIRST_FEW_BYTES]


def shortid(hexsha):
    if hexsha is None:
        return "0" * 7
    else:
        return hexsha[:7].decode('ascii')


def patch_filename(p, root):
    if p is None:
        return b"/dev/null"
    else:
        if type(p) == str: p = p.encode('utf-8')
        if type(root) == str: root = root.encode('utf-8')
        return root + b"/" + p


def write_object_diff(f, store, old_file, new_file, diff_binary=False):
    """Write the diff for an object.

    :param f: File-like object to write to
    :param store: Store to retrieve objects from, if necessary
    :param old_file: (path, mode, hexsha) tuple
    :param new_file: (path, mode, hexsha) tuple
    :param diff_binary: Whether to diff files even if they
        are considered binary files by is_binary().

    :note: the tuple elements should be None for nonexistant files
    """
    (old_path, old_mode, old_id) = old_file
    (new_path, new_mode, new_id) = new_file
    old_path = patch_filename(old_path, "a")
    new_path = patch_filename(new_path, "b")
    def content(mode, hexsha):
        if hexsha is None:
            return b''
        elif S_ISGITLINK(mode):
            return "Submodule commit " + hexsha + "\n"
        else:
            return store[hexsha].data

    def lines(content):
        if not content:
            return []
        else:
            return content.splitlines(True)
    f.writelines(gen_diff_header(
        (old_path, new_path), (old_mode, new_mode), (old_id, new_id)))
    old_content = content(old_mode, old_id)
    new_content = content(new_mode, new_id)
    if not diff_binary and (is_binary(old_content) or is_binary(new_content)):
        f.write("Binary files %s and %s differ\n" % (old_path, new_path))
    else:
        f.writelines(unified_diff(lines(old_content), lines(new_content),
            old_path, new_path))


def gen_diff_header(paths, modes, shas):
    """Write a blob diff header.

    :param paths: Tuple with old and new path
    :param modes: Tuple with old and new modes
    :param shas: Tuple with old and new shas
    """
    (old_path, new_path) = paths
    (old_mode, new_mode) = modes
    (old_sha, new_sha) = shas
    yield b"diff --git " + old_path + b" " + new_path + b"\n"
    if old_mode != new_mode:
        if new_mode is not None:
            if old_mode is not None:
                yield ("old mode %o\n" % old_mode).encode('ascii')
            yield ("new mode %o\n" % new_mode).encode('ascii')
        else:
            yield ("deleted mode %o\n" % old_mode).encode('ascii')
    yield ("index " + shortid(old_sha) + ".." + shortid(new_sha)).encode('ascii')
    if new_mode is not None:
        yield (" %o" % new_mode).encode('ascii')
    yield b"\n"


def write_blob_diff(f, old_file, new_file):
    """Write blob diff.

    :param f: File-like object to write to
    :param old_file: (path, mode, hexsha) tuple (None if nonexisting)
    :param new_file: (path, mode, hexsha) tuple (None if nonexisting)

    :note: The use of write_object_diff is recommended over this function.
    """
    (old_path, old_mode, old_blob) = old_file
    (new_path, new_mode, new_blob) = new_file
    old_path = patch_filename(old_path, "a")
    new_path = patch_filename(new_path, "b")
    def lines(blob):
        if blob is not None:
            return blob.data.splitlines(True)
        else:
            return []
    f.writelines(gen_diff_header(
        (old_path, new_path), (old_mode, new_mode),
        (getattr(old_blob, "id", None), getattr(new_blob, "id", None))))
    old_contents = lines(old_blob)
    new_contents = lines(new_blob)
    f.writelines(unified_diff(old_contents, new_contents,
        old_path, new_path))


def write_tree_diff(f, store, old_tree, new_tree, diff_binary=False):
    """Write tree diff.

    :param f: File-like object to write to.
    :param old_tree: Old tree id
    :param new_tree: New tree id
    :param diff_binary: Whether to diff files even if they
        are considered binary files by is_binary().
    """
    changes = store.tree_changes(old_tree, new_tree)
    for (oldpath, newpath), (oldmode, newmode), (oldsha, newsha) in changes:
        write_object_diff(f, store, (oldpath, oldmode, oldsha),
                                    (newpath, newmode, newsha),
                                    diff_binary=diff_binary)


def git_am_patch_split(f):
    """Parse a git-am-style patch and split it up into bits.

    :param f: File-like object to parse
    :return: Tuple with commit object, diff contents and git version
    """
    parser = email.parser.Parser()
    msg = parser.parse(f)
    c = Commit()
    c.author = msg["from"]
    c.committer = msg["from"]
    try:
        patch_tag_start = msg["subject"].index("[PATCH")
    except ValueError:
        subject = msg["subject"]
    else:
        close = msg["subject"].index("] ", patch_tag_start)
        subject = msg["subject"][close+2:]
    c.message = subject.replace("\n", "") + "\n"
    first = True

    body = BytesIO(msg.get_payload())

    for l in body:
        if l == "---\n":
            break
        if first:
            if l.startswith("From: "):
                c.author = l[len("From: "):].rstrip()
            else:
                c.message += "\n" + l
            first = False
        else:
            c.message += l
    diff = ""
    for l in body:
        if l == "-- \n":
            break
        diff += l
    try:
        version = next(body).rstrip("\n")
    except StopIteration:
        version = None
    return c, diff, version
