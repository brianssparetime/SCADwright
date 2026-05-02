package com.scadwright.language

import com.intellij.psi.tree.IElementType
import com.intellij.psi.tree.IFileElementType

class ScadwrightEquationsTokenType(debugName: String) :
    IElementType(debugName, ScadwrightEquationsLanguage)

object ScadwrightEquationsTokenTypes {
    val FILE: IFileElementType = IFileElementType(ScadwrightEquationsLanguage)

    val LINE_COMMENT = ScadwrightEquationsTokenType("LINE_COMMENT")
    val NUMBER = ScadwrightEquationsTokenType("NUMBER")
    val STRING = ScadwrightEquationsTokenType("STRING")

    val IDENTIFIER = ScadwrightEquationsTokenType("IDENTIFIER")
    val KEYWORD = ScadwrightEquationsTokenType("KEYWORD")
    val MATH_FUNCTION = ScadwrightEquationsTokenType("MATH_FUNCTION")
    val BUILTIN_FUNCTION = ScadwrightEquationsTokenType("BUILTIN_FUNCTION")
    val CARDINALITY_HELPER = ScadwrightEquationsTokenType("CARDINALITY_HELPER")
    val TYPE_NAME = ScadwrightEquationsTokenType("TYPE_NAME")
    val CONSTANT = ScadwrightEquationsTokenType("CONSTANT")

    val OPTIONAL_SIGIL = ScadwrightEquationsTokenType("OPTIONAL_SIGIL")
    val TYPE_COLON = ScadwrightEquationsTokenType("TYPE_COLON")
    val EQUATION_OP = ScadwrightEquationsTokenType("EQUATION_OP")
    val COMPARE_OP = ScadwrightEquationsTokenType("COMPARE_OP")
    val ARITH_OP = ScadwrightEquationsTokenType("ARITH_OP")

    val L_PAREN = ScadwrightEquationsTokenType("L_PAREN")
    val R_PAREN = ScadwrightEquationsTokenType("R_PAREN")
    val L_BRACKET = ScadwrightEquationsTokenType("L_BRACKET")
    val R_BRACKET = ScadwrightEquationsTokenType("R_BRACKET")
    val L_BRACE = ScadwrightEquationsTokenType("L_BRACE")
    val R_BRACE = ScadwrightEquationsTokenType("R_BRACE")
    val COMMA = ScadwrightEquationsTokenType("COMMA")
    val DOT = ScadwrightEquationsTokenType("DOT")
}
