package com.scadwright.language

import com.intellij.lang.ASTNode
import com.intellij.lang.ParserDefinition
import com.intellij.lang.PsiParser
import com.intellij.lexer.Lexer
import com.intellij.openapi.project.Project
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.TokenType
import com.intellij.psi.tree.IFileElementType
import com.intellij.psi.tree.TokenSet

// Stub parser: produces a flat PSI tree where every lexer token sits
// directly under the file root. Highlighting and completion only need
// token-level information, so building any deeper structure would be
// dead weight. If we ever want navigation between equation references
// we'll grow this then.
class ScadwrightEquationsParserDefinition : ParserDefinition {

    override fun createLexer(project: Project?): Lexer = ScadwrightEquationsLexer()

    override fun createParser(project: Project?): PsiParser = PsiParser { root, builder ->
        val rootMarker = builder.mark()
        while (!builder.eof()) {
            builder.advanceLexer()
        }
        rootMarker.done(root)
        builder.treeBuilt
    }

    override fun getFileNodeType(): IFileElementType = ScadwrightEquationsTokenTypes.FILE
    override fun getCommentTokens(): TokenSet = COMMENTS
    override fun getStringLiteralElements(): TokenSet = STRINGS
    override fun getWhitespaceTokens(): TokenSet = WHITESPACE

    override fun createElement(node: ASTNode): PsiElement = LeafPlaceholder(node)
    override fun createFile(viewProvider: FileViewProvider): PsiFile =
        ScadwrightEquationsFile(viewProvider)

    // The platform never invokes createElement for our element types
    // (we have none beyond the file root) but ParserDefinition requires
    // the override. Anything that does end up here gets wrapped in a
    // tiny adapter so debugging shows the node text.
    private class LeafPlaceholder(node: ASTNode) :
        com.intellij.extapi.psi.ASTWrapperPsiElement(node)

    companion object {
        private val WHITESPACE = TokenSet.create(TokenType.WHITE_SPACE)
        private val COMMENTS = TokenSet.create(ScadwrightEquationsTokenTypes.LINE_COMMENT)
        private val STRINGS = TokenSet.create(ScadwrightEquationsTokenTypes.STRING)
    }
}
