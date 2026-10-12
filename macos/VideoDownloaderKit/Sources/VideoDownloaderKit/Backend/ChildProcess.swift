import Darwin
import Foundation

/// A child started with posix_spawn in its own process group, its output appended to a log
/// file. Foundation's Process cannot set the group; the group lets a stop reach the child and
/// whatever stays in its group -- not the backend's workers, which start sessions of their own
/// and are stopped by the server (or, if it is killed, by their lifeline).
public final class ChildProcess: @unchecked Sendable {
    public let pid: pid_t
    private let exitSource: DispatchSourceProcess
    private let lock = NSLock()
    private var status: Int32?
    private var waiters: [CheckedContinuation<Int32, Never>] = []

    public static func spawn(executable: URL, arguments: [String], directory: URL, environment: [String: String], log: URL) throws -> ChildProcess {
        try FileManager.default.createDirectory(at: log.deletingLastPathComponent(), withIntermediateDirectories: true)
        var actions: posix_spawn_file_actions_t? = nil
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, 0, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_addopen(&actions, 1, log.path, O_WRONLY | O_CREAT | O_APPEND, 0o644)
        posix_spawn_file_actions_adddup2(&actions, 1, 2)
        posix_spawn_file_actions_addchdir(&actions, directory.path)

        var attributes: posix_spawnattr_t? = nil
        posix_spawnattr_init(&attributes)
        defer { posix_spawnattr_destroy(&attributes) }
        posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT))
        posix_spawnattr_setpgroup(&attributes, 0)

        let argv = [executable.path] + arguments
        let envp = environment.map { "\($0.key)=\($0.value)" }
        var pid: pid_t = 0
        let result = withCStrings(argv) { cArgv in
            withCStrings(envp) { cEnv in
                posix_spawn(&pid, executable.path, &actions, &attributes, cArgv, cEnv)
            }
        }
        guard result == 0 else { throw POSIXError(POSIXErrorCode(rawValue: result) ?? .EINVAL) }
        return ChildProcess(pid: pid)
    }

    private init(pid: pid_t) {
        self.pid = pid
        exitSource = DispatchSource.makeProcessSource(identifier: pid, eventMask: .exit, queue: .global())
        exitSource.setEventHandler { [weak self] in self?.reap() }
        exitSource.resume()
        reap(nonBlocking: true)  // it may already have exited before the source existed
    }

    private func reap(nonBlocking: Bool = false) {
        var raw: Int32 = 0
        let result = waitpid(pid, &raw, nonBlocking ? WNOHANG : 0)
        guard result == pid else { return }
        let code = (raw & 0x7f) == 0 ? (raw >> 8) & 0xff : 128 + (raw & 0x7f)
        lock.lock()
        status = code
        let pending = waiters
        waiters = []
        lock.unlock()
        exitSource.cancel()
        pending.forEach { $0.resume(returning: code) }
    }

    public var exitStatus: Int32? {
        lock.lock(); defer { lock.unlock() }
        return status
    }

    public func waitForExit() async -> Int32 {
        await withCheckedContinuation { continuation in
            lock.lock()
            if let status {
                lock.unlock()
                continuation.resume(returning: status)
            } else {
                waiters.append(continuation)
                lock.unlock()
            }
        }
    }

    /// SIGTERM to the whole group, then SIGKILL if it is still there after `grace`.
    /// (Polled, not raced against a continuation: a continuation cannot be cancelled, and the
    /// SIGKILL must not wait for an exit that only the SIGKILL would cause.)
    public func stop(grace: Duration = .seconds(15)) async {
        guard exitStatus == nil else { return }
        kill(-pid, SIGTERM)
        let deadline = ContinuousClock.now + grace
        while exitStatus == nil, ContinuousClock.now < deadline {
            await pause(milliseconds: 100)  // not Task.sleep: a cancelled task must still wait
        }
        if exitStatus == nil {
            kill(-pid, SIGKILL)
            _ = await waitForExit()
        }
    }
}

/// A sleep that ignores task cancellation (Task.sleep returns at once in a cancelled task,
/// which would turn the grace period into a busy loop).
private func pause(milliseconds: Int) async {
    await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
        DispatchQueue.global().asyncAfter(deadline: .now() + .milliseconds(milliseconds)) { done.resume() }
    }
}

private func withCStrings<R>(_ strings: [String], _ body: (UnsafePointer<UnsafeMutablePointer<CChar>?>) -> R) -> R {
    let pointers = strings.map { strdup($0) } + [nil]
    defer { pointers.forEach { free($0) } }
    return pointers.withUnsafeBufferPointer { body($0.baseAddress!) }
}
