package com.scadwright.language

import com.intellij.lang.injection.MultiHostInjector
import com.intellij.lang.injection.MultiHostRegistrar
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyListLiteralExpression
import com.jetbrains.python.psi.PyStringLiteralExpression
import com.jetbrains.python.psi.PyTargetExpression

// Inject the equations DSL into Python string literals that appear on
// the right-hand side of `equations = ...`. Two shapes are recognised:
//
//   equations = """name = value"""           # single string assignment
//   equations = [ "...", "...", """...""" ]  # list of strings assignment
//
// Anything else (function calls, dict comprehensions, etc.) is left
// alone — the equations parser would reject it at runtime anyway.
class EquationsInjector : MultiHostInjector {

    override fun elementsToInjectIn(): List<Class<out PsiElement>> =
        listOf(PyStringLiteralExpression::class.java)

    override fun getLanguagesToInject(registrar: MultiHostRegistrar, context: PsiElement) {
        val literal = context as? PyStringLiteralExpression ?: return
        if (!isEquationsTarget(literal)) return

        // PyStringLiteralExpression implements PsiLanguageInjectionHost,
        // and getStringElements() yields the individual quoted runs
        // (one for `"""x"""`, two for `"a" "b"` adjacency). Each element
        // exposes contentRange (relative to the element) so we can
        // inject only the inside of the quotes, never the prefix or
        // delimiters themselves.
        val hostStart = literal.textRange.startOffset
        val elements = literal.stringElements
        if (elements.isEmpty()) return

        registrar.startInjecting(ScadwrightEquationsLanguage)
        for (element in elements) {
            val elementOffsetInHost = element.textRange.startOffset - hostStart
            val content = element.contentRange
            val rangeInHost = TextRange(
                elementOffsetInHost + content.startOffset,
                elementOffsetInHost + content.endOffset,
            )
            registrar.addPlace(null, "\n", literal, rangeInHost)
        }
        registrar.doneInjecting()
    }

    private fun isEquationsTarget(literal: PyStringLiteralExpression): Boolean {
        val parent = literal.parent
        val assignment: PyAssignmentStatement = when (parent) {
            is PyAssignmentStatement -> parent
            is PyListLiteralExpression -> parent.parent as? PyAssignmentStatement ?: return false
            else -> return false
        }
        val targets = assignment.targets
        if (targets.size != 1) return false
        val target = targets[0] as? PyTargetExpression ?: return false
        return target.name == "equations"
    }
}
