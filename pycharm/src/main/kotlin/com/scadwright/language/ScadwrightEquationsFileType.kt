package com.scadwright.language

import com.intellij.openapi.fileTypes.LanguageFileType
import javax.swing.Icon

// File type required by IntelliJ's Language infrastructure even though
// no .swe-equations files exist on disk — the language only ever lives
// inside injected fragments of Python files. The default extension is
// arbitrary and not user-visible.
object ScadwrightEquationsFileType : LanguageFileType(ScadwrightEquationsLanguage) {
    override fun getName(): String = "SCADwright Equations"
    override fun getDescription(): String = "scadwright equation DSL (injected)"
    override fun getDefaultExtension(): String = "scadeq"
    override fun getIcon(): Icon? = null
}
