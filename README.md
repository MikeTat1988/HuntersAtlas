# Hunter’s Atlas 1.0

An in-game map for Bloodborne on PC.

Find your way through Yharnam with a fullscreen map that shows your position, facing direction, and locations of lamps, ladders, gates and NPCs. Explore 16 supported areas across the main game and DLC, with zoom, pan and different floor levels.

First, make sure Bloodborne runs with the [supported PC launcher v1.7.2](https://github.com/Supermedo/bloodborne_pc/releases/tag/windows-v1.7.2).

1. Download [**Hunters-Atlas-1.0.zip**](https://github.com/MikeTat1988/HuntersAtlas/releases/download/v1.0/Hunters-Atlas-1.0.zip) and extract it into a folder you’ll keep. Use this release file; **Code → Download ZIP** contains developer source only.
2. Close the game and launcher. Double-click **Install.cmd** in the extracted folder.
3. When prompted, select your launcher folder — the one containing **Bloodborne.exe**.
4. Open the launcher → **Mods & patches** → **Hunter’s Atlas**. For **Atlas folder**, choose the folder you extracted in step 1.
5. Click **Prepare Atlas maps** if prompted. This takes several minutes and adds approximately 100 MB.
6. Check **Enable Hunter’s Atlas** and click **Play**.

In the game, open the quick menu and select **Map**.

To turn Atlas off, uncheck **Enable Hunter’s Atlas**. To remove its launcher integration, close the game and launcher, then double-click **Uninstall.cmd** in the same extracted folder. Keep the package and original-launcher backup until uninstall completes.

<details>
<summary>Установка по-русски</summary>

1. Скачайте **Hunters-Atlas-1.0.zip** по ссылке выше. Кнопка **Code → Download ZIP** скачивает исходники для разработчиков.
2. Полностью распакуйте архив в постоянную папку. Закройте игру и лаунчер.
3. Дважды нажмите **Install.cmd**. Укажите папку своего лаунчера, где находится **Bloodborne.exe**.
4. Откройте обычный лаунчер → **Mods & patches** → **Hunter’s Atlas**. В **Atlas folder** выберите ту же распакованную папку.
5. Если предложено, нажмите **Prepare Atlas maps** и дождитесь завершения.
6. Включите **Enable Hunter’s Atlas**, нажмите **Play** и выберите **Map** в быстром меню игры.

Для удаления закройте игру и лаунчер и запустите **Uninstall.cmd**. Установка не требует изменения системной политики PowerShell.

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

| Hunter’s Nightmare DLC | Menu navigation |
| --- | --- |
| ![Map view in the DLC](examples/dlc.png) | ![Map tile reached with left and right menu navigation](examples/menu-left-wrap.png) |

These runtime captures show selected areas, heights and interface states. Some were collected during development; they illustrate the final map layouts. They do not certify every route or supported floor. Human visual review remains separate from technical checks.

## Compatibility and limits

Hunter’s Atlas supports the matching Windows PC launcher v1.7.2 and tested game executable. Installation verifies compatibility before replacing the launcher and retains its original executable for rollback. Game files, saves and personal settings are preserved.

The map supports controller navigation and mouse clicks, pan, zoom, elevation levels, recenter and Back. Other floors remain faintly visible for context, and enclosed spaces use a dark scratched treatment. Marker locations are static: they do not track live quest or gate states. Chalice Dungeons are not supported. Collision-derived floors and inferred interiors can contain omissions.

Map data and the required game font are prepared locally from the user’s own game files; they are not included in the download. Physical controller disconnect and focus-loss behavior still need broader testing. An idle title-screen attract movie can cause a guest fault; its cause remains unresolved.

## Source and licenses

Hunter’s Atlas builds on [Supermedo’s bloodborne_pc](https://github.com/Supermedo/bloodborne_pc). It is an independent community project and is not affiliated with FromSoftware or Sony. Development and original illustrative assets used AI assistance.

The [source repository](https://github.com/MikeTat1988/HuntersAtlas/tree/main/source) contains the implementation and build instructions. The download also includes corresponding source and dependency source in **legal/Source.zip**. The native host and Atlas additions retain their GPL notices; see **LICENSE**, source headers and dependency notices. Other components and art retain their respective licenses and provenance.
