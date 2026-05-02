package com.scadwright.actions

import com.intellij.openapi.vfs.VirtualFile
import com.scadwright.settings.ScadwrightSettings

/**
 * Editor-toolbar action that runs `scadwright render <file.py>`. The
 * CLI builds to a temp `.scad` and then invokes OpenSCAD headlessly
 * to produce an STL. Output (build messages and OpenSCAD's render
 * progress) streams into the SCADwright tool window.
 */
class RenderAction : BaseScadwrightAction() {
    override val title: String = "SCADwright: Render"

    override fun buildCommand(file: VirtualFile, settings: ScadwrightSettings): List<String> = buildList {
        add(settings.scadwrightCommand)
        add("render")
        add(file.path)
        if (settings.variant.isNotBlank()) {
            add("--variant")
            add(settings.variant)
        }
    }
}
