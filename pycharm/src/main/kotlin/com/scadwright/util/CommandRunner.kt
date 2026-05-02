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
import com.scadwright.settings.ScadwrightSettings
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
 * Three tricks make the spawned commands actually find `scadwright`
 * and `openscad` even when PyCharm was launched from Finder/Dock
 * (which gives the IDE a minimal PATH that excludes Homebrew, pyenv,
 * project venvs, and `/Applications`):
 *
 * 1. **Project-venv resolution.** If `scadwrightCommand` is a bare
 *    name (e.g. `scadwright`) and `<projectRoot>/.venv/bin/<name>`
 *    exists and is executable, that absolute path wins. Most Python
 *    projects keep their tools in a project-local `.venv/`; the user
 *    activates it manually in their shell, but that activation
 *    doesn't propagate to processes PyCharm spawns.
 *
 * 2. **Login-shell wrap on Unix.** The full command runs via
 *    `$SHELL -l -c '<command line>'` so the user's interactive shell
 *    profile sources its PATH. Windows skips the wrap.
 *
 * 3. **OpenSCAD discovery via $SCADWRIGHT_OPENSCAD.** scadwright's
 *    `preview` and `render` subcommands shell out to OpenSCAD
 *    internally. On macOS, OpenSCAD installs as an `.app` bundle
 *    (`/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD`) which is
 *    never on any PATH. We detect the binary in the user-configured
 *    setting, then on PATH, then in the standard `.app` location, and
 *    pass it through to the subprocess as `$SCADWRIGHT_OPENSCAD`.
 *    The CLI honours that variable (per `scadwright --help`), so the
 *    child OpenSCAD invocation finds the right binary without
 *    requiring the user to add anything to their shell PATH.
 */
object CommandRunner {
    private const val TOOL_WINDOW_ID = "SCADwright"

