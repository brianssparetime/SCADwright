package com.scadwright.language

import com.intellij.codeInsight.completion.CompletionContributor
import com.intellij.codeInsight.completion.CompletionParameters
import com.intellij.codeInsight.completion.CompletionProvider
import com.intellij.codeInsight.completion.CompletionResultSet
import com.intellij.codeInsight.completion.CompletionType
import com.intellij.codeInsight.completion.InsertHandler
import com.intellij.codeInsight.completion.InsertionContext
import com.intellij.codeInsight.lookup.LookupElement
import com.intellij.codeInsight.lookup.LookupElementBuilder
import com.intellij.patterns.PlatformPatterns
import com.intellij.util.ProcessingContext

class EquationsCompletionContributor : CompletionContributor() {

    init {
        extend(
            CompletionType.BASIC,
            PlatformPatterns.psiElement().withLanguage(ScadwrightEquationsLanguage),
            EquationsCompletionProvider(),
        )
    }

    private class EquationsCompletionProvider : CompletionProvider<CompletionParameters>() {
        override fun addCompletions(
            parameters: CompletionParameters,
            context: ProcessingContext,
            result: CompletionResultSet,
        ) {
            // The injected document is what the equations PSI lives in.
            val text = parameters.editor.document.charsSequence
            val caret = parameters.offset

            if (precededByTypeColon(text, caret)) {
                addTypeNames(result)
                return
            }

            addExpressionPositionCompletions(result)
        }

        // Walk left from the caret over the identifier currently being
        // typed, then over whitespace, and check whether the previous
        // non-blank character is a `:`. That marks the type-tag spot
        // (`name :_`), where only type names are valid completions.
        private fun precededByTypeColon(text: CharSequence, caret: Int): Boolean {
            var i = caret - 1
            while (i >= 0 && isIdentifierPart(text[i])) i--
            while (i >= 0 && text[i].isWhitespace() && text[i] != '\n') i--
            return i >= 0 && text[i] == ':'
        }

        private fun isIdentifierPart(c: Char): Boolean = c.isLetterOrDigit() || c == '_'

        private fun addTypeNames(result: CompletionResultSet) {
            for (name in Vocabulary.typeNames) {
                result.addElement(
                    LookupElementBuilder.create(name)
                        .withTypeText("type", true)
                )
            }
        }

        private fun addExpressionPositionCompletions(result: CompletionResultSet) {
            for (name in Vocabulary.mathFunctions) result.addElement(callable(name, "math"))
            for (name in Vocabulary.builtinFunctions) result.addElement(callable(name, "builtin"))
            for (name in Vocabulary.cardinalityHelpers) result.addElement(callable(name, "cardinality"))
            for (name in Vocabulary.constants) {
                result.addElement(
                    LookupElementBuilder.create(name)
                        .withTypeText("constant", true)
                )
            }
            for (name in Vocabulary.keywords) {
                result.addElement(
                    LookupElementBuilder.create(name)
                        .withTypeText("keyword", true)
                )
            }
        }

        private fun callable(name: String, kind: String): LookupElement =
            LookupElementBuilder.create(name)
                .withTailText("(…)", true)
                .withTypeText(kind, true)
                .withInsertHandler(ParenInsertHandler)

        // Inserts `()` after a callable name and parks the caret between
        // them. The platform's ParenthesesInsertHandler exists but its
        // signature has wandered between platform versions; this minimal
        // local handler avoids the API drift risk.
        private object ParenInsertHandler : InsertHandler<LookupElement> {
            override fun handleInsert(context: InsertionContext, item: LookupElement) {
                val editor = context.editor
                val document = editor.document
                val tail = context.tailOffset
                val nextCh = if (tail < document.textLength) document.charsSequence[tail] else ' '
                if (nextCh == '(') {
                    // already followed by `(`; just position the caret after it
                    editor.caretModel.moveToOffset(tail + 1)
                    return
                }
                document.insertString(tail, "()")
                editor.caretModel.moveToOffset(tail + 1)
            }
        }
    }
}
