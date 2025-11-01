# <p align="center">Pluto TV Plugin for Enigma2 (E²) ![GitHub repo size](https://img.shields.io/github/repo-size/oe-alliance/PlutoTV.svg) ![Profil views](https://komarev.com/ghpvc/?username=oe-alliance)</p>

Pluto TV is a free streaming service with many “linear” themed channels (news, series, documentaries, movies) and on-demand content. The plugin neatly integrates this content into Enigma2 – including bouquets (channel lists), favorites, and detailed views.


Version from <a href="https://www.opena.tv">openATV Team</a>. 

This plugin was developed with a lot of 💞 for the Enigma2 community. You are free to use and modify it for personal use.

---

<details>
<summary>Click to show Relases Notes.</summary> 

# Relases Notes:
**V3.0.1 - 28.10.2025**
**Small correction and improvements**
- Correct the Samsung URL.
- Correct enumeration of serviceTypes dictionary.
- Ensure bouquet service numbers are in hex.
- Optimise more code.
- Improve more variable names for code clarity.
- Update version number.

**V3.0 - 23.10.2025**
**Rewrite Pluto TV plugin**
- Rewrite and optimize all aspects of the Pluto TV plugin.
- All the code is now in one module.
- Move all bouquet updating to a detached background thread.
- Move the list of supported regions into an upgradeable XML file.
- Make the Setup functions a sub-class of Setup.
- Make the screens fully skin-able.
- Add an option, via TEXT button, to temporarily view the content for any supported region.
- Make the content list configurable via a skin.
- Show the number of items in each sub menu.
- Add options for how to display the show/movie details.  Allow the elements of the details to be colored via a skin.
- Add dynamic HELP.
- Allow favorites to be defined separately for each region.
- Improve the management of region bouquets.
- Allow Pluto TV to be added to the main menu.
- Make the pop up to confirm plugin close as optional, now defaulted to off (No).
- Make the background bouquet update period configurable.
- Allow the use of "#DESCRIPTION" lines in bouquets to be optional.
- Manual updates for the bouquets is now within the Setup screen.
- Add an option to use LEFT/RIGHT buttons for navigation.
- Probably more that no longer stands out after all the development time.  ;)    
</details>

---

