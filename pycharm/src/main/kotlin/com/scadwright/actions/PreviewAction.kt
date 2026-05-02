package com.scadwright.actions

import com.intellij.openapi.vfs.VirtualFile
import com.scadwright.settings.ScadwrightSettings

/**
 * Editor-toolbar action that runs `scadwright preview <file.py>`.
 * The CLI builds the script's `MODEL` to a stable temp `.scad`
 * (keyed on script + variant) and launches OpenSCAD on it. Clicking
 * Preview again overwrites the same temp file so an already-open
 * OpenSCAD window auto-reloads.
 */
class PreviewAction : BaseScadwrightAction() {
    override val title: String = "SCADwright: Preview"

    override fun buildCommand(file: VirtualFile, settings: ScadwrightSettings): List<String> = buildList {
        add(settings.scadwrightCommand)
        add("preview")
        add(file.path)
        if (settings.variant.isNotBlank()) {
            add("--variant")
            add(settings.variant)
        }
    }
}
