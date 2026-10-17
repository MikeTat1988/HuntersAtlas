Hunter's Atlas 1.3 - independent installation with the in-game map

Extract the whole package. Run Install.cmd once, then use the normal Bloodborne
desktop shortcut. Play opens the game with the existing in-game Map tile,
controller controls and optional lamp travel. The map appears inside the game.
If the imported preference had Atlas off, enable it under Mods & patches first.
Use a permanent folder your normal Windows account can read and write.
Keep the package outside OneDrive/synced or linked folders. A shortcut on a
redirected Windows Desktop is supported.

Atlas owns its tested Windows 1.9 game runtime, Python, scripts and DLLs.
Updating a separate ordinary launcher does not replace Atlas or its maps.
Upstream runtime improvements reach this installation through tested Atlas
updates. The ordinary launcher can also remain installed for stock play.

Install imports the selected game, DLC, save folder and launcher preferences.
Keep using your existing saves. The package does not include game files, maps
or saves. A fresh installation prepares maps once from your own supported game
(CUSA00207, 1.09). Valid existing maps are retained during migration/update.

For an Atlas update, extract the NEW package elsewhere and run its Update.cmd.
It finds the installed Atlas location and retains maps, settings and saves.
Close Atlas and the game before updating. Command line options include
--target, --launcher, --profile-source and --shortcut for explicit locations.

The installer reports a recovery journal. To recover or roll back, use the
new package's runtime\python\python.exe -I -B owned\installer.py followed by
--recover JOURNAL or --rollback JOURNAL. Keep previous editions until setup
completes; saves are never restored from an old snapshot.
Uninstall.cmd restores the previous desktop shortcut and retains
Atlas files and generated data for recovery.

Atlas settings and generated caches are under state. Updates preserve settings
and assets.atlaslite; rebuildable caches are recreated as needed.
Runtime updates do not invalidate compatible map geometry.
The runtime is verified against native-build.json and dependencies.json.
Runtime source provenance and third-party notices accompany the source package.
