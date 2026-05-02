package com.scadwright.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.vfs.VirtualFile
import com.scadwright.settings.ScadwrightSettings
import com.scadwright.util.CommandRunner
import com.scadwright.util.FileDetector

/**
 * Shared scaffold for the Preview / Render actions: gate visibility
 * to scadwright Python files, optionally save before running, build
 * the command vector via [buildCommand], delegate execution to
 * [CommandRunner].
 *
 * Kill is a separate one-off; it doesn't take a file argument and
 * doesn't stream into the SCADwright tool window, so it sits outside
 * this base class.
 */
abstract class BaseScadwrightAction : AnAction() {
    /** Human-readable title shown on the SCADwright tool window tab. */
    abstract val title: String

    /** Build the argv to invoke for the active file + current settings. */
    abstract fun buildCommand(file: VirtualFile, settings: ScadwrightSettings): List<String>

    final override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return
        val settings = ScadwrightSettings.getInstance()

        if (settings.saveBeforeBuild) {
            FileDocumentManager.getInstance().saveAllDocuments()
        }

        CommandRunner.run(
            project = project,
            title = title,
            command = buildCommand(file, settings),
            workDir = file.parent?.path,
        )
    }

    final override fun update(e: AnActionEvent) {
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        e.presentation.isEnabledAndVisible = FileDetector.isScadwrightFile(file)
    }

    /**
     * Required since 2022.3: declare which thread `update()` runs on.
     * Background is correct for us because [FileDetector] reads file
     * contents.
     */
    final override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
