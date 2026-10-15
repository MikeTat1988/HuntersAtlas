# Install and rollback

## Easy installation

Download **Hunters-Atlas-1.4.0-beta2.zip** from [GitHub Releases](https://github.com/MikeTat1988/HuntersAtlas/releases), then extract the whole archive into a folder you can keep. GitHub's **Code → Download ZIP** contains source, not the ready-to-install runtime.

The release is a flat folder: `Install.ps1`, `Uninstall.ps1`, `manifest.json`, `runtime\`, `art\`, `maps\`, `settings\`, `tools\`, `installer\` and `adapter\` are together at its root. Use that same extracted root as the Atlas folder in the launcher.

1. Close the launcher and game.
   If upgrading an existing Atlas adapter, run its `Uninstall.ps1` first, keeping its receipt and rollback folder. The installer accepts the matching original launcher rather than overwriting an installed or unknown adapter.
2. In the extracted release folder, open PowerShell and run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
   ```

3. Enter the existing launcher folder containing `Bloodborne.exe`. The helper shows the Atlas and backup locations. The installer checks compatibility before replacing the launcher and keeps a verified copy of the original. Do not delete that backup.
4. Open your usual launcher. The Atlas package path is the extracted release root. If it is not already selected under **Mods & patches → Hunter's Atlas**, Browse to that root folder once.
5. Select **Prepare Atlas maps** if requested. It reads your configured local game and takes several minutes. Enable Atlas and click normal **Play**.

The execution-policy option above applies only to that PowerShell process. It does not change the system policy. You can inspect both helper scripts before running them.

To turn Atlas off, uncheck its enable box. To restore the original launcher, close the game/launcher and run `Uninstall.ps1` from the same extracted release root, entering the launcher folder when prompted. Keep the original extracted files and rollback folder until uninstall succeeds.

## Manual installer commands

Close the launcher and game before installing or uninstalling the adapter. Preserve the complete extracted release and a new rollback directory until testing succeeds.

From the extracted release directory, run:

```powershell
.\installer\AtlasSetup.exe install `
  --launcher-root 'C:\Games\Bloodborne\launcher' `
  --adapter-root '.\adapter' `
  --atlas-folder 'C:\Mods\Hunters-Atlas-1.4.0-beta2' `
  --rollback-root 'C:\Backups\Hunters Atlas rollback'
```

These are example paths; select the existing launcher folder that contains `Bloodborne.exe` and its matching `run.py`. The adapter folder must contain the supplied rebuilt `Bloodborne.exe`, `_atlas_internal` tree and build receipt. The Atlas folder is the extracted release root and must contain `manifest.json` plus the `runtime`, `art`, `maps`, `settings` and `tools` directories.

The installer accepts only the fingerprinted stock launcher, matching launch script, adapter receipt and valid Atlas package. It preserves `run.py`, the stock `_internal` tree, game files, saves and settings. It backs up the original launcher executable and installs the matching adapter executable plus its separate `_atlas_internal` dependencies. Existing or modified receipts are validated before a reinstall.

Uninstall with the receipt written in the launcher directory:

```powershell
.\installer\AtlasSetup.exe uninstall `
  --receipt 'C:\Games\Bloodborne\launcher\atlas-install-receipt.json'
```

Uninstall verifies the installed files and rollback copy, restores the exact original `Bloodborne.exe`, and removes only the receipt-owned adapter dependencies. It retains an uninstalled receipt and rollback bundle. If any protected installed or rollback file changed, it refuses to overwrite it; resolve that change before retrying. Do not manually delete the rollback copy first.

Enable/disable requires no uninstall. Use **Mods & patches → Hunter's Atlas** and the normal **Play** button. Preparing maps writes only the package's generated map/font outputs and its staging/rollback files. It does not alter the configured game or saves.
