# Hunter’s Atlas 1.0

Hunter’s Atlas adds a fullscreen navigation map to Bloodborne on Windows. It shows your position and facing, supports zoom and recentering, and includes floor context for 16 supported areas.

## Downloads

- **Play:** [Hunters-Atlas-1.0.zip](https://github.com/MikeTat1988/HuntersAtlas/releases/download/v1.0/Hunters-Atlas-1.0.zip)

Atlas supports the official [Bloodborne for Windows v1.7.2 launcher](https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.7.2) and the verified CUSA00207 game build at version 1.09. Other regions and game builds are unverified. See [Compatibility](docs/COMPATIBILITY.md) before installing.

## Install and play

1. In the official launcher, choose your Bloodborne game folder containing `eboot.bin`. Close the game and launcher.
2. Extract the Play ZIP completely to a folder you will keep. Put it outside the game and launcher folders; do not run `Install.cmd` from inside the ZIP.
3. Run `Install.cmd` and select the folder containing the official `Bloodborne.exe`. The installer verifies compatibility and automatically prepares all 16 maps and the font from your game files. Allow 5–15 minutes. The original launcher is retained if preparation fails.
4. Open Bloodborne with your usual launcher shortcut. In **Mods**, enable **Hunter’s Atlas**, then click **Play**. **Prepare Atlas maps** is also available there if local maps need repair.
5. Start the game and open the quick menu to select **Map**.

The Play ZIP does not include Bloodborne files, generated maps, or the game font. Player installation does not require a separately installed Python runtime or compiler. Atlas uses the saves and game folder selected in the ordinary launcher; it does not create a separate game-save copy. The installer and Atlas do not patch game files or saves.

Keep the extracted folder in place while Atlas is installed. To remove it, close the game and launcher and run `Uninstall.cmd` from that folder. The original launcher executable is restored by the uninstaller.

If preparation fails or is cancelled, the installer restores the original launcher and package. Keep `.install/prepare.stdout.log`, `.install/prepare.stderr.log`, and `state/preparation.log` for diagnosis. After fixing the reported problem, extract the Play ZIP into a new folder and run Install again; an incomplete extraction is deliberately not reused.

If an error explicitly says preparation shutdown could not be verified, keep the folder and logs for recovery until the generator has stopped. The installer withholds package rollback in that case to avoid concurrent writes. Uninstall Atlas before updating the launcher to another version.

<details>
<summary>Установка по-русски</summary>

1. Убедитесь, что игра CUSA00207 1.09 уже запускается в поддерживаемом лаунчере v1.7.2. Закройте игру и лаунчер.
2. Скачайте архив **Play** и полностью распакуйте в постоянную папку вне папок игры и лаунчера.
3. Запустите **Install.cmd**, выберите папку с **Bloodborne.exe**. Установщик сам подготовит все 16 карт и шрифт из вашей игры; обычно это занимает 5–15 минут.
4. Откройте обычный лаунчер → **Моды → Hunter’s Atlas**, включите карту и нажмите **Играть**. В быстром меню игры выберите **Map**.
5. Для удаления закройте игру и лаунчер, затем запустите **Uninstall.cmd** из той же распакованной папки. Не перемещайте её до удаления.

Отдельные Python и компилятор не нужны. Установка и удаление сохраняют ваши игровые файлы, сейвы и обычные настройки.

</details>

## Example screenshots

| Quick menu | Central Yharnam, Great Bridge |
| --- | --- |
| ![The Map tile in the quick menu](examples/quick-menu.png) | ![Map at the Great Bridge](examples/great-bridge.png) |

| Scratched tower interiors | Cathedral Ward |
| --- | --- |
| ![Enclosed tower spaces marked with a scratched fill](examples/tower-interiors.png) | ![Map view in Cathedral Ward](examples/cathedral-ward-map.png) |

| Iosefka’s Clinic | Hunter’s Dream |
| --- | --- |
| ![Map view in Iosefka’s Clinic](examples/clinic.png) | ![Map view in Hunter’s Dream](examples/dream.png) |

| Hunter’s Nightmare | Menu navigation |
| --- | --- |
| ![Map view in the DLC](examples/dlc.png) | ![Map tile reached with left and right menu navigation](examples/menu-left-wrap.png) |

These captures show example map layouts and interface states. They do not certify every route, floor, controller, or scene.

## Limits

Markers are static and do not track live quest or gate states. Chalice Dungeons and unlisted game regions are unsupported. Compatibility and current release checks are recorded in [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) and [docs/QA.md](docs/QA.md).

## Source and licenses

The repository includes Atlas’s bootstrap, launcher integration and wrapper source, generator packaging and preparation code, the original map-generation algorithms, the native host, vendored sources, notices, and the build guide. See [source/SOURCE-BUILD.md](source/SOURCE-BUILD.md), [source/licenses/README.md](source/licenses/README.md), and the included license files. Hunter’s Atlas is an independent community project and is not affiliated with FromSoftware or Sony Interactive Entertainment.
