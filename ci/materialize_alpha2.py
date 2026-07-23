from pathlib import Path

ROOT = Path("project")

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)

write('app/build.gradle.kts', 'plugins {\n    id("com.android.application")\n    id("org.jetbrains.kotlin.android")\n    id("org.jetbrains.kotlin.plugin.compose")\n}\n\nandroid {\n    namespace = "com.sharkkernel.manager"\n    compileSdk = 35\n\n    defaultConfig {\n        applicationId = "com.sharkkernel.manager"\n        minSdk = 28\n        targetSdk = 33\n        versionCode = 1001\n        versionName = "1.0.0-alpha2"\n    }\n\n    signingConfigs {\n        getByName("debug") {\n            storeFile = rootProject.file("debug/shark-debug.keystore")\n            storePassword = "sharkdebug"\n            keyAlias = "sharkdebug"\n            keyPassword = "sharkdebug"\n        }\n    }\n\n    buildTypes {\n        release {\n            isMinifyEnabled = false\n            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")\n        }\n    }\n\n    compileOptions {\n        sourceCompatibility = JavaVersion.VERSION_17\n        targetCompatibility = JavaVersion.VERSION_17\n    }\n    kotlinOptions { jvmTarget = "17" }\n    buildFeatures { compose = true }\n    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }\n}\n\ndependencies {\n    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")\n    implementation(composeBom)\n    androidTestImplementation(composeBom)\n\n    implementation("androidx.core:core-ktx:1.15.0")\n    implementation("androidx.activity:activity-compose:1.10.0")\n    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")\n    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")\n    implementation("androidx.navigation:navigation-compose:2.8.5")\n    implementation("androidx.compose.ui:ui")\n    implementation("androidx.compose.ui:ui-tooling-preview")\n    implementation("androidx.compose.foundation:foundation")\n    implementation("androidx.compose.material3:material3")\n    implementation("androidx.compose.material:material-icons-core")\n    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")\n    implementation("com.github.topjohnwu.libsu:core:6.0.0")\n    debugImplementation("androidx.compose.ui:ui-tooling")\n}\n')

write('settings.gradle.kts', 'pluginManagement {\n    repositories {\n        google()\n        mavenCentral()\n        gradlePluginPortal()\n    }\n}\ndependencyResolutionManagement {\n    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)\n    repositories {\n        google()\n        mavenCentral()\n        maven("https://jitpack.io")\n    }\n}\nrootProject.name = "SharkManager"\ninclude(":app")\n')

write('app/src/main/java/com/sharkkernel/manager/core/RootShell.kt', 'package com.sharkkernel.manager.core\n\nimport com.topjohnwu.superuser.Shell\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.withContext\n\n/**\n * Shared root executor backed by libsu.\n *\n * KernelSU/Magisk expose root through an su shell. Keeping one libsu shell avoids\n * racing several short-lived `su -c` processes while the permission dialog is\n * still being handled.\n */\nobject RootShell {\n    data class Result(val code: Int, val out: String, val err: String) {\n        val ok: Boolean get() = code == 0\n    }\n\n    data class Probe(\n        val granted: Boolean,\n        val detail: String\n    )\n\n    suspend fun exec(command: String): Result = withContext(Dispatchers.IO) {\n        try {\n            val result = Shell.cmd(command).exec()\n            Result(\n                code = result.code,\n                out = result.out.joinToString("\\n").trim(),\n                err = result.err.joinToString("\\n").trim()\n            )\n        } catch (t: Throwable) {\n            Result(-1, "", t.message.orEmpty())\n        }\n    }\n\n    suspend fun probe(): Probe = withContext(Dispatchers.IO) {\n        try {\n            val shell = Shell.getShell()\n            if (!shell.isRoot) {\n                return@withContext Probe(false, "su shell sem UID 0")\n            }\n            val result = Shell.cmd("id -u").exec()\n            val uid = result.out.firstOrNull()?.trim().orEmpty()\n            if (result.isSuccess && uid == "0") {\n                Probe(true, "KernelSU/libsu: UID 0")\n            } else {\n                val reason = result.err.joinToString(" ").trim().ifEmpty {\n                    "id -u retornou \'${uid.ifEmpty { "sem saída" }}\' (code=${result.code})"\n                }\n                Probe(false, reason)\n            }\n        } catch (t: Throwable) {\n            Probe(false, t.message ?: t.javaClass.simpleName)\n        }\n    }\n\n    suspend fun granted(): Boolean = probe().granted\n\n    fun q(value: String): String = "\'" + value.replace("\'", "\'\\\\\'\'") + "\'"\n}\n')

