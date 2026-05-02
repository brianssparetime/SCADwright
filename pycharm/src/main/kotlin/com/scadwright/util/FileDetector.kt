package com.scadwright.util

import com.intellij.openapi.vfs.VirtualFile
import java.io.IOException

/**
 * Decide whether a file is the kind of file the SCADwright actions
 * should be enabled on. Same rule as the VSCode extension: a Python
 * file that contains an `import scadwright` or `from scadwright …`
 * statement at line start.
 *
 * Reads the file contents (cached by VFS) and scans with a regex.
 * Cheap on the small files we care about; the gating runs on every
 * action-update tick, so heavier inspection isn't appropriate here.
 */
object FileDetector {
    private val IMPORT_PATTERN = Regex(
        "(?m)^\\s*(import\\s+scadwright|from\\s+scadwright(\\.|\\s+import))"
    )

    fun isScadwrightFile(file: VirtualFile?): Boolean {
        if (file == null) return false
        if (file.extension != "py") return false
        return try {
            val text = String(file.contentsToByteArray(), Charsets.UTF_8)
            IMPORT_PATTERN.containsMatchIn(text)
        } catch (e: IOException) {
            false
        }
    }
}
