from pathlib import Path

p = Path('project/app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionCode = 1001', 'versionCode = 1002')
s = s.replace('versionName = "1.0.0-alpha2"', 'versionName = "1.0.0-alpha3"')
s = s.replace('    implementation("com.github.topjohnwu.libsu:core:6.0.0")\n', '')
p.write_text(s)

p = Path('project/settings.gradle.kts')
s = p.read_text().replace('        maven("https://jitpack.io")\n', '')
p.write_text(s)

p = Path('project/app/src/main/java/com/sharkkernel/manager/data/DeviceRepository.kt')
s = p.read_text()
s = s.replace(
    '    fun invalidateRoot() {\n        cached = null\n        cachedAtMs = 0L\n    }',
    '    fun invalidateRoot() {\n        cached = null\n        cachedAtMs = 0L\n        RootShell.reset()\n    }'
)
p.write_text(s)

p = Path('project/README.md')
s = p.read_text()
s += '''\n\n## 1.0.0-alpha3 root compatibility\n\n- Root detection uses the legacy persistent interactive `Runtime.exec("su")` strategy.\n- The probe writes `echo /testRoot/` through the opened shell, matching the old RootUtils behavior.\n- libsu and JitPack are no longer required.\n- Retry Root closes the current shell and forces a fresh KernelSU negotiation.\n'''
p.write_text(s)
