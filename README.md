# snapjaw: Vanilla World of Warcraft AddOn manager
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) [![CodeQL](https://github.com/refaim/snapjaw/actions/workflows/codeql.yml/badge.svg?branch=master)](https://github.com/refaim/snapjaw/actions/workflows/codeql.yml) [![Package](https://github.com/refaim/snapjaw/actions/workflows/package.yml/badge.svg)](https://github.com/refaim/snapjaw/actions/workflows/package.yml)

## Features
- Support for Git repositories as addon sources
- Detection of outdated and/or modified addons
- Automatic handling of folder naming and nested addon folders
- Fast addon update check due to multithreading implementation
- Simple command line interface

## How to install
- [Download snapjaw](https://nightly.link/refaim/snapjaw/workflows/package/master/snapjaw.zip)
- Unpack snapjaw.exe to WoW directory (where WoW.exe is located)
- See usage examples or run `snapjaw --help`

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
- [Python 3.10](https://www.python.org)
- [poetry](https://python-poetry.org)
