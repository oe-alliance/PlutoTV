# Pluto TV Plugin for Enigma2


# Relases Notes:

## 3.0

### Rewrite Pluto TV plugin
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