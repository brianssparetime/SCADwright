package com.scadwright.settings

import com.intellij.openapi.options.BoundConfigurable
import com.intellij.openapi.ui.DialogPanel
import com.intellij.ui.dsl.builder.COLUMNS_LARGE
import com.intellij.ui.dsl.builder.COLUMNS_MEDIUM
import com.intellij.ui.dsl.builder.bindSelected
import com.intellij.ui.dsl.builder.bindText
import com.intellij.ui.dsl.builder.columns
import com.intellij.ui.dsl.builder.panel

/**
 * The Settings → Tools → SCADwright pane. Built with Kotlin UI DSL v2;
 * each row binds directly to a property on the [ScadwrightSettings]
 * service so the form's apply/reset/state-tracking is automatic.
 */
class ScadwrightSettingsConfigurable : BoundConfigurable("SCADwright") {
    override fun createPanel(): DialogPanel {
        val settings = ScadwrightSettings.getInstance()
        return panel {
            row("scadwright command:") {
                textField()
                    .bindText(settings::scadwrightCommand)
                    .columns(COLUMNS_LARGE)
                    .comment("Path or command to invoke the SCADwright CLI. Use a full path if it isn't on PATH.")
            }
            row("openscad command:") {
                textField()
                    .bindText(settings::openscadCommand)
                    .columns(COLUMNS_LARGE)
                    .comment("Path or command to invoke OpenSCAD.")
            }
            row("Variant:") {
                textField()
                    .bindText(settings::variant)
                    .columns(COLUMNS_MEDIUM)
                    .comment("Variant passed to <code>scadwright build --variant=…</code>. Empty means no flag.")
            }
            row {
                checkBox("Save active file before invoking scadwright build")
                    .bindSelected(settings::saveBeforeBuild)
            }
        }
    }
}
