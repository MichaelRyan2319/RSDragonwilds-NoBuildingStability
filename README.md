# No Building Stability for RuneScape: Dragonwilds

Turns off building stability in Normal and Hard worlds and keeps achievements
enabled.

The game already has a "No Building Stability" world setting, but you can only
pick it in Custom or Creative worlds, and achievements don't unlock in those
modes. This mod turns on the game's own no-stability behaviour while your world
stays Normal or Hard.

## How it works

The setting's value comes from the world's saved value if it has one. Otherwise
it comes from `DA_DifficultySetting_NoBuildingStability`'s
`PresetDefaults[current mode]`. The mod overrides that one data asset and adds:

```
PresetDefaults = { Normal: 1.0, Hard: 1.0 }
```

Nothing is written to your saves and no game file is changed. The mod is a small
IoStore container (`.pak` / `.utoc` / `.ucas`) in the game's `~mods` folder.

Achievement unlocks are skipped only when the world's `ESurvivalDifficulty` is
Creative or Custom, and this mod doesn't change it. The game's mod check
(`CheckForMods`) logs a warning and marks the world as modded for people
joining, but achievements still unlocked in testing.

## Build and install

This repo has no prebuilt pak: the mod is a modified copy of a game asset, so
you build it from your own copy of the game. You need Python 3. Only the
standard library is used.

The script finds the game from its own location: the game folder must be two
folders above `build_mod.py`. The easiest setup is to clone this repo into a
`ModSource` folder inside the game folder:

```
cd "C:\Program Files (x86)\Steam\steamapps\common\RSDragonwilds"
git clone https://github.com/MichaelRyan2319/RSDragonwilds-NoBuildingStability ModSource\NoBuildingStability
python ModSource\NoBuildingStability\build_mod.py
```

The script writes `NoBuildingStability_P.pak`, `.utoc` and `.ucas` to
`RSDragonwilds\Content\Paks\~mods`. Use `--out DIR` to write them somewhere else.

Re-run the script after every game update. The mod replaces a whole asset, so it
has to be rebuilt from the current version. If the asset's layout has changed,
the script stops with an error instead of writing a broken mod.

Built for game build 26162923 (Unreal Engine 5.6). On that build the mod mounted
and achievements kept unlocking with it installed.

## Uninstall

Delete `NoBuildingStability_P.pak`, `.utoc` and `.ucas` from
`RSDragonwilds\Content\Paks\~mods`. Your worlds go back to normal stability.
