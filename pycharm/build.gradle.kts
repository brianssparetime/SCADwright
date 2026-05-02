plugins {
    id("org.jetbrains.kotlin.jvm") version "1.9.22"
    id("org.jetbrains.intellij") version "1.17.4"
}

group = "com.scadwright"
version = "0.2.0"

repositories {
    mavenCentral()
}

// Target JDK 17 — the IntelliJ Platform 2024.1+ requires it. The
// Gradle toolchain will pick up the JDK pointed at by JAVA_HOME or
// auto-provision via Foojay.
kotlin {
    jvmToolchain(17)
}

intellij {
    // PyCharm Community 2024.1. We depend on the bundled Python
    // plugin (PythonCore) for PSI-aware features in Phase 2; Phase 1
    // doesn't strictly need it but declaring early keeps the build
    // honest about the dependency.
    version.set("2024.1")
    type.set("PC")
    plugins.set(listOf("PythonCore"))
}

tasks {
    patchPluginXml {
        // sinceBuild covers PyCharm 2024.1+. Phase 1 only uses stable
        // platform APIs (AnAction, GeneralCommandLine, ConsoleView,
        // BoundConfigurable, PersistentStateComponent), so we widen
        // untilBuild aggressively to cover current and near-future
        // PyCharm releases without forcing a rebuild every six months.
        // Bump if a future IntelliJ Platform version breaks something.
        sinceBuild.set("241")
        untilBuild.set("263.*")
    }

    // Default test task setup — no tests yet, but having the toolchain
    // pinned avoids surprises when we do add a test class.
    test {
        useJUnitPlatform()
    }

    // The bundled Java compiler should target JDK 17 even if the host
    // toolchain is newer; lock the bytecode level explicitly.
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }
}
