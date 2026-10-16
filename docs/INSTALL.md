# Hunter’s Atlas 1.1 — installation

## Fresh installation

1. Choose your compatible game folder in the official launcher, then close the game and launcher.
2. Extract **Hunters-Atlas-1.1.zip** completely into a permanent folder outside the game and launcher folders, on the launcher’s drive.
3. Run **Install.cmd** and select the folder containing **Bloodborne.exe**. Wait for map preparation, usually 5–15 minutes.
4. Reopen the launcher → **Mods & patches** → tick **Enable Hunter’s Atlas**. Wait for **Ready**, then **Play**.
5. Open the game’s quick menu and select **Map**.

**Atlas must be enabled after installation.** Fog, travel and pickup options are independent.
No manual Python or compiler installation is required. On a launcher requiring a
new runtime, Atlas downloads its tools and rebuilds automatically; allow several
minutes, internet access and 8 GiB of free space.

## Update an existing Atlas

Close the game and launcher. Extract 1.1 into a **new folder**, run **Update.cmd
from that extraction**, and select your existing launcher. Its current version
is retained. Valid maps are reused; old maps without the required feature data
are prepared automatically. Keep both folders until the update completes.

Use the ordinary launcher **Update** button separately when you want a newer
launcher. Atlas follows automatically. If an upstream change prevents rebuilding,
the verified launcher still updates and runs stock while Atlas reports pending.

## Remove or recover

Keep the associated Atlas folder in place while installed. To remove Atlas, close
the game and launcher and run **Uninstall.cmd** from that folder. This restores
the stock launcher for the installed launcher version. Saves and ordinary settings
are preserved. See [updates and recovery](LAUNCHER-UPDATES.md).

## Requirements

Windows 10/11 64-bit, official Bloodborne for Windows, and verified CUSA00207 1.09.
Launcher 1.7.2 and the update to 1.8.2 were tested. See [compatibility](COMPATIBILITY.md).
