"""QProcess children isolated in a Windows Job Object (kill-on-close)."""
import ctypes
from ctypes import wintypes
import os

from PySide6.QtCore import QProcess, QProcessEnvironment, QObject, QTimer, Signal


class Job:
    def __init__(self, memory_limit=0):
        self.handle = None
        if os.name != "nt":
            return
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_uint64 * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if memory_limit:
            limits.BasicLimitInformation.LimitFlags |= 0x200  # JOB_MEMORY
            limits.JobMemoryLimit = int(memory_limit)
        if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError("無法建立工作程序隔離，請重新啟動程式")

    def assign(self, pid):
        if self.handle:
            process = self.kernel.OpenProcess(0x0100 | 0x0001, False, int(pid))
            try:
                if not process or not self.kernel.AssignProcessToJobObject(self.handle, process):
                    raise OSError("無法隔離子程序，已停止工作以避免殘留程序")
            finally:
                if process:
                    self.kernel.CloseHandle(process)

    def terminate(self):
        if self.handle:
            self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class ManagedProcess(QObject):
    line = Signal(str)
    done = Signal(int, str)

    def __init__(self, program, args, parent=None, timeout=180000, memory_limit=0):
        super().__init__(parent)
        self.proc = QProcess(self)
        self.proc.setProgram(str(program))
        self.proc.setArguments([str(a) for a in args])
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.buffer, self.output, self.job, self.ended = b"", "", None, False
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.started.connect(self._started)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.timeout = timeout
        self.memory_limit = memory_limit

    def start(self):
        try:
            self.job = Job(self.memory_limit)
            self.proc.start()
            if self.timeout:
                self.timer.start(self.timeout)
        except OSError as exc:
            self._finish(-1, str(exc))

    def _started(self):
        try:
            self.job.assign(self.proc.processId())
        except OSError as exc:
            self.output += str(exc)
            self.cancel()

    def _read(self):
        self.buffer += bytes(self.proc.readAllStandardOutput())
        while b"\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n", 1)
            text = raw.decode("utf-8", errors="replace").rstrip("\r")
            self.output = (self.output + text + "\n")[-2_000_000:]
            self.line.emit(text)

    def _finished(self, code, _status):
        self._read()
        if self.buffer:
            self.output += self.buffer.decode("utf-8", errors="replace")
            self.buffer = b""
        self._finish(code, self.output)

    def _finish(self, code, output):
        if self.ended:
            return
        self.ended = True
        self.timer.stop()
        if self.job:
            self.job.close()
        self.done.emit(code, output)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(-1, "必要元件無法啟動：" + self.proc.program() + " " + self.proc.errorString())

    def _timeout(self):
        self.output += "\nConnection timeout: 工作程序逾時\n"
        self.cancel()

    def cancel(self):
        if self.job:
            self.job.terminate()
        self.proc.kill()

