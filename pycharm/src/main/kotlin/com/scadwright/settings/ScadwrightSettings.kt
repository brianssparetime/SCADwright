package com.scadwright.settings

import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.intellij.util.xmlb.XmlSerializerUtil

/**
 * Persistent settings for the SCADwright plugin. Mirrors the four
 * configurables exposed by the VSCode extension so behavior matches
 * across editors.
 */
@Service(Service.Level.APP)
@State(name = "ScadwrightSettings", storages = [Storage("scadwright.xml")])
class ScadwrightSettings : PersistentStateComponent<ScadwrightSettings> {
    /** Path or command to invoke for the SCADwright CLI. */
    var scadwrightCommand: String = "scadwright"

    /** Path or command to invoke OpenSCAD. */
    var openscadCommand: String = "openscad"

    /** Variant passed to `scadwright build --variant=…`. Empty means no flag. */
    var variant: String = ""

    /** Save the active file before invoking `scadwright build`. */
    var saveBeforeBuild: Boolean = true

    override fun getState(): ScadwrightSettings = this

    override fun loadState(state: ScadwrightSettings) {
        XmlSerializerUtil.copyBean(state, this)
    }

    companion object {
        fun getInstance(): ScadwrightSettings = service()
    }
}
