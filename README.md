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

## Install

Download `NoBuildingStability.zip` from the [Releases](../../releases) page.
Extract the three files (`NoBuildingStability_P.pak`, `.utoc` and `.ucas`) into
`RSDragonwilds\Content\Paks\~mods` in the game folder. Create the `~mods` folder
if it doesn't exist.

The release is built for game build 26162923 (Unreal Engine 5.6). On that build
the mod mounted and achievements kept unlocking with it installed. After a game
update, a new release may be needed, or you can build the mod yourself (below).

## Build it yourself

The mod replaces a whole asset, so after a game update it should be rebuilt from
the new version. You need Python 3. Only the standard library is used.

```
python build_mod.py --game "C:\Program Files (x86)\Steam\steamapps\common\RSDragonwilds"
```

`--game` is the folder that contains `RSDragonwilds.exe`. Without it, the script
looks two folders above itself, so cloning this repo to
`<game>\ModSource\NoBuildingStability` also works. The script writes the three
files to `RSDragonwilds\Content\Paks\~mods`. Use `--out DIR` to write them
somewhere else.

If the asset's layout has changed, the script stops with an error instead of
writing a broken mod.

## Uninstall

Delete `NoBuildingStability_P.pak`, `.utoc` and `.ucas` from
`RSDragonwilds\Content\Paks\~mods`. Your worlds go back to normal stability.
