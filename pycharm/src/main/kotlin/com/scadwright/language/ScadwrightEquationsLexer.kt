package com.scadwright.language

import com.intellij.lexer.LexerBase
import com.intellij.psi.TokenType
import com.intellij.psi.tree.IElementType

// Hand-rolled lexer for the equations DSL. Avoids a JFlex dependency:
// the grammar is small (numbers, identifiers, operators, strings,
// comments) and a state-machine in Kotlin is comparable in size to a
// .flex file once you count generated boilerplate.
class ScadwrightEquationsLexer : LexerBase() {

    private var buffer: CharSequence = ""
    private var endOffset: Int = 0
    private var startOffset: Int = 0

    private var tokenStart: Int = 0
    private var tokenEnd: Int = 0
    private var tokenType: IElementType? = null

    override fun start(buffer: CharSequence, startOffset: Int, endOffset: Int, initialState: Int) {
        this.buffer = buffer
        this.startOffset = startOffset
        this.endOffset = endOffset
        this.tokenStart = startOffset
        this.tokenEnd = startOffset
        this.tokenType = null
        advance()
    }

    override fun getState(): Int = 0
    override fun getTokenType(): IElementType? = tokenType
    override fun getTokenStart(): Int = tokenStart
    override fun getTokenEnd(): Int = tokenEnd
    override fun getBufferSequence(): CharSequence = buffer
    override fun getBufferEnd(): Int = endOffset

    override fun advance() {
        tokenStart = tokenEnd
        if (tokenStart >= endOffset) {
            tokenType = null
            return
        }
        val c = buffer[tokenStart]
        when {
            c.isWhitespace() -> readWhitespace()
            c == '#' -> readLineComment()
            c == '"' || c == '\'' -> readString(c)
            c.isDigit() -> readNumber()
            c == '.' && tokenStart + 1 < endOffset && buffer[tokenStart + 1].isDigit() -> readNumber()
            isIdentifierStart(c) -> readIdentifier()
            c == '?' -> readOptionalSigil()
            else -> readOperatorOrPunctuation()
        }
    }

    // --- token readers ---------------------------------------------------

    private fun readWhitespace() {
        var i = tokenStart
        while (i < endOffset && buffer[i].isWhitespace()) i++
        tokenEnd = i
        tokenType = TokenType.WHITE_SPACE
    }

    private fun readLineComment() {
        var i = tokenStart
        while (i < endOffset && buffer[i] != '\n') i++
        tokenEnd = i
        tokenType = ScadwrightEquationsTokenTypes.LINE_COMMENT
    }

    private fun readString(quote: Char) {
        var i = tokenStart + 1
        while (i < endOffset) {
            val ch = buffer[i]
            if (ch == '\\' && i + 1 < endOffset) {
                i += 2
                continue
            }
            if (ch == quote) {
                i++
                break
            }
            if (ch == '\n') break
            i++
        }
        tokenEnd = i
        tokenType = ScadwrightEquationsTokenTypes.STRING
    }

    private fun readNumber() {
        var i = tokenStart
        var sawDot = false
        var sawExp = false

        // integer / leading dot part
        if (buffer[i] == '.') {
            sawDot = true
            i++
            while (i < endOffset && buffer[i].isDigit()) i++
        } else {
            while (i < endOffset && buffer[i].isDigit()) i++
            if (i < endOffset && buffer[i] == '.') {
                sawDot = true
                i++
                while (i < endOffset && buffer[i].isDigit()) i++
            }
        }
        // optional exponent
        if (i < endOffset && (buffer[i] == 'e' || buffer[i] == 'E')) {
            val expStart = i
            i++
            if (i < endOffset && (buffer[i] == '+' || buffer[i] == '-')) i++
            val digitsBefore = i
            while (i < endOffset && buffer[i].isDigit()) i++
            if (i == digitsBefore) {
                // no exponent digits — back up, treat as identifier-ish boundary
                i = expStart
            } else {
                sawExp = true
            }
        }

        // suppress unused warnings — these flags exist for clarity
        @Suppress("UNUSED_VARIABLE") val _dot = sawDot
        @Suppress("UNUSED_VARIABLE") val _exp = sawExp

        tokenEnd = i
        tokenType = ScadwrightEquationsTokenTypes.NUMBER
    }

