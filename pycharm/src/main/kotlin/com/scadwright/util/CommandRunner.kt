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
 *
 * Two extra tricks make the spawned commands actually find
 * `scadwright` and `openscad` even when PyCharm was launched from
 * Finder/Dock (which gives the IDE a minimal PATH):
 *
 * 1. **Project-venv resolution.** If the configured command is a
 *    bare name (e.g. `scadwright`) and `<projectRoot>/.venv/bin/<name>`
 *    exists and is executable, that absolute path wins. Most Python
 *    projects keep their tools in a project-local `.venv/`; the user
 *    activates it manually in their shell, but that activation
 *    doesn't propagate to processes PyCharm spawns.
 *
 * 2. **Login-shell wrap on Unix.** The full command runs via
 *    `$SHELL -l -c '<command line>'`, so the user's interactive shell
 *    profile (`.zshrc` / `.bash_profile`) sources its PATH. This is
 *    what makes `openscad` resolve when it's on Homebrew's
 *    `/opt/homebrew/bin` (a path PyCharm itself doesn't inherit from
 *    Finder). Windows skips the wrap; PATH inheritance there works
 *    differently and doesn't need it.
 */
object CommandRunner {
    private const val TOOL_WINDOW_ID = "SCADwright"

    fun run(
        project: Project,
        title: String,
        command: List<String>,
        workDir: String? = null,
    ) {
        val resolved = resolveAndWrap(project, command)
        val cmd = GeneralCommandLine(resolved).apply {
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
                "Failed to start command: ${e.message ?: "unknown error"}\n\n" +
                    "Resolved command:\n${resolved.joinToString(" ")}\n\n" +
                    "Original command:\n${command.joinToString(" ")}\n\n" +
                    "If `scadwright` lives in a non-standard location, set its " +
                    "absolute path in Settings → Tools → SCADwright.",
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

    /**
     * Apply the project-venv resolution and the login-shell wrap, in
     * that order. The first element of [command] is the executable;
     * arguments after it pass through unchanged.
     */
    private fun resolveAndWrap(project: Project, command: List<String>): List<String> {
        if (command.isEmpty()) return command

        val resolvedExe = resolveExecutable(project, command[0])
        val resolvedCommand = listOf(resolvedExe) + command.drop(1)

        return if (isWindows()) {
            resolvedCommand
        } else {
            wrapInLoginShell(resolvedCommand)
        }
    }

    /**
     * If [exe] is a bare name (no path separator), look for
     * `<projectRoot>/.venv/bin/<exe>` and substitute the absolute path
     * if it exists. Otherwise return [exe] unchanged so PATH lookup
     * (or the user's absolute path setting) takes over.
     */
    private fun resolveExecutable(project: Project, exe: String): String {
        if (exe.contains('/') || exe.contains('\\')) return exe
        val basePath = project.basePath ?: return exe
        val venvBin = File("$basePath/.venv/bin/$exe")
        return if (venvBin.canExecute()) venvBin.absolutePath else exe
    }

    /**
     * Wrap the command in a login shell so the spawned process
     * inherits the PATH from the user's shell rc. Each argument is
     * single-quoted; embedded single quotes are escaped via the
     * standard `'\''` idiom so paths with spaces or punctuation pass
     * through unmodified.
     */
    private fun wrapInLoginShell(command: List<String>): List<String> {
        val shell = System.getenv("SHELL") ?: "/bin/sh"
        val quoted = command.joinToString(" ") { arg ->
            "'" + arg.replace("'", "'\\''") + "'"
        }
        return listOf(shell, "-l", "-c", quoted)
    }

    private fun isWindows(): Boolean =
        System.getProperty("os.name").lowercase().contains("win")
}
