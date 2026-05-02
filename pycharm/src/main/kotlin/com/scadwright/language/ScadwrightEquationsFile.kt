package com.scadwright.language

import com.intellij.extapi.psi.PsiFileBase
import com.intellij.openapi.fileTypes.FileType
import com.intellij.psi.FileViewProvider

class ScadwrightEquationsFile(viewProvider: FileViewProvider) :
    PsiFileBase(viewProvider, ScadwrightEquationsLanguage) {

    override fun getFileType(): FileType = ScadwrightEquationsFileType
    override fun toString(): String = "SCADwright Equations File"
}
