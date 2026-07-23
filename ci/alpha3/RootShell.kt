package com.sharkkernel.manager.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.util.concurrent.locks.ReentrantLock

/**
 * Persistent interactive su shell.
 *
 * Root detection deliberately follows the method used by the legacy Shark
 * Manager/KernelManager RootUtils implementation: launch `su` interactively,
 * write a harmless echo command, and consider access granted when the shell
 * accepts the command and returns its callback. This avoids relying on `su -c`
 * or on a specific root-manager library's interpretation of the shell.
 */
object RootShell {
    data class Result(val code: Int, val out: String, val err: String) {
        val ok: Boolean get() = code == 0
    }

    data class Probe(val granted: Boolean, val detail: String)

    private val sessionLock = ReentrantLock()
    @Volatile private var session: SuSession? = null

    private fun getSession(): SuSession {
        val current = session
        if (current != null && !current.closed && !current.denied) return current
        sessionLock.lock()
        try {
            val again = session
            if (again != null && !again.closed && !again.denied) return again
            try { again?.close() } catch (_: Throwable) {}
            return SuSession().also { session = it }
        } finally {
            sessionLock.unlock()
        }
    }

    suspend fun exec(command: String): Result = withContext(Dispatchers.IO) {
        getSession().runCommand(command)
    }

    /** Same root-access test used by the old app: echo through interactive su. */
    suspend fun probe(): Probe = withContext(Dispatchers.IO) {
        val su = getSession()
        if (su.denied || su.closed) {
            return@withContext Probe(false, su.lastError.ifBlank { "não foi possível abrir a shell su" })
        }

        su.runCommand("echo /testRoot/")
        // Match legacy RootUtils.rootAccess() exactly: after the harmless command,
        // root is considered available as long as the interactive su session did
        // not mark itself denied. No UID check and no output-content requirement.
        if (!su.denied && !su.closed) {
            Probe(true, "RootUtils legado: shell su interativa OK")
        } else {
            Probe(false, su.lastError.ifBlank { "acesso su negado" })
        }
    }

    suspend fun granted(): Boolean = probe().granted

    /** Force a fresh permission negotiation on the next access. */
    fun reset() {
        sessionLock.lock()
        try {
            try { session?.close() } catch (_: Throwable) {}
            session = null
        } finally {
            sessionLock.unlock()
        }
    }

    fun q(value: String): String = "'" + value.replace("'", "'\\''") + "'"

    private class SuSession {
        private val ioLock = ReentrantLock()
        private var process: Process? = null
        private var writer: BufferedWriter? = null
        private var reader: BufferedReader? = null
        @Volatile var closed: Boolean = false
            private set
        @Volatile var denied: Boolean = false
            private set
        @Volatile var lastError: String = ""
            private set
        private var sequence: Long = 0

        init {
            try {
                // Intentionally identical to the old RootUtils.SU constructor.
                process = Runtime.getRuntime().exec("su")
                writer = BufferedWriter(OutputStreamWriter(process!!.outputStream))
                reader = BufferedReader(InputStreamReader(process!!.inputStream))
            } catch (t: Throwable) {
                lastError = t.message ?: t.javaClass.simpleName
                denied = true
                closed = true
            }
        }

        fun runCommand(command: String): Result {
            if (closed) return Result(-1, "", lastError.ifBlank { "su shell fechada" })

            ioLock.lock()
            try {
                val w = writer ?: return fail("su stdin indisponível")
                val r = reader ?: return fail("su stdout indisponível")
                val token = "__SHARK_CALLBACK_${System.nanoTime()}_${sequence++}__"

                // The first line mirrors legacy RootUtils. The callback below is
                // prefixed by a newline so even sysfs files without a trailing
                // newline cannot swallow the token into their output.
                w.write(command)
                w.write("\n")
                w.write("__shark_rc=$?; printf '\\n${token}%s\\n' \"\$__shark_rc\"")
                w.write("\n")
                w.flush()

                val output = StringBuilder()
                while (true) {
                    val line = r.readLine()
                    if (line == null) {
                        closed = true
                        denied = true
                        lastError = "EOF da shell su"
                        return Result(-1, output.toString().trim(), lastError)
                    }
                    if (line.startsWith(token)) {
                        val code = line.removePrefix(token).trim().toIntOrNull() ?: -1
                        return Result(code, output.toString().trim(), "")
                    }
                    if (output.isNotEmpty()) output.append('\n')
                    output.append(line)
                }
            } catch (t: Throwable) {
                lastError = t.message ?: t.javaClass.simpleName
                closed = true
                denied = true
                return Result(-1, "", lastError)
            } finally {
                ioLock.unlock()
            }
        }

        private fun fail(message: String): Result {
            lastError = message
            closed = true
            denied = true
            return Result(-1, "", message)
        }

        fun close() {
            ioLock.lock()
            try {
                if (!closed) {
                    try {
                        writer?.write("exit\n")
                        writer?.flush()
                    } catch (_: Throwable) {}
                }
                try { writer?.close() } catch (_: Throwable) {}
                try { reader?.close() } catch (_: Throwable) {}
                try { process?.destroy() } catch (_: Throwable) {}
                closed = true
            } finally {
                ioLock.unlock()
            }
        }
    }
}
