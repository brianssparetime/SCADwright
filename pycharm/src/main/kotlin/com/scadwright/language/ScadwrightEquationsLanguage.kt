package com.scadwright.language

import com.intellij.lang.Language

object ScadwrightEquationsLanguage : Language("ScadwrightEquations") {
    private fun readResolve(): Any = ScadwrightEquationsLanguage
}
