package com.scadwright.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.scadwright.util.FileDetector

/**
 * Kill any running OpenSCAD process. Handy when a preview window is
 * stuck (CGAL render hung, modal dialog open with no model) and the
 * usual close-window route isn't responding.
 *
 * Fire-and-forget: spawns the platform's process-killer and returns
 * immediately. No console output, no error dialog if there's no
 * matching process (the typical "kill a thing that wasn't there"
 * case is harmless).
 */
class KillAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val cmd = if (System.getProperty("os.name").lowercase().contains("win")) {
            arrayOf("taskkill", "/F", "/IM", "openscad.exe")
        } else {
            arrayOf("pkill", "-f", "openscad")
        }
        try {
            ProcessBuilder(*cmd).redirectErrorStream(true).start()
        } catch (_: Exception) {
            // Best effort: if the platform doesn't have pkill / taskkill on
            // PATH, there's nothing useful to surface. The user can fall
            // back to their OS-level process tools.
        }
    }

    override fun update(e: AnActionEvent) {
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)
        e.presentation.isEnabledAndVisible = FileDetector.isScadwrightFile(file)
    }

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
