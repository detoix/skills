"""Private local files and process locks using only Python and native OS APIs."""

import contextlib
import errno
import os
from pathlib import Path
import secrets
import stat
import time


class PrivateFileError(Exception):
    pass


class WindowsFiles:
    """Reject reparse points and DACL access by other ordinary Windows accounts."""

    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt

        self.c, self.w, self.crt = c, w, msvcrt
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.security = c.WinDLL("advapi32", use_last_error=True)
        pointer = c.c_void_p
        out_pointer = c.POINTER(pointer)

        def bind(dll, name, restype, *args):
            function = getattr(dll, name)
            function.restype, function.argtypes = restype, list(args)
            return function

        self.close = bind(self.kernel, "CloseHandle", w.BOOL, w.HANDLE)
        self.free = bind(self.kernel, "LocalFree", pointer, pointer)
        self.process = bind(self.kernel, "GetCurrentProcess", w.HANDLE)
        self.create = bind(self.kernel, "CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD,
                           w.DWORD, pointer, w.DWORD, w.DWORD, w.HANDLE)
        self.file_info = bind(self.kernel, "GetFileInformationByHandleEx", w.BOOL,
                              w.HANDLE, c.c_int, pointer, w.DWORD)
        self.open_token = bind(self.security, "OpenProcessToken", w.BOOL,
                               w.HANDLE, w.DWORD, c.POINTER(w.HANDLE))
        self.token_info = bind(self.security, "GetTokenInformation", w.BOOL,
                               w.HANDLE, c.c_int, pointer, w.DWORD, c.POINTER(w.DWORD))
        self.sid_string = bind(self.security, "ConvertSidToStringSidW", w.BOOL,
                               pointer, out_pointer)
        self.descriptor = bind(self.security, "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                               w.BOOL, w.LPCWSTR, w.DWORD, out_pointer, pointer)
        self.get_security = bind(self.security, "GetSecurityInfo", w.DWORD, w.HANDLE,
                                 c.c_int, w.DWORD, out_pointer, out_pointer,
                                 out_pointer, out_pointer, out_pointer)
        self.equal_sid = bind(self.security, "EqualSid", w.BOOL, pointer, pointer)
        self.get_ace = bind(self.security, "GetAce", w.BOOL, pointer, w.DWORD, out_pointer)

        class SecurityAttributes(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", pointer), ("inherit", w.BOOL)]

        class Acl(c.Structure):
            _fields_ = [("revision", w.BYTE), ("reserved", w.BYTE), ("size", w.WORD),
                        ("count", w.WORD), ("reserved2", w.WORD)]

        self.attributes_type, self.acl_type = SecurityAttributes, Acl
        token, size = w.HANDLE(), w.DWORD()
        if not self.open_token(self.process(), 0x0008, c.byref(token)):  # TOKEN_QUERY
            raise PrivateFileError("Cannot inspect the Windows user identity.")
        try:
            self.token_info(token, 1, None, 0, c.byref(size))  # TokenUser
            self.identity = c.create_string_buffer(size.value)
            if not self.token_info(token, 1, self.identity, size, c.byref(size)):
                raise PrivateFileError("Cannot inspect the Windows user identity.")
        finally:
            self.close(token)
        self.sid = c.cast(self.identity, c.POINTER(pointer))[0]
        sid_text = pointer()
        if not self.sid_string(self.sid, c.byref(sid_text)):
            raise PrivateFileError("Cannot inspect the Windows user identity.")
        try:
            self.sddl = "D:P(A;;FA;;;" + c.wstring_at(sid_text) + ")"
        finally:
            self.free(sid_text)

    @contextlib.contextmanager
    def security_attributes(self):
        c = self.c
        descriptor = c.c_void_p()
        if not self.descriptor(self.sddl, 1, c.byref(descriptor), None):
            raise PrivateFileError("Cannot create private Windows file permissions.")
        try:
            attributes = self.attributes_type(c.sizeof(self.attributes_type), descriptor, False)
            yield c.byref(attributes)
        finally:
            self.free(descriptor)

    def open(self, path, writable, create, exclusive):
        c = self.c
        # Security attributes apply at creation, before any credential is written.
        with self.security_attributes() as attributes:
            access = 0x80020000 | (0x40000000 if writable else 0)  # READ_CONTROL + generic R/W
            disposition = 1 if exclusive else 4 if create else 3  # CREATE_NEW / OPEN_ALWAYS / OPEN_EXISTING
            name = str(path)
            if not name.startswith("\\\\?\\"):
                name = "\\\\?\\UNC\\" + name[2:] if name.startswith("\\\\") else "\\\\?\\" + name
            handle = self.create(name, access, 7, attributes, disposition, 0x00200080, None)
        if handle == c.c_void_p(-1).value:
            code = c.get_last_error()
            if code in (2, 3):
                raise FileNotFoundError()
            if code in (80, 183):
                raise FileExistsError()
            raise PrivateFileError("Cannot open the private file on Windows.")
        try:
            attributes = (self.w.DWORD * 2)()
            if not self.file_info(handle, 9, attributes, c.sizeof(attributes)):
                raise PrivateFileError("Cannot verify Windows file attributes.")
            if attributes[0] & (0x00000400 | 0x00000010):  # reparse point or directory
                raise PrivateFileError("Private files cannot be links or directories.")
            self.verify(handle)
            flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOINHERIT | os.O_BINARY
            fd = self.crt.open_osfhandle(handle, flags)
            handle = None  # The CRT descriptor now owns the native handle.
            return fd
        finally:
            if handle is not None:
                self.close(handle)

    def verify(self, handle):
        c = self.c
        owner, acl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        error = self.get_security(handle, 1, 5, c.byref(owner), None,
                                  c.byref(acl), None, c.byref(descriptor))
        if error:
            raise PrivateFileError("Cannot verify private Windows file permissions.")
        try:
            if not owner or not self.equal_sid(owner, self.sid) or not acl:
                raise PrivateFileError("Private Windows files must belong exclusively to the current user.")
            header = c.cast(acl, c.POINTER(self.acl_type)).contents
            if not header.count:
                raise PrivateFileError("Private Windows file permissions are unavailable.")
            for index in range(header.count):
                ace = c.c_void_p()
                if not self.get_ace(acl, index, c.byref(ace)):
                    raise PrivateFileError("Cannot verify private Windows file permissions.")
                # A standard ACCESS_ALLOWED_ACE stores its SID after the header and mask.
                if c.c_ubyte.from_address(ace.value).value != 0 or not self.allowed_sid(ace.value + 8):
                    raise PrivateFileError("Private Windows files must not grant access to other users; use set-token to create one.")
        finally:
            self.free(descriptor)

    def allowed_sid(self, sid):
        if self.equal_sid(sid, self.sid):
            return True
        text = self.c.c_void_p()
        if not self.sid_string(sid, self.c.byref(text)):
            raise PrivateFileError("Cannot verify private Windows file permissions.")
        try:
            # SYSTEM and machine administrators retain OS-level access, like root on POSIX.
            return self.c.wstring_at(text) in {"S-1-5-18", "S-1-5-32-544"}
        finally:
            self.free(text)


_windows = None


def open_private(path, *, writable=False, create=False, exclusive=False):
    """Return an owned descriptor; reject unsafe files before reading their contents."""
    if os.name == "nt":
        global _windows
        if _windows is None:
            _windows = WindowsFiles()
        return _windows.open(Path(path).absolute(), writable, create, exclusive)
    flags = os.O_RDWR if writable else os.O_RDONLY
    flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    if create:
        flags |= os.O_CREAT
    if exclusive:
        flags |= os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PrivateFileError("Private files must be regular, owned by this user, with mode 600.")
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextlib.contextmanager
def locked(path, timeout=30):
    """The stable lock file is never removed, so concurrent processes share one lock."""
    fd = open_private(path, writable=True, create=True)
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            def lock():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def unlock():
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def lock():
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock():
                fcntl.flock(fd, fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock()
                acquired = True
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise PrivateFileError("Cannot lock the local credential file.") from None
                if time.monotonic() >= deadline:
                    raise PrivateFileError("Another client holds the credential lock; retry later.") from None
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        yield
    finally:
        try:
            if acquired:
                unlock()
        finally:
            os.close(fd)


def atomic_write(path, contents):
    """Create a private file before writing, then atomically replace the destination."""
    path = Path(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(16))
    fd = open_private(temporary, writable=True, create=True, exclusive=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
