# Atlas updates and recovery

Hunter’s Atlas 1.3 owns its tested Windows 1.9 runtime, Python, Tk and required DLLs. An ordinary update to a separate Bloodborne launcher does not replace the Atlas runtime or generated maps. Atlas runtime updates are delivered through Atlas packages.

For an independent Atlas installation, close Atlas and the game, extract the new **Hunters-Atlas-1.3-Windows.zip** to a new folder, and run **Update.cmd from that extraction**. The updater finds the installed Atlas and preserves its profile, settings and maps. Rebuildable caches are recreated as needed.

To migrate from launcher-integrated Atlas 1.2 or earlier, extract 1.3 into a new folder and run **Install.cmd** instead. Keep the older folder available for map import; do not uninstall it first because its uninstaller resets maps. Keep a full copy if you need to restore its legacy integration.

The ordinary Bloodborne desktop shortcut continues to open the game. If the imported preference had Atlas disabled, enable **Hunter’s Atlas** under **Mods & patches** before choosing **Play**. Then open the native in-game **Map** tile. The separate ordinary launcher may remain installed for stock play.

## Recovery

Install and update operations print a recovery journal path. Close Atlas and the game, then run the included private Python interpreter and installer from the new Atlas package:

```text
runtime\python\python.exe -I -B owned\installer.py --recover "JOURNAL"
runtime\python\python.exe -I -B owned\installer.py --rollback "JOURNAL"
```

Replace `JOURNAL` with the exact path printed by the operation. `--recover` reverses or completes an interrupted activation from its journal; `--rollback` restores the retained prior installation. Preserve the full previous Atlas folder when the old integration may be needed. Recovery does not restore old saves over current saves.

**Uninstall.cmd** restores the previous desktop shortcut and leaves Atlas files, maps and settings in place. An external legacy hook left by an older 1.2 setup is outside the 1.3 uninstaller’s management.

See [installation](INSTALL.md) for package steps and [compatibility](COMPATIBILITY.md) for the tested scope.