write('app/src/main/java/com/sharkkernel/manager/data/DeviceRepository.kt', 'package com.sharkkernel.manager.data\n\nimport android.os.Build\nimport android.os.SystemClock\nimport com.sharkkernel.manager.core.RootShell\nimport com.sharkkernel.manager.model.DeviceState\n\nobject DeviceRepository {\n    @Volatile private var cached: DeviceState? = null\n    @Volatile private var cachedAtMs: Long = 0L\n\n    suspend fun read(): DeviceState {\n        val now = SystemClock.elapsedRealtime()\n        cached?.let { state ->\n            // Root grants can change while the app is already open. Never cache a\n            // negative result for long; positive results can be reused safely.\n            val ttl = if (state.root) 30_000L else 1_500L\n            if (now - cachedAtMs < ttl) return state\n        }\n\n        val rootProbe = RootShell.probe()\n        val probe = if (rootProbe.granted) {\n            RootShell.exec("[ -d /sys/kernel/shark_g3d_oc ] || [ -d /sys/kernel/debug/shark_soc ] || [ -d /sys/kernel/fvmap_interface ]")\n        } else null\n        val deviceOk = Build.MODEL.startsWith("SM-S721", true) || Build.DEVICE.equals("r12s", true)\n        val socOk = Build.BOARD.equals("s5e9945", true) || Build.HARDWARE.equals("s5e9945", true)\n        return DeviceState(\n            root = rootProbe.granted,\n            rootDetail = rootProbe.detail,\n            supported = rootProbe.granted && deviceOk && socOk && probe?.ok == true,\n            model = Build.MODEL,\n            device = Build.DEVICE,\n            hardware = Build.HARDWARE,\n            kernel = System.getProperty("os.version").orEmpty()\n        ).also {\n            cached = it\n            cachedAtMs = now\n        }\n    }\n\n    fun invalidateRoot() {\n        cached = null\n        cachedAtMs = 0L\n    }\n}\n')

write('app/src/main/java/com/sharkkernel/manager/ui/screens/DashboardScreen.kt', 'package com.sharkkernel.manager.ui.screens\n\nimport androidx.compose.foundation.layout.*\nimport androidx.compose.foundation.rememberScrollState\nimport androidx.compose.foundation.verticalScroll\nimport androidx.compose.material3.*\nimport androidx.compose.runtime.Composable\nimport androidx.compose.ui.Modifier\nimport androidx.compose.ui.unit.dp\nimport com.sharkkernel.manager.core.Format\nimport com.sharkkernel.manager.model.SharkState\nimport com.sharkkernel.manager.ui.HeroMetric\nimport com.sharkkernel.manager.ui.SharkCard\n\n@Composable fun DashboardScreen(s: SharkState, onRetryRoot: () -> Unit) {\n    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement=Arrangement.spacedBy(14.dp)) {\n        SharkCard("Shark Manager", "${s.device.model} • ${s.device.hardware}") {\n            Text(s.device.kernel, color=MaterialTheme.colorScheme.onSurfaceVariant)\n            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {\n                AssistChip(onClick=if (s.device.root) ({}) else onRetryRoot, label={Text(if(s.device.root) "ROOT OK" else "TENTAR ROOT")})\n                AssistChip(onClick={}, label={Text(if(s.device.supported) "SHARK ACTIVE" else "CHECK")})\n            }\n            if (!s.device.root) {\n                Text("Root não foi obtido: ${s.device.rootDetail.ifBlank { "sem diagnóstico" }}", color=MaterialTheme.colorScheme.error)\n                Text("Toque em TENTAR ROOT para abrir/revalidar a sessão do KernelSU.", color=MaterialTheme.colorScheme.onSurfaceVariant)\n            } else if (!s.device.supported) {\n                Text("Root OK, mas nenhuma interface SharkKernel esperada foi encontrada.", color=MaterialTheme.colorScheme.error)\n            }\n        }\n        s.cpu.forEach { p ->\n            HeroMetric(p.name, microarch(p.name)+" • CPU ${p.cpus}", Format.frequency(p.currentKhz), trailing="${Format.frequency(p.minKhz)} ↔ ${Format.frequency(p.maxKhz)} • ${p.governor}")\n        }\n        Row(Modifier.fillMaxWidth(), horizontalArrangement=Arrangement.spacedBy(12.dp)) {\n            Box(Modifier.weight(1f)) { HeroMetric("G3D", "Xclipse 940", Format.frequency(s.gpu.currentKhz), if(s.gpu.ocEnabled) "OC" else "AUTO") }\n            Box(Modifier.weight(1f)) { HeroMetric("DSU", "Shared fabric", Format.frequency(s.dsu.currentKhz)) }\n        }\n        s.domains.firstOrNull { it.name == "MIF" }?.let { HeroMetric("MIF", "Memory interface", Format.frequency(it.currentKhz), trailing="${Format.frequency(it.minKhz)} ↔ ${Format.frequency(it.maxKhz)}") }\n    }\n}\n\nprivate fun microarch(name:String)=when(name){"CPUCL0"->"Cortex-A520";"CPUCL1L","CPUCL1H"->"Cortex-A720";"CPUCL2"->"Cortex-X4";else->"Exynos CPU"}\n')