    /** Common macOS OpenSCAD locations checked when the user's
     *  PATH-based lookup fails. Most users on macOS install OpenSCAD
     *  via the GUI installer, which puts it in `/Applications/`
     *  rather than anywhere PATH-discoverable. */
    private val MAC_OPENSCAD_LOCATIONS = listOf(
        "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
        "/Applications/OpenSCAD-2021.01.app/Contents/MacOS/OpenSCAD",
    )

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
            // Inject SCADWRIGHT_OPENSCAD pointing at the resolved
            // OpenSCAD binary so scadwright's preview/render
            // subcommands find it without relying on PATH (which on
            // macOS GUI-launched IDEs doesn't include /Applications).
            val openscadPath = resolveOpenScad()
            if (openscadPath != null) {
                environment["SCADWRIGHT_OPENSCAD"] = openscadPath
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
     * Resolve a usable path that scadwright should hand to its
     * `--openscad` (or `$SCADWRIGHT_OPENSCAD`) lookup. Order:
     * configured setting (if absolute and exists), login-shell PATH
     * lookup, the standard macOS `.app` bundle.
     *
     * On macOS, when the answer is a `.app` bundle's inner binary,
     * [appBundleLauncherFor] swaps in a tiny shell-script wrapper
     * that goes through `open -a` instead of executing the binary
     * directly. Bypassing Launch Services that way is what causes
     * OpenSCAD's GPU/Metal context to fall back to software
     * rendering (the laggy zoom symptom) — going through `open` gives
     * the app its full launch-time setup.
     *
     * The result is set as `$SCADWRIGHT_OPENSCAD` on every spawned
     * scadwright process; the CLI consults that variable before
     * falling back to its own PATH search, which means the child
     * OpenSCAD invocation works even when PyCharm's spawned
     * environment knows nothing about Homebrew or `/Applications/`.
     */
    private fun resolveOpenScad(): String? {
        val configured = ScadwrightSettings.getInstance().openscadCommand.trim()

        // 1. User-configured absolute path that actually exists wins.
        if (configured.isNotEmpty() && (configured.contains('/') || configured.contains('\\'))) {
            val asFile = File(configured)
            if (asFile.canExecute()) {
                return appBundleLauncherFor(asFile.absolutePath) ?: asFile.absolutePath
            }
        }

        // 2. Try the user's interactive shell — covers Homebrew,
        // pyenv, and any custom PATH setup. Cheap subprocess.
        whichInLoginShell(configured.ifEmpty { "openscad" })?.let { found ->
            return appBundleLauncherFor(found) ?: found
        }

        // 3. macOS .app bundle locations. The GUI installer puts
        // OpenSCAD here; nothing on PATH points at it.
        if (!isWindows()) {
            for (path in MAC_OPENSCAD_LOCATIONS) {
                if (File(path).canExecute()) {
                    return appBundleLauncherFor(path) ?: path
                }
            }
        }

        return null
    }

    /**
     * If [binaryPath] points into a macOS `.app` bundle's
     * `Contents/MacOS/` directory, return the path to a
     * bundle-launching wrapper script (extracting/regenerating it
     * lazily). Otherwise return null and the caller uses [binaryPath]
     * directly.
     *
     * Why the wrapper: a macOS GUI app launched via its inner binary
     * skips Launch Services, which means the process doesn't get the
     * proper GPU/Metal context, the proper window-server registration,
     * or the proper sandbox setup. Symptoms include laggy 3D viewports
     * (software-rendering fallback) and missing GPU acceleration.
     * Routing the launch through `open -a` fixes all three.
     *
     * The wrapper lives under `~/.cache/scadwright-pycharm/`. Each
     * invocation rewrites it so an upgrade that changes the wrapper
     * shape takes effect on next click without manual cleanup.
     */
    private fun appBundleLauncherFor(binaryPath: String): String? {
        if (isWindows()) return null
        val appBundleRegex = Regex("^(.+\\.app)/Contents/MacOS/[^/]+$")
        val match = appBundleRegex.find(binaryPath) ?: return null
        val appPath = match.groupValues[1]
        val cacheDir = File(System.getProperty("user.home"), ".cache/scadwright-pycharm")
        cacheDir.mkdirs()
        val wrapper = File(cacheDir, "openscad-launch.sh")

        // The wrapper goes through `open` so the app gets a full
        // Launch Services launch (proper GPU + sandbox + window
        // registration). `-W` blocks until the app exits — which
        // matters for headless render runs where scadwright depends
        // on the openscad subprocess having actually finished writing
        // the STL before scadwright itself returns. Preview runs
        // block too, but the user typically wants the console to
        // stay "running" until they close OpenSCAD anyway.
        val script = """#!/bin/sh
            |# Generated by scadwright-pycharm. Routes openscad
            |# invocations through Launch Services so the app gets
            |# its proper GPU/Metal/sandbox setup. Without this, the
            |# 3D viewport falls back to software rendering and the
            |# UI is noticeably laggy.
            |exec /usr/bin/open -W -a "$appPath" --args "${'$'}@"
            |""".trimMargin()

        try {
            wrapper.writeText(script)
            wrapper.setExecutable(true)
        } catch (_: Exception) {
            return null
        }
        return wrapper.absolutePath
    }

    /**
     * Run `which <name>` inside the user's login shell to discover an
     * absolute path the way the user's interactive terminal would.
     * Returns null if the binary isn't on the login-shell PATH.
     */
    private fun whichInLoginShell(name: String): String? {
        if (name.isBlank()) return null
        if (isWindows()) return null
        val shell = System.getenv("SHELL") ?: "/bin/sh"
        val safeName = name.replace("'", "'\\''")
        return try {
            val proc = ProcessBuilder(shell, "-l", "-c", "command -v '$safeName'")
                .redirectErrorStream(false)
                .start()
            val line = proc.inputStream.bufferedReader().readLine()?.trim().orEmpty()
            proc.waitFor()
            if (line.isNotEmpty() && File(line).canExecute()) line else null
        } catch (_: Exception) {
            null
        }
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