    private fun readIdentifier() {
        var i = tokenStart + 1
        while (i < endOffset && isIdentifierPart(buffer[i])) i++
        tokenEnd = i
        val text = buffer.subSequence(tokenStart, tokenEnd).toString()
        tokenType = classifyIdentifier(text)
    }

    private fun classifyIdentifier(text: String): IElementType = when (text) {
        in Vocabulary.keywords -> ScadwrightEquationsTokenTypes.KEYWORD
        in Vocabulary.constants -> ScadwrightEquationsTokenTypes.CONSTANT
        in Vocabulary.typeNames -> ScadwrightEquationsTokenTypes.TYPE_NAME
        in Vocabulary.mathFunctions -> ScadwrightEquationsTokenTypes.MATH_FUNCTION
        in Vocabulary.builtinFunctions -> ScadwrightEquationsTokenTypes.BUILTIN_FUNCTION
        in Vocabulary.cardinalityHelpers -> ScadwrightEquationsTokenTypes.CARDINALITY_HELPER
        else -> ScadwrightEquationsTokenTypes.IDENTIFIER
    }

    private fun readOptionalSigil() {
        // `?` on its own is a sigil only when followed by an identifier
        // start, mirroring the VSCode grammar's `\\?(?=[a-zA-Z_])`.
        val next = if (tokenStart + 1 < endOffset) buffer[tokenStart + 1] else ' '
        tokenEnd = tokenStart + 1
        tokenType = if (isIdentifierStart(next)) {
            ScadwrightEquationsTokenTypes.OPTIONAL_SIGIL
        } else {
            TokenType.BAD_CHARACTER
        }
    }

    private fun readOperatorOrPunctuation() {
        val c = buffer[tokenStart]
        val next = if (tokenStart + 1 < endOffset) buffer[tokenStart + 1] else ' '
        when (c) {
            '=' -> {
                if (next == '=') two(ScadwrightEquationsTokenTypes.COMPARE_OP)
                else one(ScadwrightEquationsTokenTypes.EQUATION_OP)
            }
            '!' -> {
                if (next == '=') two(ScadwrightEquationsTokenTypes.COMPARE_OP)
                else one(TokenType.BAD_CHARACTER)
            }
            '<', '>' -> {
                if (next == '=') two(ScadwrightEquationsTokenTypes.COMPARE_OP)
                else one(ScadwrightEquationsTokenTypes.COMPARE_OP)
            }
            '+' -> one(ScadwrightEquationsTokenTypes.ARITH_OP)
            '-' -> one(ScadwrightEquationsTokenTypes.ARITH_OP)
            '*' -> {
                if (next == '*') two(ScadwrightEquationsTokenTypes.ARITH_OP)
                else one(ScadwrightEquationsTokenTypes.ARITH_OP)
            }
            '/' -> {
                if (next == '/') two(ScadwrightEquationsTokenTypes.ARITH_OP)
                else one(ScadwrightEquationsTokenTypes.ARITH_OP)
            }
            '%' -> one(ScadwrightEquationsTokenTypes.ARITH_OP)
            '(' -> one(ScadwrightEquationsTokenTypes.L_PAREN)
            ')' -> one(ScadwrightEquationsTokenTypes.R_PAREN)
            '[' -> one(ScadwrightEquationsTokenTypes.L_BRACKET)
            ']' -> one(ScadwrightEquationsTokenTypes.R_BRACKET)
            '{' -> one(ScadwrightEquationsTokenTypes.L_BRACE)
            '}' -> one(ScadwrightEquationsTokenTypes.R_BRACE)
            ',' -> one(ScadwrightEquationsTokenTypes.COMMA)
            '.' -> one(ScadwrightEquationsTokenTypes.DOT)
            ':' -> one(ScadwrightEquationsTokenTypes.TYPE_COLON)
            else -> one(TokenType.BAD_CHARACTER)
        }
    }

    private fun one(type: IElementType) {
        tokenEnd = tokenStart + 1
        tokenType = type
    }

    private fun two(type: IElementType) {
        tokenEnd = tokenStart + 2
        tokenType = type
    }

    private fun isIdentifierStart(c: Char): Boolean = c.isLetter() || c == '_'
    private fun isIdentifierPart(c: Char): Boolean = c.isLetterOrDigit() || c == '_'
}