p = ROOT / 'app/src/main/java/com/sharkkernel/manager/ui/SharkApp.kt'
s = p.read_text()
s = s.replace('import androidx.compose.material.icons.outlined.*', 'import androidx.compose.material.icons.filled.*')
for a, b in {
    'Icons.Outlined.Dashboard':'Icons.Filled.Home',
    'Icons.Outlined.Memory':'Icons.Filled.List',
    'Icons.Outlined.DeveloperBoard':'Icons.Filled.Star',
    'Icons.Outlined.Hub':'Icons.Filled.Share',
    'Icons.Outlined.ElectricBolt':'Icons.Filled.Star',
    'Icons.Outlined.PictureInPicture':'Icons.Filled.Home',
    'Icons.Outlined.Settings':'Icons.Filled.Settings',
    'Icons.Outlined.Info':'Icons.Filled.Info',
    'Icons.Outlined.Speed':'Icons.Filled.List',
    'Icons.Outlined.Menu':'Icons.Filled.Menu',
    'Icons.Outlined.Refresh':'Icons.Filled.Refresh',
}.items():
    s = s.replace(a, b)
s = s.replace('composable("dashboard"){DashboardScreen(state)}', 'composable("dashboard"){DashboardScreen(state, vm::retryRoot)}')
p.write_text(s)

p = ROOT / 'app/src/main/java/com/sharkkernel/manager/model/Models.kt'
s = p.read_text()
if 'rootDetail:' not in s:
    marker = '    val root: Boolean = false,\n    val supported:'
    if marker not in s:
        raise SystemExit('DeviceState marker not found')
    s = s.replace(marker, '    val root: Boolean = false,\n    val rootDetail: String = "",\n    val supported:')
p.write_text(s)

p = ROOT / 'app/src/main/java/com/sharkkernel/manager/ui/SharkViewModel.kt'
s = p.read_text()
if 'fun retryRoot()' not in s:
    marker = '    fun refreshNow() = viewModelScope.launch { _state.value = SharkRepository.snapshot(_state.value) }\n'
    extra = '    fun retryRoot() = viewModelScope.launch {\n        DeviceRepository.invalidateRoot()\n        _state.value = _state.value.copy(refreshing = true)\n        _state.value = SharkRepository.snapshot(_state.value)\n    }\n'
    if marker not in s:
        raise SystemExit('refreshNow marker not found')
    s = s.replace(marker, marker + extra)
p.write_text(s)

print('alpha2 root backend materialized')
