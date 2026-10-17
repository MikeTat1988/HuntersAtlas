# Hunter’s Atlas 1.3 — install and update

## Install

1. Download **Hunters-Atlas-1.3-Windows.zip** and extract the whole archive to a permanent folder outside the game and launcher folders.
2. Run **Install.cmd**. It imports your existing game, DLC, save location and launcher preferences, then updates the Bloodborne shortcut on the Windows desktop. If asked, point it to the original launcher folder so it can find your existing profile and saves.
3. Open Bloodborne from the desktop shortcut. If the imported preference had Atlas off, enable **Hunter’s Atlas** under **Mods & patches** before choosing **Play**. In the game, open the native **Map** tile. Use the usual controller controls; optional lamp travel works from the map.

Do not uninstall a launcher-integrated Atlas 1.2 or earlier first: its uninstaller resets map data. A compatible existing map pack is reused. If one is unavailable, the first Play prepares maps from your own game files once; later launches reuse them.

The package includes its tested Windows 1.9 runtime, Python, Tk and required DLLs. You do not need system Python, a compiler, or the official launcher’s private interpreter.

Keep the Atlas package in an ordinary local folder your Windows account can read and write, outside OneDrive/synced or linked folders. The shortcut can still be created on your redirected Windows Desktop.

## Update

To migrate from launcher-integrated Atlas 1.2 or earlier, extract 1.3 into a new folder and run **Install.cmd**, keeping the old folder available for map import. **Update.cmd** locates an already independent Atlas installation.

Close Atlas and the game. Extract **Hunters-Atlas-1.3-Windows.zip** into a new folder and run **Update.cmd from that new extraction**. It detects the installed Atlas and carries over its profile, settings and maps. Rebuildable caches are recreated as needed. Keep the previous full Atlas folder as a backup if you need its legacy integration.

An ordinary update to a separate launcher does not replace Atlas or its maps. Atlas runtime updates arrive in Atlas packages; apply them with the steps above.

## Uninstall or recover

Close Atlas and the game, then run **Uninstall.cmd** from the installed Atlas folder. It restores the previous Bloodborne desktop shortcut and retains Atlas files, maps and settings for recovery. An external legacy hook from an older 1.2 setup is not managed by the 1.3 uninstaller; retain the full old backup if you need that integration.

For an interrupted install, run the new package’s private interpreter and installer with the journal path printed by setup:

```text
runtime\python\python.exe -I -B owned\installer.py --recover "JOURNAL"
runtime\python\python.exe -I -B owned\installer.py --rollback "JOURNAL"
```

Replace `JOURNAL` with the exact path printed by setup. Use `--recover` for an interrupted operation or `--rollback` to restore the previous installation. Close Atlas and the game first.

## Requirements and size

Windows 10 or 11, 64-bit. The verified game build is CUSA00207 version 1.09. The download is about 177 MB and the installed package about 415 MB, plus generated caches. Game files, maps, native font and saves are not included.

See [compatibility](COMPATIBILITY.md), [updates and recovery](LAUNCHER-UPDATES.md), and [QA status](QA.md).
