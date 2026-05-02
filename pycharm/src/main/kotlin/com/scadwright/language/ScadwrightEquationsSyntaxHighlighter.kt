package com.scadwright.language

import com.intellij.lexer.Lexer
import com.intellij.openapi.editor.DefaultLanguageHighlighterColors as D
import com.intellij.openapi.editor.colors.TextAttributesKey
import com.intellij.openapi.fileTypes.SyntaxHighlighterBase
import com.intellij.psi.tree.IElementType

// Map equation token types to IntelliJ's default color keys so themes
// pick up sensible defaults without forcing the user to configure
// anything. Keys mirror the VSCode TextMate scopes' intent: math /
// builtin / cardinality functions get the "predefined symbol" key
// (function-like color), type names get METADATA, the optional sigil
// gets METADATA so it pops as a declaration modifier.
class ScadwrightEquationsSyntaxHighlighter : SyntaxHighlighterBase() {

    override fun getHighlightingLexer(): Lexer = ScadwrightEquationsLexer()

    override fun getTokenHighlights(tokenType: IElementType): Array<TextAttributesKey> {
        val key = MAP[tokenType] ?: return emptyArray()
        return arrayOf(key)
    }

    companion object {
        private val MAP: Map<IElementType, TextAttributesKey> = mapOf(
            ScadwrightEquationsTokenTypes.LINE_COMMENT to D.LINE_COMMENT,
            ScadwrightEquationsTokenTypes.NUMBER to D.NUMBER,
            ScadwrightEquationsTokenTypes.STRING to D.STRING,

            ScadwrightEquationsTokenTypes.KEYWORD to D.KEYWORD,
            ScadwrightEquationsTokenTypes.MATH_FUNCTION to D.PREDEFINED_SYMBOL,
            ScadwrightEquationsTokenTypes.BUILTIN_FUNCTION to D.PREDEFINED_SYMBOL,
            ScadwrightEquationsTokenTypes.CARDINALITY_HELPER to D.PREDEFINED_SYMBOL,
            ScadwrightEquationsTokenTypes.TYPE_NAME to D.METADATA,
            ScadwrightEquationsTokenTypes.CONSTANT to D.CONSTANT,

            ScadwrightEquationsTokenTypes.OPTIONAL_SIGIL to D.METADATA,
            ScadwrightEquationsTokenTypes.TYPE_COLON to D.OPERATION_SIGN,
            ScadwrightEquationsTokenTypes.EQUATION_OP to D.OPERATION_SIGN,
            ScadwrightEquationsTokenTypes.COMPARE_OP to D.OPERATION_SIGN,
            ScadwrightEquationsTokenTypes.ARITH_OP to D.OPERATION_SIGN,

            ScadwrightEquationsTokenTypes.L_PAREN to D.PARENTHESES,
            ScadwrightEquationsTokenTypes.R_PAREN to D.PARENTHESES,
            ScadwrightEquationsTokenTypes.L_BRACKET to D.BRACKETS,
            ScadwrightEquationsTokenTypes.R_BRACKET to D.BRACKETS,
            ScadwrightEquationsTokenTypes.L_BRACE to D.BRACES,
            ScadwrightEquationsTokenTypes.R_BRACE to D.BRACES,
            ScadwrightEquationsTokenTypes.COMMA to D.COMMA,
            ScadwrightEquationsTokenTypes.DOT to D.DOT,
        )
    }
}
