# Hunter’s Atlas 1.3 — validation

The 1.3 release passed 72 automated checks: 48 owned-runtime checks (35 installer and 13 contract), 20 legacy bootstrap checks, and 4 asset checks. Eight added checks cover Windows Desktop resolution, redirected folders and OneDrive cloud shortcuts. A clean install was exercised with Atlas’s own Python, system PATH, a Unicode installation path, fresh map preparation, and a second launch that reused the maps with zero generator runs.

The actual GPU helper was exercised in scaled automatic mode. The final probe was mocked only during that dry run, so this result does not claim broad GPU coverage.

Live game checks used clean 04 and 05 installations with copied saves and the owned runtime. They covered opening the native in-game Map tile, pan and zoom, cancel, closing and reopening, and travel from Cathedral Ward to Hunter’s Dream. The installed desktop-target executable separately passed the real launcher UI smoke check, and the owner confirmed the normal play experience works as expected. All 15 live save files retained their original SHA-256 hashes.

The final screenshot was inspected from the native post-overlay swapchain. Geometry was checked with fog disabled. Live gameplay QA was performed on the Windows 11 machine with CUSA00207 1.09. Windows 10/11 x64 is the stated requirement, but gameplay was not verified on both versions. These checks do not certify all game builds, GPUs, routes, controllers or full playthroughs. See [compatibility](COMPATIBILITY.md) and [controls and coverage](MAP-FEATURES.md).
