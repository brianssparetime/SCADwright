package com.scadwright.util

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.filters.TextConsoleBuilderFactory
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.ui.ConsoleView
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.wm.ToolWindowAnchor
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.openapi.wm.RegisterToolWindowTask
import com.intellij.ui.content.ContentFactory
import java.io.File
import java.nio.charset.StandardCharsets

/**
 * Runs an external command and streams its output to a "SCADwright"
 * tool window at the bottom of the IDE. Each invocation appends a
 * fresh tab to the window so consecutive Preview / Render runs stay
 * inspectable side by side.
 *
 * Centralizes the GeneralCommandLine + OSProcessHandler + ConsoleView
 * wiring so the action classes stay focused on building command
 * vectors. Error dialogs surface at the front of the IDE if the
 * process can't even be started (e.g. `scadwright` not on PATH);
 * runtime errors from the command itself appear in the console.
 */
object CommandRunner {
    private const val TOOL_WINDOW_ID = "SCADwright"

    fun run(
        project: Project,
        title: String,
        command: List<String>,
        workDir: String? = null,
    ) {
        val cmd = GeneralCommandLine(command).apply {
            charset = StandardCharsets.UTF_8
            if (workDir != null) {
                setWorkDirectory(File(workDir))
            }
        }

        val handler = try {
            OSProcessHandler(cmd)
        } catch (e: ExecutionException) {
            Messages.showErrorDialog(
                project,
                "Failed to start command: ${e.message ?: "unknown error"}\n\nCommand: ${command.joinToString(" ")}",
                title,
            )
            return
        }

        val console: ConsoleView = TextConsoleBuilderFactory.getInstance()
            .createBuilder(project)
            .console
        console.attachToProcess(handler)

        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow(TOOL_WINDOW_ID)
            ?: ToolWindowManager.getInstance(project).registerToolWindow(
                RegisterToolWindowTask(
                    id = TOOL_WINDOW_ID,
                    anchor = ToolWindowAnchor.BOTTOM,
                    canCloseContent = true,
                )
            )

        val content = ContentFactory.getInstance().createContent(
            console.component, title, false,
        )
        toolWindow.contentManager.addContent(content)
        toolWindow.contentManager.setSelectedContent(content)
        toolWindow.show()

        handler.startNotify()
    }
}
