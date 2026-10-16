# Launcher updates and recovery

Hunter’s Atlas 1.1 includes adapters for official Windows 1.7.2 and 1.8.1,
plus automatic source rebuilding for other official releases from 1.7 onward.

For a fresh installation, extract the complete package and run Install.cmd.
For an installed Atlas, extract into a NEW folder and run Update.cmd there.
It selects the installed launcher version, without silently downgrading it.
Use the ordinary launcher Update button when you want a newer launcher.

The updater prefers an authenticated bundled adapter. Otherwise it downloads
official release metadata and source, merges the reviewed Atlas integration,
compiles locally, checks binary identity, stages the pair and reopens the launcher.
No uninstall or second confirmation is requested. Disabled Atlas also follows updates.

The signed catalog uses a pinned RSA-3072 public key. Expired or unavailable
catalogs fall back to official release metadata and its archive SHA-256.
Local builds record the installed seed hash, immutable upstream commit,
source archive digest and output hashes separately from signed adapter downloads.
A version number never bypasses dependency verification.

The first rebuild installs a hash-pinned portable MSYS2 bootstrap and signed
compiler packages in local application data. Allow several minutes and 8 GiB.
Source conflicts, changed submodule revisions or failed native checks require
an Atlas integration repair; arbitrary future compatibility cannot be guaranteed.
The official launcher still updates: Atlas retains its maps in a pending state,
and Play uses the stock runtime. Startup retries are spaced by six hours;
Check Atlas updates retries immediately. Unverified launcher downloads are never activated.

## Preserved data

The coordinator retains launcher `user`, `out`, `mods`, graphics/input configuration, mod/patch selections and logs. External save locations stay selected. It changes only the Atlas association fields in the profile and preserves unknown settings and the current Atlas enable preference. The maintenance lock is shared with installation/uninstallation and launch checks. Activation and rollback require the relevant game and launcher processes to stop.

Generated maps have a separate identity derived from the generator, feature extractor, schemas, and relevant game inputs. An unchanged key reuses the verified pack with zero generator invocations. A changed extractor, supported map input, event/talk/parameter/text input or schema requires preparation. Older public packs without this key and feature metadata are prepared once. Runtime or launcher changes alone do not invalidate maps. Player ZIPs contain no game maps, game font or saves.

## Cancel, recover and roll back

The coordinator prints a journal path in a sibling `.atlas-update-<id>` directory. That directory contains an immutable helper interpreter and:

- **Cancel.cmd**: request cancellation during preparation. Wait for preparation to stop; the working installation remains in place.
- **Recover.cmd**: reverse an interrupted activation using its persisted rename journal. A live preparation must finish shutdown first.
- **Rollback.cmd**: deliberately restore the retained previous launcher/Atlas pair after a successful update. Close both products first. Newer save progress and mutable settings are carried back; rollback does not replace them with an old snapshot.

Do not manually delete transaction files while an update or recovery is running. If both source and destination of an interrupted rename exist, recovery preserves both and reports the ambiguity instead of guessing. Keep the journal, `preparation.log`, and Atlas `state/preparation.log` for diagnosis.

To uninstall after updating, run **Uninstall.cmd from the currently associated Atlas folder**. Its per-install receipt restores the stock executable for the active target (the currently installed version), rather than a globally hardcoded older executable. It retains your ordinary saves and settings. Rollback is a separate operation from uninstall.

## Maintainer requirements

The player package includes the signed 1.7.2/1.8.1 compatibility catalog,
the matching 1.8.1 adapter and the reviewed rebuild seed. A source ZIP accompanies
the player ZIP, including exact legacy native source and the rebuild inputs.
The 1.7.2 binary retains its legacy identity; newer native builds expose their
compiled identity for preflight. Never label an old binary as a new upstream build.
See [release procedure](releases/RELEASE-PROCESS.md).