## Github status
[![Build](https://github.com/oe-alliance/PlutoTV/actions/workflows/buildbot.yml/badge.svg)](https://github.com/oe-alliance/PlutoTV/actions/workflows/buildbot.yml)
[![Lint Status](https://github.com/oe-alliance/PlutoTV/actions/workflows/pylint.yml/badge.svg)](https://github.com/oe-alliance/PlutoTV/actions/workflows/pylint.yml)
[![Ruff Status](https://github.com/oe-alliance/PlutoTV/actions/workflows/ruff.yml/badge.svg)](https://github.com/oe-alliance/PlutoTV/actions/workflows/ruff.yml)
[![Build Status](https://github.com/oe-alliance/PlutoTV/actions/workflows/compile.yml/badge.svg)](https://github.com/oe-alliance/PlutoTV/actions/workflows/compile.yml)
[![AUTOTAG](https://github.com/oe-alliance/PlutoTV/actions/workflows/autotag.yml/badge.svg)](https://github.com/oe-alliance/PlutoTV/actions/workflows/autotag.yml)


[![Pull Requests Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)](https://github.com/oe-alliance/PlutoTV/pulls)
[![Plugin Version](https://img.shields.io/github/v/tag/oe-alliance/PlutoTV?label=Latest%20Version&color=darkviolet)](https://github.com/oe-alliance/PlutoTV/tags)
[![Latest Release](https://img.shields.io/github/release-date/oe-alliance/PlutoTV?label=From&color=darkviolet)](https://github.com/oe-alliance/PlutoTV/releases/latest)
[![Github last commit](https://img.shields.io/github/last-commit/oe-alliance/PlutoTV)](https://github.com/oe-alliance/PlutoTV)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/oe-alliance/PlutoTV.svg?label=commits)](https://github.com/oe-alliance/PlutoTV/commits)
[![GitHub Activity](https://img.shields.io/github/commit-activity/m/oe-alliance/PlutoTV.svg?label=commits)](https://github.com/oe-alliance/PlutoTV/commits)
## SonarCloud status
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=bugs)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=oe-alliance_PlutoTV&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)

[![SonarQube Cloud](https://sonarcloud.io/images/project_badges/sonarcloud-light.svg)](https://sonarcloud.io/summary/new_code?id=oe-alliance_PlutoTV)

---

### 📜 License Information [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

This is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation

This plugin is released under GPLv3. See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.html#license-text) for full details.

<img width="120" height="58" alt="GPLv3_Logo svg" src="https://github.com/user-attachments/assets/67d32b0a-2a44-4fa9-a972-202daf28808e" />

---

## 1. 📦 Overview

- Integration of free Pluto TV channels in Enigma2
- Creation/updating of an Enigma2 bouquet (“Pluto TV”)
- Picon support (depending on image)

## 2. 🚀 Requirements

- OE Alliance-based Enigma2 image (e.g., openATV, openViX, openBH, etc.)
- Stable internet connection
- Python 3-compatible image
- Enough free Storage for picons

## 3. 📂 Installation
### 3.1 GUI (Feed)

**ℹ️ The best method, and the one we recommend, is to install the plugin via your image feed. This way, you will automatically receive updates along with regular image updates.**

- Menu → Extensions/Plugins
- Green button (“Download extensions”)
- Select category (Extensions / IPTV)
- Install PlutoTV, restart E2 if necessary

## 3.2 Console

```
opkg update
opkg install enigma2-plugin-extensions-plutotv
```

## 4. ⚙️ Settings

The following options are available on this settings screen:

- **Video region**
  - Select the region from which the Pluto TV services will be loaded.

- **Add to Main Menu**
  - Select 'Yes' to add Pluto TV to the Main Menu.
  
- **Add to Extensions Menu**
  - Select 'Yes' to add Pluto TV to the Extensions Menu.
  
- **Add update to Extensions Menu**
  - Select 'Yes' to add the Pluto TV update function to the Extensions Menu.

- **Confirm close**
  - Select 'Yes' to display a pop up screen to confirm the close request.

- **Picon directory**
  - Enter the directory where the Pluto TV picons will be saved.

- **Start PlutoTV in silent mode**
  - Select 'Yes' to display the initial data loading information.

- **Picon mode**
  - Select the operating picon mode.

- **Time between automatic updates**
  - Select the delay between automatic updates of the Pluto TV carousel.

- **Add Samsung channels to bouquets**
  - Select 'Yes' to add the Samsung VOD channels to the bouquet.

- **Add Xiaomi channels to bouquets**
  - Select 'Yes' to add the Xiaomi VOD channels to the bouquet.
  
- **Live TV mode**
  - Select the operating mode.

- **Live TV channel numbering**
  - Select the service numbering scheme.

- **Add #DESCRIPTION to bouquets**
  - Select 'Yes' to add #DESCRIPTION lines to all bouquets created by Pluto TV.

- **Force picon download**
  - Select 'Yes' to force picons to be downloaded from Pluto TV even if they are already locally available.

- **Separate episode details**
  - Select 'Yes' to add a blank line between the parts of the episode number, name and description.
  
- **Separate other details**
  - Select 'Yes' to add a blank line between the parts (cast, writers, directors, producers, release date) of the description.

## 5. 🖼️ Design & Skinning

- All screens are “skin-bar” – the plugin respects the appearance of your image.
- The content list itself can be configured via skin (e.g., columns, spacing).
- Detailed information can be color-coded (title, category, additional information).

## 6. 🌎 Bouquets & Regions – How it works

- “Bouquet” = channel list. The plugin creates/updates PlutoTV bouquets tailored to your region.
- The region selection comes from an XML file that can be updated, ensuring that regions remain up to date.
- Use the TEXT button to temporarily view another region (e.g., test US channels) without changing your main region.
- Favorites are saved per region. If you change the region, you will see the favorites stored there.

## 7. 🎥 Playback & Troubleshooting
Common problems

- No picture/error: Check network/region
- Jerky playback: Reduce quality, increase buffer
- No EPG: Check EPG import source, start import
- Channels missing: Regenerate/update bouquet
- Advertising: Normal (advertising-financed)

Logs
- View plugin/E2 logs via GUI or console (e.g., /home/root/logs/)

## 8. ❌ Uninstallation
### 8.1 GUI (Feed)
- Erweiterungen → Deinstallieren

## 8.2 Console

```
    opkg remove enigma2-plugin-extensions-plutotv
```

## 📖 9. FAQ

- Account required? – No; regional restrictions possible
- Recording? – Timeshift partially possible; recordings from HLS often restricted
- Keep channels up to date?

## 10. 🌐 Regions
### Available regions (excerpt)

| Land (ISO) | Name | TID |
|---|---|---|
| AR | Argentina | 10B |
| AT | Austria | 108 |
| AU | Australia | 11E |
| BO | Bolivia | 111 |
| BR | Brazil | 100 |
| CA | Canada | 101 |
| CH | Switzerland | 109 |
| CL | Chile | 110 |
| CO | Colombia | 10C |
| CR | Costa Rica | 10D |
| DE | Germany | 102 |
| DK | Denmark | 11C |
| DO | Dominican Republic | 11A |
| EC | Ecuador | 118 |
| ES | Spain | 103 |
| FI | Finland | 11F |
| FR | France | 104 |
| GB | United Kingdom | 106 |
| GT | Guatemala | 113 |
| HN | Honduras | 114 |
| IT | Italy | 10A |
| MX | Mexico | 105 |
| NI | Nicaragua | 115 |
| NO | Norway | 11D |
| PA | Panama | 116 |
| PE | Peru | 10E |
| PY | Paraguay | 119 |
| SE | Sweden | 11B |
| SV | El Salvador | 112 |
| US | United States | 107 |
| UY | Uruguay | 117 |
| VE | Venezuela | 10F |

---

### 🤝 Contributing & Contact

PlutoTV is created by users for users and we welcome every contribution. There are no highly paid developers. There are only users who have seen a problem and done their best to fix it. This means PlutoTV will always need the contributions of users like you. How can you get involved?

For questions or feedback, feel free and please open an issue or contribute with a Pull Request!

Pull requests are very welcome for:
- **Coding:** Developers can help by fixing a bug, adding new features, Integration improvements, Feature enhancements
- **Localization:** Translate into your native language.
- **Helping users:** Our support process relies on enthusiastic contributors like you to help others.

Your contribution is very welcome! Follow these steps:

1. 🍴 Fork this repository
2. 🔄 Create a branch for your feature
3. 💻 Make your changes
4. ✅ Commit using conventional messages
5. 📤 Push to your branch
6. 🔍 Open a Pull Request

Enjoy and help us improve it today. :)

---

### 🛠️ Support

For help and support, visit us on [oATV Forum](https://www.opena.tv/viewtopic.php?t=69049) or open an [Issue](https://github.com/oe-alliance/PlutoTV/issues)

---

### 🚨 Disclaimer

The project author is not responsible for how this software is used by others. It is not intended to be used for accessing or distributing copyrighted materials without authorization.
Users are solely responsible for determining the legality of their actions.

This repository has no control over the streams, links, or the legality of the content provided by the different hosts (including all mirror sites). It is the end user's responsibility to ensure the legal use of these streams, and we strongly recommend verifying that the content complies with all applicable laws, including copyright laws and regulations of your countrys jurisdiction before use.

---

⭐️ If you find this plugin useful, please give it a star on GitHub!
Thanks! ❤️ 💞 💖 ❤️‍🔥 💗

---

<p align="center">
  Powered 💡 by <a href="https://www.opena.tv">openATV Team</a>
</p> 
