# snapjaw: Vanilla World of Warcraft AddOn manager
[![CI](https://github.com/refaim/snapjaw/actions/workflows/ci.yml/badge.svg)](https://github.com/refaim/snapjaw/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/refaim/snapjaw/graph/badge.svg)](https://codecov.io/gh/refaim/snapjaw)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![GitHub release](https://img.shields.io/github/v/release/refaim/snapjaw)](https://github.com/refaim/snapjaw/releases/latest)

## Features
- Support for Git repositories as addon sources
- Detection of outdated and/or modified addons
- Automatic handling of folder naming and nested addon folders
- Fast addon update check due to multithreading implementation
- Simple command line interface

## How to install

### Windows
- [Download snapjaw](https://github.com/refaim/snapjaw/releases/latest) (the `.zip` file)
- Extract the archive into the WoW folder. This will create a structure similar to `C:\Games\WoW\snapjaw\snapjaw.exe`. Alternatively, if you choose a different destination, you'll need to specify the path to the addons directory using the `--addons-dir` argument.
- See usage examples or run `snapjaw.exe --help`

### Linux
- [Download snapjaw](https://github.com/refaim/snapjaw/releases/latest) (the `.tar.gz` file)
- Extract and install:
  ```
  tar xzf snapjaw-*-linux-x86_64.tar.gz
  chmod +x snapjaw
  mv snapjaw ~/.local/bin/
  ```
- Run from your WoW directory: `cd /path/to/wow && snapjaw --help`
- Or use `--addons-dir` to specify the path to `Interface/Addons` from anywhere

#### Note
If you are new to snapjaw, you will need to reinstall each of your addons manually using the `snapjaw install` command. This process is essential as it creates an index file to effectively track the status of your addons folder.

## Usage examples
```
cd c:\games\wow
snapjaw install https://github.com/refaim/TrainerSkills
```
```
2022-11-01 01:45:16,711 [INFO] Cloning https://github.com/refaim/TrainerSkills.git
2022-11-01 01:45:18,540 [INFO] Installing addon "TrainerSkills"
2022-11-01 01:45:18,759 [INFO] Done
2022-11-01 01:45:18,809 [INFO] Saving config...
2022-11-01 01:45:18,817 [INFO] Done!
```
---
```
snapjaw status -v
```
```
addon                          status      released_at    installed_at
-----------------------------  ----------  -------------  --------------
Accountant                     up-to-date  Apr 24 2016    Oct 30
AdvancedTradeSkillWindow       up-to-date  Oct 14         Oct 30
Altoholic                      up-to-date  Feb 09 2018    yesterday
Beastmaster                    up-to-date  Jun 23 2017    today
BetterCharacterStats           up-to-date  Sep 23 2019    Oct 30
Cartographer                   up-to-date  Oct 22         Oct 30
ClassIcons                     up-to-date  today          today
CleanChat                      up-to-date  Dec 31 2018    Oct 30
Mail                           up-to-date  Jun 04 2019    Oct 30
MasterTradeSkills              up-to-date  Oct 22         Oct 30
Mendeleev                      modified    Oct 16         Oct 30
MobInfo2                       up-to-date  yesterday      yesterday
pfQuest                        up-to-date  Sep 30         Oct 30
pfQuest-turtle                 up-to-date  Sep 29         Oct 30
PvPWarning                     up-to-date  May 08 2022    Oct 30
QuestItem                      up-to-date  Feb 01 2018    Oct 30
Quiver                         untracked
ReagentData                    up-to-date  Oct 22         Oct 30
RecipeRadar                    up-to-date  Oct 23         Oct 30
RestBar                        up-to-date  May 25 2022    Oct 30
ShaguTweaks                    outdated    Oct 30         Oct 28
```
---
```
snapjaw update ShaguTweaks
```
```
2022-11-01 01:52:55,539 [INFO] Cloning https://github.com/shagu/ShaguTweaks.git
2022-11-01 01:53:01,098 [INFO] Installing addon "ShaguTweaks"
2022-11-01 01:53:01,530 [INFO] Done
2022-11-01 01:53:01,602 [INFO] Saving config...
2022-11-01 01:53:01,610 [INFO] Done!
```

## Requirements for developers
- [Python 3.12](https://www.python.org)
- [uv](https://docs.astral.sh/uv/)
