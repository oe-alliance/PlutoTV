"""
Copyright (C) 2021 Team OpenSPA
https://openspa.info/

Copyright (c) 2021-2024 Billy2011 @ vuplus-support.org
20210618 (1st release)
- adaptions for VTI
- many fixes, improvements, mods & rewrites
- py3 adaption
20240831 (latest release)

Copyright (c) 2025 jbleyel and IanSav - Version 3.0.1

Rewrite Pluto TV plugin
- Rewrite and optimize all aspects of the Pluto TV plugin.
- All the code is now in one module.
- Move all bouquet updating to a detached background thread.
- Move the list of supported regions into an upgradeable XML file.
- Make the Setup functions a sub-class of Setup.
- Make the screens fully skin-able.
- Add an option, via TEXT button, to temporarily view the content for any
  supported region.
- Make the content list configurable via a skin.
- Show the number of items in each sub menu.
- Add options for how to display the show/movie details.  Allow the elements
  of the details to be colored via a skin.
- Add dynamic HELP.
- Allow favorites to be defined separately for each region.
- Improve the management of region bouquets.
- Allow Pluto TV to be added to the main menu.
- Make the pop up to confirm plugin close as optional, now defaulted to
  off (No).
- Make the background bouquet update period configurable.
- Allow the use of "#DESCRIPTION" lines in bouquets to be optional.
- Manual updates for the bouquets is now within the Setup screen.
- Add an option to use LEFT/RIGHT buttons for navigation.
- Probably more that no longer stands out after all the development time.  ;)

SPDX-License-Identifier: GPL-2.0-or-later
See LICENSES/README.md for more information.

PlutoTV is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

PlutoTV is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
PlutoTV.  If not, see <http://www.gnu.org/licenses/>.
"""

from calendar import timegm
from os import makedirs, statvfs
from os.path import exists, getsize, isdir, isfile, join
from pickle import dump, load
from re import sub
from requests import get
from shutil import copy2
from time import gmtime, localtime, sleep, strftime, strptime, time
from traceback import format_exc
from twisted.internet import defer, reactor, threads
from unicodedata import normalize
from urllib.parse import parse_qsl, quote_plus, urljoin, urlparse
from uuid import uuid4, uuid1

from enigma import eDVBDB, eEPGCache, ePicLoad, eServiceCenter, eServiceReference, eTimer, gRGB, iPlayableService

from skin import parseColor
from Components.ActionMap import HelpableActionMap
from Components.config import ConfigDirectory, ConfigNumber, ConfigSelection, ConfigSubList, ConfigSubsection, ConfigYesNo, config, getConfigListEntry  # noqa: F401
try:
	from Components.International import international
except ImportError:
	international = None
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
try:
	from Plugins.Extensions.IMDb.plugin import main as imdb
	imdbAvailable = True
except ImportError:
	imdbAvailable = False
try:
	from Plugins.Extensions.tmdb import tmdb
	tmdbAvailable = True
except ImportError:
	tmdbAvailable = False
from Screens.InfoBar import MoviePlayer
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import Setup
from Tools.Directories import SCOPE_CONFIG, SCOPE_GUISKIN, SCOPE_PLUGIN_ABSOLUTE, fileReadLine, fileReadLines, fileReadXML, fileWriteLine, fileWriteLines, resolveFilename
from Tools.LoadPixmap import LoadPixmap
from Tools.Notifications import AddNotificationWithCallback

from . import _, __version__

MODULE_NAME = __name__.split(".")[-1]

PLUTO_USER_AGENT = {"User-agent": "Mozilla/5.0 (Windows NT 6.2; rv:24.0) Gecko/20100101 Firefox/24.0"}
PLUTO_IMAGE_URL = "https://images.pluto.tv"
PLUTO_API_URL = "https://api.pluto.tv"
PLUTO_GUIDE_URL = f"{PLUTO_API_URL}/v2/channels"
PLUTO_LINEUP_URL = f"{PLUTO_API_URL}/v2/channels"
PLUTO_VOD_URL = f"{PLUTO_API_URL}/v3/vod/categories"
PLUTO_SEASON_URL = f"{PLUTO_API_URL}/v3/vod/series/%s/seasons"

PLUTO_FOLDER = "/tmp"
PLUTO_TIMER_PATH = "/etc/enigma2/PlutoTV_timer"
PLUTO_SERVICE_NUMBER_PATH = "/etc/enigma2/PlutoTV_numbers"

SID1_HEX = str(uuid4().hex)  # Defined as a global to save time.
DEVICEID1_HEX = str(uuid1().hex)  # Defined as a global to save time.

PLUTO_COUNTRY_NAME = 0
PLUTO_IP = 1
PLUTO_TIDS = 2
PLUTO_DATA = {
	"AUTO": (_("* Automatic *"), "", "0")
}
PLUTO_SERVICE_CHOICES = [
	("4097", f"{_("Original")} (4097)"),
	("5001", "ServiceGstPlayer (5001)"),
	("5002", "ServiceExtPlayer3 (5002)"),
]
config.plugins.PlutoTV = ConfigSubsection()
config.plugins.PlutoTV.addToMainMenu = ConfigYesNo(default=False)
config.plugins.PlutoTV.addToExtensionMenu = ConfigYesNo(default=False)
config.plugins.PlutoTV.addUpdateToExtensionMenu = ConfigYesNo(default=False)
config.plugins.PlutoTV.confirmClose = ConfigYesNo(default=False)
config.plugins.PlutoTV.updateTimer = ConfigSelection(default=5, choices=[
	(0, _("Updates disabled"))
] + [
	(x, ngettext("%d Hour", "%d Hours", x) % x) for x in range(1, 25)
])
config.plugins.PlutoTV.silentMode = ConfigYesNo(default=True)
config.plugins.PlutoTV.addXiaomi = ConfigYesNo(default=False)
config.plugins.PlutoTV.addSamsung = ConfigYesNo(default=True)
config.plugins.PlutoTV.channelNumbering = ConfigSelection(default="original", choices=[
	("original", _("Original")),
	("plugin", _("Plugin generated"))
])
config.plugins.PlutoTV.liveMode = ConfigSelection(default="samsung", choices=[
	("original", _("Original")),
	("roku", "Roku TV"),
	("samsung", "Samsung TV")
])
domData = fileReadXML(resolveFilename(SCOPE_PLUGIN_ABSOLUTE, "plutotv.xml"), default=None, source=MODULE_NAME)
choices = []
if domData is not None:
	for region in domData.findall("region"):
		country = region.get("country")
		name = international.getCountryTranslated(country) if international else region.get("country")
		ip = region.get("ip")
		tids = region.get("tids")
		if country and name and ip and tids:
			PLUTO_DATA[country] = (name, ip, tids)
			choices.append((country, name))
	choices.sort(key=lambda x: x[1])
	print(f"[PlutoTV] Data for {len(PLUTO_DATA)} regions loaded.")
else:
	print("[PlutoTV] Error: No region data loaded!")
choices.insert(0, ("AUTO", _("* Automatic *")))
config.plugins.PlutoTV.region = ConfigSelection(default="AUTO", choices=choices)
config.plugins.PlutoTV.bouquetCount = ConfigNumber(default=0)
config.plugins.PlutoTV.bouquetRegion = ConfigSubList()
config.plugins.PlutoTV.bouquetService = ConfigSubList()
for count in range(config.plugins.PlutoTV.bouquetCount.value):
	config.plugins.PlutoTV.bouquetRegion.append(ConfigSelection(default="AUTO", choices=choices))
	config.plugins.PlutoTV.bouquetService.append(ConfigSelection(default="4097", choices=PLUTO_SERVICE_CHOICES))
choices = [("NONE", _("None"))] + choices
config.plugins.PlutoTV.piconMode = ConfigSelection(default="srp", choices=[
	("srp", _("Reference")),
	("name", _("Name")),
	("snp", _("SNP"))
])
# config.plugins.PlutoTV.piconPath = ConfigDirectory(default="/usr/share/enigma2/picon")
config.plugins.PlutoTV.piconPath = ConfigSelection(default="/usr/share/enigma2/picon", choices=["/usr/share/enigma2/picon", "/picon"])
piconPath = config.plugins.PlutoTV.piconPath.value
if not isdir(piconPath):
	makedirs(piconPath)
config.plugins.PlutoTV.addDescriptions = ConfigYesNo(default=True)
config.plugins.PlutoTV.forcePiconDownload = ConfigYesNo(default=False)
config.plugins.PlutoTV.separateEpisode = ConfigYesNo(default=False)
config.plugins.PlutoTV.separateDetails = ConfigYesNo(default=False)


class PlutoLabel(Label):
	def __init__(self):
		self.actorsColor = 0x00BBBBBB
		self.descriptionColor = 0x00FFFFFF
		self.detailsColor = 0x00FFFFFF
		self.directorsColor = 0x00BBBBBB
		self.durationColor = 0x00999999
		self.episodeColor = 0x00FFFF00
		self.genreColor = 0x00999999
		self.producersColor = 0x00BBBBBB
		self.ratingColor = 0x00999999
		self.releaseColor = 0x00BBBBBB
		self.seasonColor = 0x00999999
		self.seriesColor = 0x00999999
		self.writersColor = 0x00BBBBBB
		Label.__init__(self)

	def applySkin(self, desktop, parent):
		if self.skinAttributes:
			skinAttributes = []
			for attribute, value in self.skinAttributes:
				match attribute:
					case "actorsColor" | "castColor":
						self.actorsColor = gRGB(parseColor(value, default=self.actorsColor)).argb()
					case "descriptionColor":
						self.descriptionColor = gRGB(parseColor(value, default=self.descriptionColor)).argb()
					case "detailsColor":
						self.detailsColor = gRGB(parseColor(value, default=self.detailsColor)).argb()
					case "directorsColor":
						self.directorsColor = gRGB(parseColor(value, default=self.directorsColor)).argb()
					case "durationColor":
						self.durationColor = gRGB(parseColor(value, default=self.durationColor)).argb()
					case "episodeColor":
						self.episodeColor = gRGB(parseColor(value, default=self.episodeColor)).argb()
					case "genreColor":
						self.genreColor = gRGB(parseColor(value, default=self.genreColor)).argb()
					case "producersColor":
						self.producersColor = gRGB(parseColor(value, default=self.producersColor)).argb()
					case "ratingColor":
						self.ratingColor = gRGB(parseColor(value, default=self.ratingColor)).argb()
					case "releaseColor":
						self.releaseColor = gRGB(parseColor(value, default=self.releaseColor)).argb()
					case "seasonColor":
						self.seasonColor = gRGB(parseColor(value, default=self.seasonColor)).argb()
					case "seriesColor":
						self.seriesColor = gRGB(parseColor(value, default=self.seriesColor)).argb()
					case "writersColor":
						self.writersColor = gRGB(parseColor(value, default=self.writersColor)).argb()
					case _:
						skinAttributes.append((attribute, value))
			self.skinAttributes = skinAttributes
		return Label.applySkin(self, desktop, parent)


class PlutoTV(Screen):
	skin = """
	<screen name="PlutoTV" title="Pluto TV" position="center,center" size="1180,570" resolution="1280,720">
		<widget name="loading" position="0,0" size="e,e-50" font="Regular;30" horizontalAlignment="center" verticalAlignment="center" zPosition="1" />
		<widget source="menu" render="Listbox" position="0,0" size="440,480" backgroundColorSelected="#00FF0063" itemHeight="30" transparent="1">
			<templates>
				<template name="Default" fonts="Regular;20" itemHeight="30" itemWidth="440">
					<mode name="default">
						<pixmap index="Icon" position="0,0" size="30,30" alpha="blend" padding="5" scale="centerScaled" />
						<text index="Name" position="30,0" size="350,30" font="0" horizontalAlignment="left" padding="5,0" verticalAlignment="center" />
						<text index="Count" position="380,0" size="60,30" autoAlign="1" font="0" horizontalAlignment="right" padding="5,0,10,0" verticalAlignment="center" />
					</mode>
				</template>
			</templates>
		</widget>
		<widget name="name" position="450,0" size="730,35" font="Regular;25" foregroundColor="#00FFFF00" horizontalAlignment="center" noWrap="1" verticalAlignment="center" />
		<widget name="poster" position="450,45" size="299,435" alphatest="blend" />
		<!-- The backgroundColor needs to be specified, as #00000000, because of an erroneous background color bleed from the last background color used in a previously drawn widget! -->
		<widget name="details" position="760,45" size="420,435" backgroundColor="#00000000" font="Regular;20" scrollText="direction=top,mode=bounce,startDelay=2500,stepSize=1,stepDelay=60,endDelay=2500,repeat=-1" transparent="1" />
		<!-- widget source="details" render="RunningText" position="760,45" size="420,435" backgroundColor="#00000000" font="Regular;20" options="movetype=swimming,startpoint=0,direction=top,steptime=120,repeat=10,always=0,startdelay=2000,pagedelay=1000,wrap" transparent="1" / -->
		<widget name="footnote" position="0,e-75" size="e,25" font="Regular;20" foregroundColor="#0000FFFF" horizontalAlignment="center" noWrap="1" verticalAlignment="center" />
		<widget source="key_red" render="Label" position="0,e-40" size="180,40" backgroundColor="key_red" conditional="key_red" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_green" render="Label" position="190,e-40" size="180,40" backgroundColor="key_green" conditional="key_green" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_yellow" render="Label" position="380,e-40" size="180,40" backgroundColor="key_yellow" conditional="key_yellow" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		<!--
		<widget source="key_blue" render="Label" position="570,e-40" size="180,40" backgroundColor="key_blue" conditional="key_blue" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		-->
		<widget source="key_menu" render="Label" position="920,e-40" size="80,40" backgroundColor="key_back" conditional="key_menu" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_text" render="Label" position="1010,e-40" size="80,40" backgroundColor="key_back" conditional="key_text" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_help" render="Label" position="1100,e-40" size="80,40" backgroundColor="key_back" conditional="key_help" font="Regular;20" foregroundColor="key_text" halign="center" valign="center">
			<convert type="ConditionalShowHide" />
		</widget>
	</screen>"""
	FAVORITES_PATH = resolveFilename(SCOPE_CONFIG, "PlutoTV_favorites")
	FAVORITES_NAME = _("** My Favorites **")

	MENU_INDEX = 0  # This is the value from getCurrentIndex() and added when the menu item is fetched by getCurrent().
	MENU_NAME = 1  # For skins this is index item 0!
	MENU_COUNT = 2
	MENU_ICON = 3
	MENU_TYPE = 4
	MENU_IDENTIFIER = 5
	MENU_EPISODE = 6

	HISTORY_TITLE = 0
	HISTORY_INDEX = 1
	HISTORY_TYPE = 2

	CATEGORY_IDENTIFIER = 0
	CATEGORY_NAME = 1
	CATEGORY_SUMMARY = 2
	CATEGORY_DESCRIPTION = 3
	CATEGORY_GENRE = 4
	CATEGORY_RATING = 5
	CATEGORY_DURATION = 6
	CATEGORY_POSTER = 7
	CATEGORY_IMAGE = 8
	CATEGORY_MEDIATYPE = 9
	CATEGORY_URL = 10
	CATEGORY_SEASONS = 11
	CATEGORY_CLIP = 12
	CATEGORY_CAPTIONS = 13

	EPISODE_IDENTIFIER = 0
	EPISODE_NAME = 1
	EPISODE_NUMBER = 2
	EPISODE_SEASON = 3
	EPISODE_DESCRIPTION = 4
	EPISODE_RATING = 5
	EPISODE_DURATION = 6
	EPISODE_ORIGINAL_DURATION = 7
	EPISODE_GENRE = 8
	EPISODE_POSTER = 9
	EPISODE_IMAGE = 10
	EPISODE_URL = 11
	EPISODE_CLIP = 12

	def __init__(self, session):
		def keyRedHelp():
			return _("Go back to the previous menu") if self.history else _("Close Pluto TV")

		Screen.__init__(self, session, enableHelp=True)
		self.baseTitle = _("Pluto TV")
		self.setTitle(self.baseTitle)
		self.loadingMsg = _("Loading Pluto TV categories, please wait...")
		self["loading"] = Label(self.loadingMsg)
		indexNames = {
			"Name": 0,
			"Count": 1,
			"Icon": 2
		}
		self["menu"] = List(indexNames=indexNames)
		self["menu"].onSelectionChanged.append(self.selectionChanged)
		self["name"] = Label()
		self["name"].hide()
		self["poster"] = Pixmap()
		self["poster"].hide()
		self["details"] = PlutoLabel()
		self["details"].hide()
		self["footnote"] = Label()
		self["footnote"].hide()
		self["key_menu"] = StaticText(_("MENU"))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText()
		self["key_yellow"] = StaticText()
		self["key_text"] = StaticText(_("TEXT"))
		if config.plugins.PlutoTV.silentMode.value:
			self.oldService = self.session.nav.getCurrentlyPlayingServiceReference()
			self.session.nav.stopService()
		else:
			self.oldService = None
		self.history = []
		self["actions"] = HelpableActionMap(self, ["PlutoActions"], {
			"close": (self.keyClose, _("Close Pluto TV")),
			"closeRecursive": (self.keyCloseRecursive, _("Close PlutoTV and close all menus")),
			"menu": (self.keySetup, _("Open the Pluto TV settings screen")),
			"back": (self.keyPreviousMenu, keyRedHelp),
			"region": (self.keySelectRegion, _("Select a VOD region"))
		}, prio=0, description=_("Pluto TV Actions"))
		self["menuActions"] = HelpableActionMap(self, ["PlutoActions", "NavigationActions"], {
			"select": (self.keySelect, _("Select the current menu item")),
			"top": (self["menu"].goTop, _("Move to first line / screen")),
			"pageUp": (self["menu"].goPageUp, _("Move up a screen")),
			"up": (self["menu"].goLineUp, _("Move up a line")),
			"down": (self["menu"].goLineDown, _("Move down a line")),
			"pageDown": (self["menu"].goPageDown, _("Move down a screen")),
			"bottom": (self["menu"].goBottom, _("Move to last line / screen"))
		}, prio=0, description=_("Pluto TV Actions"))
		self["menuActions"].setEnabled(False)
		self["previousMenuAction"] = HelpableActionMap(self, ["PlutoActions", "NavigationActions"], {
			"first": (self.keyTopMenu, _("Return to the top menu"))
		}, prio=0, description=_("Pluto TV Actions"))
		self["previousMenuAction"].setEnabled(False)
		self["movieDbAction"] = HelpableActionMap(self, ["PlutoActions"], {
			"moviedb": self.keyMovieDatabase
		}, prio=0, description=_("Pluto TV Actions"))
		self["movieDbAction"].setEnabled(False)
		self["favoriteAction"] = HelpableActionMap(self, ["PlutoActions"], {
			"favorite": self.keyFavorite,
		}, prio=0, description=_("Pluto TV Actions"))
		self["favoriteAction"].setEnabled(False)
		if not config.misc.actionLeftRightToPageUpPageDown.value:  # Add the "left" and "right" navigation options.
			self["menuActions"].addAction(self, "NavigationActions", "right", (self.keySelect, _("Select the current menu item")))
			self["previousMenuAction"].addAction(self, "NavigationActions", "left", (self.keyPreviousMenu, _("Go back to the previous menu")))
		self.region = config.plugins.PlutoTV.region.value
		self.categories = {}
		self.categoryMenu = []
		self.categoryTimer = eTimer()
		self.categoryTimer.callback.append(self.getCategories)
		self.films = []
		self.posterTimer = eTimer()
		self.posterTimer.callback.append(self.getTimedPoster)
		self.postersToDownload = []
		self.picLoad = ePicLoad()
		self.episodes = {}
		self.favorites = {}
		self.favoritesModified = False
		self.inFavoritesMenu = False
		self.seasonText = ngettext("Season", "Seasons", 1)  # This is required to resolve an ambiguity is translations for "Season" and "Seasons"!
		self.onLayoutFinish.append(self.layoutFinished)
		self.onClose.append(self.saveFavorites)

	def layoutFinished(self):
		self["menu"].enableAutoNavigation(False)  # Override list box self navigation.
		width = self["poster"].instance.size().width()
		height = self["poster"].instance.size().height()
		self.picLoad.setPara((width, height, 1, 1, 0, 0, "#00000000"))
		self.loadFavorites()
		self.categoryTimer.start(25, True)

	def loadFavorites(self):
		if isfile(self.FAVORITES_PATH):
			try:
				with open(self.FAVORITES_PATH, "rb") as fd:
					self.favorites = load(fd)
					for region in self.favorites.keys():
						print(f"[PlutoTV] {len(self.favorites[region])} '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}' favorites loaded from '{self.FAVORITES_PATH}'.")
			except OSError as err:
				print(f"[PlutoTV] Error {err.errno}: Unable to load favorites '{self.FAVORITES_PATH}'!  ({err.strerror})")

	def saveFavorites(self):
		if self.favoritesModified:
			try:
				with open(self.FAVORITES_PATH, "wb") as fd:
					dump(self.favorites, fd, protocol=5)
					self.favoritesModified = False
					for region in self.favorites.keys():
						print(f"[PlutoTV] {len(self.favorites[region])} '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}' favorites saved to '{self.FAVORITES_PATH}'.")
			except OSError as err:
				print(f"[PlutoTV] Error {err.errno}: Unable to save favorites '{self.FAVORITES_PATH}'!  ({err.strerror})")
		elif len(self.favorites):
			print("[PlutoTV] No favorites changed, nothing to save.")

	def getCategories(self):
		self.setTitle(self.baseTitle)
		self["key_red"].setText(_("Close"))
		self["previousMenuAction"].setEnabled(False)
		self.history.clear()
		self.categories.clear()
		self.categoryMenu.clear()
		if self.region not in self.favorites:
			self.favorites[self.region] = {}
		self.categories[self.FAVORITES_NAME] = [self.favorites[self.region][x] for x in self.favorites[self.region].keys()]  # It is assumed that the favorites category item is *always* first!
		self.categoryMenu.append((self.FAVORITES_NAME, self.FAVORITES_NAME, len(self.favorites[self.region])))  # It is assumed that the favorites menu item is *always* first!
		header = buildHeader(PLUTO_DATA[self.region][PLUTO_IP])
		param = {
			"includeItems": "true",
			"deviceType": "web",
			"deviceId": DEVICEID1_HEX,
			"sid": SID1_HEX,
		}
		carousel = fetchURL(PLUTO_VOD_URL, header=header, param=param)  # A single dictionary.
		# carouselDump(self.region, carousel)
		# offset = carousel.get("offset", 0)
		# page = carousel.get("page", 0)
		# totalCategories = carousel.get("totalCategories", 0)
		# totalPages = carousel.get("totalPages", 0)
		# categories = carousel.get("categories", [])  # List of category dictionaries.
		totalCategories = int(carousel.get("totalCategories", "0"))
		if totalCategories:
			print(f"[PlutoTV] {totalCategories} {PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]} VOD categories found.")
			for category in carousel.get("categories", []):  # List of category dictionaries.
				# identifier = category.get("_id", "")
				# name = category.get("name", "")
				# plutoOfficeOnly = category.get("plutoOfficeOnly", False)
				# kidsMode = category.get("plutoOfficeOnly", False)
				# page = category.get("page", 0)
				# offset = category.get("offset", 0)
				# totalItemsCount = category.get("totalItemsCount", 0)
				# mainCategories = category.get("mainCategories", [{}])  # List of dictionaries with key "categoryID" (typically only one entry defined).
				# items = category.get("items", [{}])  # List of dictionaries of the items in this category.
				# hero_carousel = category.get("hero_carousel", False)  # Only present when True, usually only one occurrence.
				categoryIdentifier = category.get("_id", "")
				categoryName = category.get("name", "")
				self.categories[categoryIdentifier] = []
				self.categoryMenu.append((categoryIdentifier, categoryName, int(category.get("totalItemsCount", "0"))))
				items = category.get("items", [])
				for item in items:
					# identifier = item.get("_id", "")
					# seriesID = item.get("seriesID", "")
					# slug = item.get("slug", "")
					# name = item.get("name", "")
					# summary = item.get("summary", "")
					# description = item.get("description", "")
					# duration = item.get("duration", 0)
					# originalContentDuration = item.get("originalContentDuration", 0)
					# allotment = item.get("allotment", 0)
					# rating = item.get("rating", "")
					# featuredImage = item.get("featuredImage", {})  # Typically key "path" as a URL to a background or screen shot image.
					# genre = item.get("genre", "")
					# type = item.get("type", "")
					# seasonsNumbers = item.get("seasonsNumbers", [])  # Typically a list of numeric season numbers.
					# stitched = item.get("stitched", {})  # Typically keys "urls" and "sessionURL" with "urls" a list of dictionaries with keys "type" and "url".
					# covers = item.get("covers", [{}])  # Typically a list of dictionaries with keys "aspectRatio" and "url".
					# kidsMode = item.get("kidsMode", False)
					# ratingDescriptors = item.get("ratingDescriptors", [])  # Typically a list of strings.
					# poweredByViaFree = item.get("poweredByViaFree", False)
					# poster16_9 = item.get("poster16_9", {})  # Typically key "path" as a URL to a background or promotional image.
					# clip = item.get("clip", {})  # Typically keys "actors"[], "writers"[], "directors"[], producers"[] and "originalReleaseDate".
					# entitlements = item.get("entitlements", [])  # Typically a list of strings, usually not present.
					# avail = item.get("avail", {}) Typically a dictionary of strings, usually empty.
					# ad = item.get("ad", False)
					# cc = item.get("cc", False)  # Only present when True.
					identifier = item.get("_id", "")
					if not identifier:
						continue
					mediaType = item.get("type", "")
					if mediaType == "movie":
						urls = item.get("stitched", {}).get("urls")
						if not isinstance(urls, list) or not urls:
							continue
					else:
						urls = []
					rating = item.get("rating", "")
					if rating.isdigit():
						rating = f"FSK-{rating}"
					covers = item.get("covers", [])
					coversLength = len(covers)
					poster = ""
					image = ""
					if coversLength > 2:
						image = covers[2].get("url", "")
					if coversLength > 1 and len(image) == 0:
						image = covers[1].get("url", "")
					if coversLength > 0:
						poster = covers[0].get("url", "")
					self.categories[categoryIdentifier].append((
						identifier,  # CATEGORY_IDENTIFIER.
						item.get("name", ""),  # CATEGORY_NAME.
						item.get("summary", ""),  # CATEGORY_SUMMARY.
						item.get("description", ""),  # CATEGORY_DESCRIPTION.
						item.get("genre", ""),  # CATEGORY_GENRE.
						rating,  # CATEGORY_RATING.
						int(item.get("duration", "0")) // 1000,  # CATEGORY_DURATION (In seconds).
						poster,  # CATEGORY_POSTER.
						image,  # CATEGORY_IMAGE.
						mediaType,  # CATEGORY_MEDIATYPE.
						urls[0].get("url", "") if urls else "",  # CATEGORY_URL.
						item.get("seasonsNumbers", []) or [],  # CATEGORY_SEASONS.
						item.get("clip", {}),  # CATEGORY_CLIP.
						item.get("cc", False)  # CATEGORY_CAPTIONS.
					))
			self.setTitle(f"{self.baseTitle} - {"" if self.region == "AUTO" else f"{PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]} "}{_("VOD Categories Menu")}")
			self["menu"].setList([self.buildMenuEntry(x[0], x[1], "menu", x[2]) for x in self.categoryMenu])
			self["loading"].hide()
			self["menuActions"].setEnabled(True)
		else:
			print("[PlutoTV] No VOD categories found.")
			self["loading"].setText(f"{_("Error: No VOD categories available!")}\n\n\n\n{_("Pluto TV may not be available in your location.")}")
			self["menuActions"].setEnabled(False)

	def buildMenuEntry(self, identifier, name, menuType, count="", episode=0):
		def showProgress(media):
			icon = f"pluto_{media}_unwatched.png"
			sid = episode if menuType == "episode" else identifier
			if sid:
				last, length = getResumePoint(sid)
				if last and (last > 900000) and (not length or (last < length - 900000)):
					icon = f"pluto_{media}_started.png"
				elif last and last >= length - 900000:
					icon = f"pluto_{media}_watched.png"
			return icon

		match menuType:
			case "episode":
				icon = showProgress("tv")
			case "menu":
				icon = "pluto_menu.png"
			case "movie":
				icon = showProgress("movie")
			case "seasons":
				icon = "pluto_seasons.png"
			case "series":
				icon = "pluto_series.png"
			case _:
				icon = None
				print(f"[PlutoTV] Error: Unxpected menu entry type '{menuType}'!")
		count = str(count) if isinstance(count, int) else "\u25B6" if menuType in ("episode", "movie") else ""  # Display count or PLAY icon or nothing.
		if icon:
			iconPath = resolveFilename(SCOPE_GUISKIN, f"images/{icon}")
			if not isfile(iconPath):
				iconPath = resolveFilename(SCOPE_PLUGIN_ABSOLUTE, f"images/{icon}")
			icon = LoadPixmap(iconPath) if isfile(iconPath) else None
		else:
			iconPath = None
		# print(f"[PlutoTV] buildMenuEntry DEBUG: name='{name}', count='{count.replace("\u25B6", ">")}', icon={iconPath}, menuType='{menuType}', identifier='{identifier}', episode='{episode}'.")
		return (name, count, icon, menuType, identifier, episode)

	def getTimedPoster(self):
		def getPoster(path, url):
			def getPosterDone(path):
				def showPoster(picInfo=None):
					try:
						image = self.picLoad.getData()
						if image:
							self["poster"].instance.setPixmap(image.__deref__())
							self["poster"].instance.show()
					except Exception as err:
						print(f"[PlutoTV] showPoster Error: '{err}'!")

				try:
					pictureData = self.picLoad.PictureData.get()
					del pictureData[:]
					pictureData.append(showPoster)
					self.picLoad.startDecode(path)
				except Exception as err:
					print(f"[PlutoTV] getPosterDone Error: '{err}'!")

			def getPosterError(error, path=None, url=""):
				print(f"[PlutoTV] Error: Unable to get poster image!  (Error='{error}', Path='{path}', URL='{url}')")
				if url.endswith("/poster.jpg?h=640&w=480"):
					url = url.replace("/poster.jpg?h=640&w=480", "/tile.jpg?h=480&w=480")
					return getPoster(path, url)
				else:
					self["poster"].hide()

			if isfile(path):
				# print(f"[PlutoTV] getPoster DEBUG: Using cached poster '{path}' from '{url}'.")
				getPosterDone(path)  # Use poster already cached.
			else:
				# print(f"[PlutoTV] getPoster DEBUG: Fetch poster '{path}' from '{url}'.")
				PlutoDownloader().start(path, url).addCallback(getPosterDone).addErrback(getPosterError, path, url)  # Fetch poster.

		path, url = self.postersToDownload[-1]
		self.postersToDownload.clear()
		path = path.rstrip()
		if path:
			if url.endswith(".jpg"):
				url = f"{url}?h=640&w=480"
			getPoster(path, url)

	def selectionChanged(self):
		def getPoster(path, url):
			self.postersToDownload.append((path, url))
			self.posterTimer.start(250, True)

		def processDetails(description, genre, rating, duration, original, clip):
			if description:
				details.append(rf"\c{detailsLabel.detailsColor:08X}{description}\c{detailsLabel.detailsColor:08X}")
			section = []
			if genre:
				section.append(rf"\c{detailsLabel.genreColor:08X}{_("Genre")}: {genre}\c{detailsLabel.detailsColor:08X}")
			if rating:
				section.append(rf"\c{detailsLabel.ratingColor:08X}{_("Rating")}: {rating}\c{detailsLabel.detailsColor:08X}")
			if duration:
				original = f"  ({_("Original")}: {strftime("%H:%M", gmtime(original))})" if original else ""
				section.append(rf"\c{detailsLabel.durationColor:08X}{_("Duration")}: {strftime("%H:%M", gmtime(duration))}{original}\c{detailsLabel.detailsColor:08X}")
			if section:
				if details:
					details.append("")
				details.append("\n".join(section))
			if clip:
				section = []
				if "actors" in clip:
					# data = ", ".join(clip["actors"])
					# details.append(f"{ngettext("Actor", "Actors", len(data))}: {", ".join(data)}.")
					section.append(rf"\c{detailsLabel.actorsColor:08X}{_("Cast")}: {", ".join(clip["actors"])}.\c{detailsLabel.detailsColor:08X}")
				if "writers" in clip:
					data = clip["writers"]
					section.append(rf"\c{detailsLabel.writersColor:08X}{ngettext("Writer", "Writers", len(data))}: {", ".join(data)}.\c{detailsLabel.detailsColor:08X}")
				if "directors" in clip:
					data = clip["directors"]
					section.append(rf"\c{detailsLabel.directorsColor:08X}{ngettext("Director", "Directors", len(data))}: {", ".join(data)}.\c{detailsLabel.detailsColor:08X}")
				if "producers" in clip:
					data = clip["producers"]
					section.append(rf"\c{detailsLabel.producersColor:08X}{ngettext("Producer", "Producers", len(data))}: {", ".join(data)}.\c{detailsLabel.detailsColor:08X}")
				if "originalReleaseDate" in clip:
					data = strftime(config.usage.date.daylong.value, localtime(timegm(strptime(clip["originalReleaseDate"], "%Y-%m-%dT%H:%M:%SZ"))))
					section.append(rf"\c{detailsLabel.releaseColor:08X}{_("Original release")}: {data}.\c{detailsLabel.detailsColor:08X}")
				if section:
					if details:
						details.append("")
					details.append(("\n\n" if config.plugins.PlutoTV.separateDetails.value else "\n").join(section))

		def updateMovieDbButton(flag):
			text = (_("IMDb") if imdbAvailable else _("TMDb") if tmdbAvailable else "") if flag else ""
			self["key_green"].setText(text)
			self["movieDbAction"].setEnabled(text != "")

		detailsLabel = self["details"]
		menuData = self.getMenuSelection()
		index = menuData[self.MENU_INDEX]
		match menuData[self.MENU_TYPE]:
			case "empty" | "menu":
				self["name"].hide()
				self["poster"].hide()
				self["details"].hide()
				updateMovieDbButton(False)
				self.updateFavoriteButton(None)
			case "episode":
				episode = self.episodes[menuData[self.MENU_IDENTIFIER]][index]
				details = []
				number = episode[self.EPISODE_NUMBER]
				season = episode[self.EPISODE_SEASON]
				if number and season:
					details.append(rf"\c{detailsLabel.episodeColor:08X}{self.seasonText} {season} - {_("Episode")} {number}\c{detailsLabel.detailsColor:08X}")
					if config.plugins.PlutoTV.separateEpisode.value:
						details.append("")
				data = episode[self.EPISODE_NAME]
				if data:
					details.append(rf"\c{detailsLabel.episodeColor:08X}{data}\c{detailsLabel.detailsColor:08X}")
					if config.plugins.PlutoTV.separateEpisode.value:
						details.append("")
				processDetails(episode[self.EPISODE_DESCRIPTION], episode[self.EPISODE_GENRE], episode[self.EPISODE_RATING], episode[self.EPISODE_DURATION], episode[self.EPISODE_ORIGINAL_DURATION], episode[self.EPISODE_CLIP])
				self["details"].setText("\n".join(details))
				self["details"].show()
				updateMovieDbButton(False)
				self.updateFavoriteButton(None)
			case "movie":
				film = self.films[index]
				self["name"].setText(film[self.CATEGORY_NAME])
				self["name"].show()
				data = f"{film[self.CATEGORY_IDENTIFIER]}.jpg"
				if len(data) > 5:
					posterURL = film[self.CATEGORY_POSTER]
					posterURL = urlparse(posterURL)
					posterURL = urljoin(PLUTO_IMAGE_URL, posterURL.path.replace("/v3/images", ""))
					getPoster(join(PLUTO_FOLDER, data), posterURL)
				self["poster"].hide()  # Disable this to keep the previous image visible until the new image is loaded!
				details = []
				processDetails(film[self.CATEGORY_SUMMARY], film[self.CATEGORY_GENRE], film[self.CATEGORY_RATING], film[self.CATEGORY_DURATION], None, film[self.CATEGORY_CLIP])
				detailsLabel.setText("\n".join(details))
				detailsLabel.show()
				updateMovieDbButton(True)
				self.updateFavoriteButton(film[self.CATEGORY_IDENTIFIER] in self.favorites[self.region])
			case "seasons":
				seasons = list(self.episodes.keys())
				details = self.details[:]
				details.append(rf"\c{detailsLabel.seasonColor:08X}{self.seasonText} {seasons[index]} contains {len(self.episodes[seasons[index]])} episodes\c{detailsLabel.detailsColor:08X}")
				detailsLabel.setText("\n".join(details))
				detailsLabel.show()
				updateMovieDbButton(False)
				self.updateFavoriteButton(None)
			case "series":
				film = self.films[index]
				self["name"].setText(film[self.CATEGORY_NAME])
				self["name"].show()
				data = f"{film[self.CATEGORY_IDENTIFIER]}.jpg"
				if len(data) > 5:
					posterURL = film[self.CATEGORY_POSTER]
					posterURL = urlparse(posterURL)
					posterURL = urljoin(PLUTO_IMAGE_URL, posterURL.path.replace("/v3/images", ""))
					getPoster(join(PLUTO_FOLDER, data), posterURL)
				self["poster"].hide()  # Disable this to keep the previous image visible until the new image is loaded!
				details = []
				processDetails(film[self.CATEGORY_SUMMARY], film[self.CATEGORY_GENRE], film[self.CATEGORY_RATING], film[self.CATEGORY_DURATION], None, film[self.CATEGORY_CLIP])
				data = len(film[self.CATEGORY_SEASONS])
				details.append("")
				self.details = details
				details.append(rf"\c{detailsLabel.seriesColor:08X}{data} {ngettext("Season available", "Seasons available", data)}\c{detailsLabel.detailsColor:08X}")
				detailsLabel.setText("\n".join(details))
				detailsLabel.show()
				updateMovieDbButton(True)
				self.updateFavoriteButton(film[self.CATEGORY_IDENTIFIER] in self.favorites[self.region])
		self["footnote"].hide()

	def updateFavoriteButton(self, isFavorite):
		text = "" if isFavorite is None else (_("Delete Favorite") if isFavorite else _("Add Favorite"))
		self["key_yellow"].setText(text)
		self["favoriteAction"].setEnabled(text != "")

	def keyClose(self):
		def keyCloseCallback(answer):
			if answer:
				self.posterTimer.stop()
				if self.oldService:
					self.session.nav.playService(self.oldService)
				self.close()

		if config.plugins.PlutoTV.confirmClose.value:
			self.session.openWithCallback(keyCloseCallback, MessageBox, _("Do you want to close Pluto TV?"), type=MessageBox.TYPE_YESNO, windowTitle=self.baseTitle)
		else:
			keyCloseCallback(True)

	def keyCloseRecursive(self):
		self.posterTimer.stop()
		if self.oldService:
			self.session.nav.playService(self.oldService)
		self.close((True,))

	def keySetup(self):
		def keySetupCallback(result=None):
			if config.plugins.PlutoTV.region.value != self.region:
				self.region = config.plugins.PlutoTV.region.value
				self.setTitle(self.baseTitle)
				self["loading"].setText(self.loadingMsg)
				self["loading"].show()
				self.categoryTimer.start(25, True)

		self.session.openWithCallback(keySetupCallback, PlutoSetup)

	def keySelect(self):
		def playVOD(url, name, identifier):
			url = updateQuery(url, {
				"deviceId": DEVICEID1_HEX,
				"sid": DEVICEID1_HEX,
				"deviceType": "web",
				"deviceMake": "Firefox",
				"deviceModel": "Firefox",
				"appName": "web"
			})
			serviceReference = eServiceReference(f"4097:0:0:0:0:0:0:0:0:0:{url.replace(":", "%3A")}:{name.replace(":", "%3A")}")
			if "m3u8" in url.lower():
				self.session.open(PlutoPlayer, serviceReference, identifier)

		menuData = self.getMenuSelection()
		index = menuData[self.MENU_INDEX]
		name = menuData[self.MENU_NAME]
		menuType = menuData[self.MENU_TYPE]
		identifier = menuData[self.MENU_IDENTIFIER]
		if menuType not in ("empty", "episode", "movie"):  # These do not lead to a sub-menu.
			self.history.append((self.getTitle(), index, menuType))
		self["key_red"].setText(_("Back"))
		self["previousMenuAction"].setEnabled(True)
		match menuType:
			case "empty":
				pass
			case "episode":
				episode = self.episodes[identifier][index]
				playVOD(episode[self.EPISODE_URL], episode[self.EPISODE_NAME], episode[self.EPISODE_IDENTIFIER])
			case "menu":
				self.films = self.categories[self.categoryMenu[index][0]]
				if len(self.films):
					self["menu"].setList([self.buildMenuEntry(x[self.CATEGORY_IDENTIFIER], x[self.CATEGORY_NAME], x[self.CATEGORY_MEDIATYPE], len(x[self.CATEGORY_SEASONS]) or "") for x in self.films])
				else:
					self["menu"].setList([self.buildMenuEntry(0, _("** No favorites available **"), "empty")])
				self["menu"].setCurrentIndex(0)
				self.setTitle(f"{self.baseTitle} - {name}")
				self.inFavoritesMenu = name == self.FAVORITES_NAME
			case "movie":
				film = self.films[index]
				playVOD(film[self.CATEGORY_URL], film[self.CATEGORY_NAME], film[self.CATEGORY_IDENTIFIER])
			case "seasons":
				if identifier in self.episodes.keys():
					menu = [self.buildMenuEntry(identifier, f"{x[self.EPISODE_NUMBER]}: {x[self.EPISODE_NAME]}", "episode", "", x[self.EPISODE_IDENTIFIER]) for x in self.episodes[identifier]]
				else:
					menu = [self.buildMenuEntry(0, _("** No episodes available **"), "empty")]
				self["menu"].setList(menu)
				self["menu"].setCurrentIndex(0)
				self.setTitle(f"{self.baseTitle} - {self.getTitle().split(" - ")[1]} - {name}")
			case "series":
				header = buildHeader(PLUTO_DATA[self.region][PLUTO_IP])
				param = {
					"includeItems": "true",
					"deviceType": "web",
					"deviceId": DEVICEID1_HEX,
					"sid": SID1_HEX,
				}
				series = fetchURL(PLUTO_SEASON_URL % identifier, header=header, param=param)
				# seriesDump(self.region, series)
				# identifier = series.get("_id", "")
				# name = series.get("name", "")
				# summary = series.get("summary", "")
				# description = series.get("description", "")
				# slug = series.get("slug", "")
				# type = series.get("type", "")
				# rating = series.get("rating", "")
				# featuredImage = series.get("featuredImage", {})  # Typically key "path" as a URL to a background or screen shot image.
				# genre = series.get("genre", "")
				# offset = series.get("offset", 0)
				# page = series.get("page", 0)
				# seasons = series.get("seasons", [])  # List of dictionaries of the items in this season.
				# covers = series.get("covers", [])  # Typically a list of dictionaries with keys "aspectRatio" and "url".
				# poster16_9 = series.get("poster16_9", {})  # Typically key "path" as a URL to a background or promotional image.
				# avail = series.get("avail", {})  # Typically an empty dictionary.
				self.episodes.clear()
				for season in series.get("seasons", []):
					# episodes = season.get("episodes", [])  # List of dictionaries of the episodes in this season.
					# number = season.get("number", 0)
					for episode in (season.get("episodes", [])):
						# identifier = episode.get("_id", "")
						# name = episode.get("name", "")
						# description = episode.get("description", "")
						# allotment = episode.get("allotment", 0)
						# rating = episode.get("rating", "")
						# slug = episode.get("slug", "")
						# duration = episode.get("duration", 0)
						# originalContentDuration = episode.get("originalContentDuration", 0)
						# genre = episode.get("genre", "")
						# type = episode.get("type", "")
						# number = episode.get("number", 0)
						# season = episode.get("season", 0)
						# stitched = episode.get("stitched", {})  # Typically keys "urls" and "sessionURL" with "urls" a list of dictionaries with keys "type" and "url".
						# covers = episode.get("covers", [])  # Typically a list of dictionaries with keys "aspectRatio" and "url".
						# poster16_9 = episode.get("poster16_9", {})  # Typically key "path" as a URL to a background or promotional image.
						# clip = episode.get("clip", {})  # Typically keys "actors"[], "writers"[], "directors"[], producers"[] and "originalReleaseDate".
						# cc = episode.get("cc", False)
						season = int(episode.get("season", "0") or "0")
						if season:
							if season not in self.episodes:
								self.episodes[season] = []
							urls = episode.get("stitched", {}).get("urls", [])
							if len(urls) > 0:
								url = urls[0].get("url", "")
							else:
								continue
							covers = episode.get("covers", [])
							coversLength = len(covers)
							poster = ""
							image = ""
							if coversLength > 2:
								image = covers[2].get("url", "")
							if coversLength > 1 and len(image) == 0:
								image = covers[1].get("url", "")
							if coversLength > 0:
								poster = covers[0].get("url", "")
							self.episodes[season].append((
								episode.get("_id", ""),  # EPISODE_IDENTIFIER.
								episode.get("name", ""),  # EPISODE_NAME.
								episode.get("number", "0"),  # EPISODE_NUMBER.
								episode.get("season", "0"),  # EPISODE_SEASON.
								episode.get("description", ""),  # EPISODE_DESCRIPTION.
								episode.get("rating", ""),  # EPISODE_RATING.
								int(episode.get("duration", "0") or "0") // 1000,  # EPISODE_DURATION.
								int(episode.get("originalContentDuration", "0") or "0") // 1000,  # EPISODE_ORIGINAL_DURATION.
								episode.get("genre", ""),  # EPISODE_GENRE.
								poster,  # EPISODE_POSTER.
								image,  # EPISODE_IMAGE.
								url,  # EPISODE_URL.
								episode.get("clip", {})  # EPISODE_CLIP.
							))
				if self.episodes:
					menu = [self.buildMenuEntry(x, f"{self.seasonText} {x}", "seasons", len(self.episodes[x]) or "") for x in self.episodes.keys()]
					count = len(menu)
				else:
					menu = [self.buildMenuEntry(0, _("** No seasons available **"), "empty")]
					count = 0
				self["menu"].setList(menu)
				self["menu"].setCurrentIndex(0)
				self.setTitle(f"{self.baseTitle} - {series.get("name", "")} - {ngettext("Season", "Seasons", count)}")

	def keyMovieDatabase(self):
		menuData = self.getMenuSelection()
		name = menuData[self.MENU_NAME]
		if imdbAvailable:
			try:
				imdb(self.session, name)
			except Exception as err:
				print(f"[PlutoTV] Error: Unable to retrieve IMDb data for '{name}'!  ({err})")
		elif tmdbAvailable:
			try:
				self.session.open(tmdb.tmdbScreen, name, 0)
			except Exception as err:
				print(f"[PlutoTV] Error: Unable to retrieve TMDb data for '{name}'!  ({err})")

	def keyFavorite(self):
		menuData = self.getMenuSelection()
		identifier = menuData[self.MENU_IDENTIFIER]
		name = menuData[self.MENU_NAME]
		index = menuData[self.MENU_INDEX]
		if identifier in self.favorites[self.region]:
			del self.favorites[self.region][identifier]
			print(f"[PlutoTV] {PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]} favorite '{name}' deleted.")
			self.updateFavoriteButton(False)
			text = _("%s favorite deleted.") % PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]
		else:
			film = self.films[index]
			if self.region not in self.favorites:
				self.favorites[self.region] = {}
			self.favorites[self.region][film[self.CATEGORY_IDENTIFIER]] = film
			print(f"[PlutoTV] {PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]} favorite '{name}' added.")
			self.updateFavoriteButton(True)
			text = _("%s favorite added.") % PLUTO_DATA[self.region][PLUTO_COUNTRY_NAME]
		self.favoritesModified = True
		self.categoryMenu[0] = (self.FAVORITES_NAME, self.FAVORITES_NAME, len(self.favorites[self.region]))  # This assumes that the favorites menu item is *always* first!
		favorites = [self.favorites[self.region][x] for x in self.favorites[self.region].keys()]
		self.categories[self.FAVORITES_NAME] = favorites
		if self.inFavoritesMenu:
			if favorites:
				self["menu"].setList([self.buildMenuEntry(x[self.CATEGORY_IDENTIFIER], x[self.CATEGORY_NAME], x[self.CATEGORY_MEDIATYPE], len(x[self.CATEGORY_SEASONS]) or "") for x in favorites])
			else:
				self["menu"].setList([self.buildMenuEntry(0, _("** No favorites available **"), "empty")])
				self.selectionChanged()
		self["footnote"].setText(text)
		self["footnote"].show()

	def keyPreviousMenu(self, top=False):
		if not self.history:
			self.keyClose()
		else:
			if top:
				history = self.history[0]
				self.history.clear()
			else:
				history = self.history.pop()
			match history[self.HISTORY_TYPE]:
				case "menu":
					self["name"].hide()
					self["details"].hide()
					menu = [self.buildMenuEntry(x[0], x[1], "menu", x[2]) for x in self.categoryMenu]
				case "seasons":
					menu = [self.buildMenuEntry(x, f"{self.seasonText} {x}", "seasons", len(self.episodes[x]) or "") for x in self.episodes.keys()]
				case "series":
					menu = [self.buildMenuEntry(x[self.CATEGORY_IDENTIFIER], x[self.CATEGORY_NAME], x[self.CATEGORY_MEDIATYPE], len(x[self.CATEGORY_SEASONS]) or "") for x in self.films]
				case _:
					menu = [self.buildMenuEntry(0, _("** Unexpected menu type '%s'!") % history[self.HISTORY_TYPE], "empty", "")]
					print(f"Unexpected menu type '{history[self.HISTORY_TYPE]}'!")
			self["menu"].setList(menu)
			self["menu"].setCurrentIndex(history[self.HISTORY_INDEX])
			self.setTitle(history[self.HISTORY_TITLE])
			if self.history:
				self["key_red"].setText(_("Back"))
				self["previousMenuAction"].setEnabled(True)
			else:
				self["key_red"].setText(_("Close"))
				self["previousMenuAction"].setEnabled(False)

	def keyTopMenu(self):
		self.keyPreviousMenu(top=True)

	def keySelectRegion(self):
		def keySelectRegionCallback(answer):
			if answer and answer != self.region:
				self.region = answer
				self.setTitle(self.baseTitle)
				self["loading"].setText(self.loadingMsg)
				self["loading"].show()
				self.categoryTimer.start(25, True)

		selectionList = [(x[1], x[0]) for x in config.plugins.PlutoTV.region.getSelectionList()]
		selectionIndex = config.plugins.PlutoTV.region.getIndex()
		self.session.openWithCallback(keySelectRegionCallback, MessageBox, _("Select the VOD region to be viewed:"), MessageBox.TYPE_YESNO, list=selectionList, default=selectionIndex, windowTitle=self.baseTitle)

	def getMenuSelection(self):
		# print(f"[PlutoTV] getMenuSelection DEBUG: Count={self["menu"].count()}, Index={self["menu"].getCurrentIndex()}, Entry={self["menu"].getCurrent()}")
		return (self["menu"].getCurrentIndex(),) + self["menu"].getCurrent()


class PlutoDownloader:
	def start(self, filename, sourcefile, overwrite=False):
		def downloadWithRequests(url, filename, timeout=30):
			def download():
				try:
					if "missing.png" in url or "MISSING" in url:
						# print("[PlutoTV] Don't bother fetching the 'missing.png' or 'MISSING' picons!")
						pass
					else:
						response = get(url, timeout=timeout)
						response.raise_for_status()
						with open(filename, 'wb') as fd:
							fd.write(response.content)
					return filename
				except Exception as err:
					print(f"[PlutoTV] download DEBUG: Error in download!  ({err})")

			try:
				return threads.deferToThread(download)
			except Exception as err:
				print(f"[PlutoTV] downloadWithRequests DEBUG: Error in deferToThread!  ({err})")

		try:
			if not filename or not sourcefile:
				return defer.fail(Exception("[PlutoTV] PlutoDownloader Error: Wrong arguments!"))
			if not overwrite and exists(filename) and getsize(filename):
				return defer.succeed(filename)
			return downloadWithRequests(sourcefile, filename, timeout=30).addCallback(self.downloadDone, filename).addErrback(self.downloadFail, sourcefile)
		except Exception as err:
			print(f"[PlutoTV] start DEBUG: Error in download!  ({err})")

	def downloadDone(self, result, path):
		# print(f"[PlutoTV] PlutoDownloader DEBUG: File '{path}' downloaded.")
		try:
			if not getsize(path):
				raise Exception(f"[PlutoTV] downloadDone Error: File '{path}' is empty!")
		except OSError as err:
			raise (err)
		else:
			return path

	def downloadFail(self, error, path):
		print(f"[PlutoTV] downloadFail Error: Failed to download '{path}'!  ({error})")
		return error


class PlutoSetup(Setup):
	def __init__(self, session):
		self.choices = list(PLUTO_DATA.keys())
		self.baseConfigLength = None
		Setup.__init__(self, session=session, setup="PlutoTV", plugin="Extensions/PlutoTV", PluginLanguageDomain="PlutoTV")
		self["key_yellow"] = StaticText()
		self["key_blue"] = StaticText()
		description = _("Pluto TV Actions")
		self["manageAction"] = HelpableActionMap(self, ["ColorActions"], {
			"yellow": (self.keyManageBouquet, _("Add/Delete a Pluto TV bouquet"))
		}, prio=0, description=description)
		self["bouquetAction"] = HelpableActionMap(self, ["ColorActions"], {
			"blue": (self.keyUpdateBouquets, _("Remove a Pluto TV bouquet"))
		}, prio=0, description=description)
		self.initialRegions = self.buildRegionList()

	def buildRegionList(self):
		regions = []
		for index in range(config.plugins.PlutoTV.bouquetCount.value):
			regions.append(config.plugins.PlutoTV.bouquetRegion[index].value)
		return sorted(regions)

	def updateControls(self):
		current = self["config"].getCurrent()
		if len(current) > 3:
			self["key_yellow"].setText(_("Delete Bouquet"))
			self["manageAction"].setEnabled(True)
		else:
			if self.getChoices():
				self["key_yellow"].setText(_("Add Bouquet"))
			else:
				self["key_yellow"].setText("")
				self["manageAction"].setEnabled(False)
		if config.plugins.PlutoTV.bouquetCount.value:
			self["key_blue"].setText(_("Update Bouquets"))
			self["bouquetAction"].setEnabled(True)
		else:
			self["key_blue"].setText("")
			self["bouquetAction"].setEnabled(False)
		if len(current) > 3 and config.plugins.PlutoTV.bouquetCount.value:
			last = int(fileReadLine(PLUTO_TIMER_PATH, default="0", source=MODULE_NAME))
			self.setFootnote(f"{_("Pluto TV bouquets last updated")} {strftime(f"{config.usage.date.daylong.value}  {config.usage.time.long.value}", localtime(last))}")

	def getChoices(self, choice=None):
		choices = self.choices[:]
		for index in range(config.plugins.PlutoTV.bouquetCount.value):
			value = config.plugins.PlutoTV.bouquetRegion[index].value
			if choice != value and value in choices:
				choices.remove(value)
		return sorted([(x, PLUTO_DATA[x][PLUTO_COUNTRY_NAME]) for x in choices], key=lambda x: x[1])

	def keyManageBouquet(self):
		current = self["config"].getCurrent()
		if len(current) > 3:
			config.plugins.PlutoTV.bouquetCount.value -= 1
			config.plugins.PlutoTV.bouquetRegion.pop(current[3])
			config.plugins.PlutoTV.bouquetService.pop(current[3])
			index = self["config"].getCurrentIndex()
			self.createSetup()
			length = self.baseConfigLength + (config.plugins.PlutoTV.bouquetCount.value * 2) if config.plugins.PlutoTV.bouquetCount.value else self.baseConfigLength - 1
			if index >= length:
				index = length
		else:
			choices = self.getChoices()
			config.plugins.PlutoTV.bouquetCount.value += 1
			default = list(choices)[0]
			config.plugins.PlutoTV.bouquetRegion.append(ConfigSelection(default=default, choices=choices))
			config.plugins.PlutoTV.bouquetRegion[-1].value = default
			config.plugins.PlutoTV.bouquetService.append(ConfigSelection(default="4097", choices=PLUTO_SERVICE_CHOICES))
			self.createSetup()
			index = self.baseConfigLength + (config.plugins.PlutoTV.bouquetCount.value * 2) - 1
		self["config"].setCurrentIndex(index)
		self.updateControls()

	def keyUpdateBouquets(self):
		def keyUpdateBouquetsCallback():
			# if config.plugins.PlutoTV.updateTimer.value:  # isfile(PLUTO_TIMER_PATH):
			# 	self.setFootnote(_("Pluto TV bouquets will be updated again in %s hours.") % config.plugins.PlutoTV.updateTimer.value)
			self.updateControls()

		self.session.openWithCallback(keyUpdateBouquetsCallback, PlutoUpdate)

	def layoutFinished(self):
		Setup.layoutFinished(self)
		self.updateControls()

	def createSetup(self):
		Setup.createSetup(self)
		configList = self["config"].getList()
		if self.baseConfigLength is None:
			self.baseConfigLength = len(configList)
		configList = configList[:self.baseConfigLength]
		if config.plugins.PlutoTV.bouquetCount.value:
			configList.append(getConfigListEntry(_("--- Pluto TV Bouquets ---")))
			for count in range(config.plugins.PlutoTV.bouquetCount.value):
				configList.append(getConfigListEntry(_("Bouquet %s region") % (count + 1), config.plugins.PlutoTV.bouquetRegion[count], _("Select the region for which a bouquet will be created."), count, True))
				configList.append(getConfigListEntry((_("Bouquet %s service type") % (count + 1), 1), config.plugins.PlutoTV.bouquetService[count], _("Select the service type to be used for the region bouquet."), count, False))
		self["config"].setList(configList)

	def selectionChanged(self):
		Setup.selectionChanged(self)
		current = self["config"].getCurrent()
		if len(current) > 4 and current[4]:
			index = current[3]
			default = config.plugins.PlutoTV.bouquetRegion[index].value
			config.plugins.PlutoTV.bouquetRegion[index].setSelectionList(self.getChoices(default))
		self.updateControls()

	def keySave(self):
		def keySaveCallback():
			Setup.keySave(self)

		config.plugins.PlutoTV.bouquetCount.save()  # These are not in the basic ConfigList so need to be saved separately.
		config.plugins.PlutoTV.bouquetRegion.save()
		config.plugins.PlutoTV.bouquetService.save()
		if config.plugins.PlutoTV.piconMode.isChanged() or (config.plugins.PlutoTV.channelNumbering.isChanged() and config.plugins.PlutoTV.piconMode.value == "srp"):
			self.session.open(MessageBox, _("NOTE: Pluto TV picons should be deleted before the next bouquet update."), type=MessageBox.TYPE_INFO, timeout=10, windowTitle=self.getTitle())
		removeRegions = self.initialRegions[:]
		updateRegions = []
		for region in self.buildRegionList():
			if region in self.initialRegions:
				removeRegions.remove(region)
			else:
				updateRegions.append(region)
		if removeRegions:
			serviceHandler = eServiceCenter.getInstance()
			mutableList = serviceHandler.list(eServiceReference("1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"bouquets.tv\" ORDER BY bouquet")).startEdit()
			changed = False
			for region in removeRegions:
				print(f"[PlutoTV] Remove bouquet for region '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
				bouquetReference = eServiceReference(f"1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"userbouquet.pluto_tv_{region.lower()}.tv\" ORDER BY bouquet")
				if bouquetReference.valid() and mutableList is not None and not mutableList.removeService(bouquetReference):
					changed = True
			if changed:
				mutableList.flushChanges()
				eDVBDB.getInstance().reloadBouquets()
		if updateRegions:
			self.session.openWithCallback(keySaveCallback, PlutoUpdate, bouquetRegionList=updateRegions)
		else:
			Setup.keySave(self)

	def keyCancel(self):
		config.plugins.PlutoTV.bouquetCount.cancel()
		for index in range(len(config.plugins.PlutoTV.bouquetRegion)):  # These are not in the basic ConfigList so need to be canceled separately.
			config.plugins.PlutoTV.bouquetRegion[index].cancel()
			config.plugins.PlutoTV.bouquetService[index].cancel()
		Setup.keyCancel(self)


class PlutoPlayer(MoviePlayer):
	ENABLE_RESUME_SUPPORT = False  # Don't use Enigma2 resume support. We use our own resume support.

	def __init__(self, session, service, identifier):
		MoviePlayer.__init__(self, session, service)
		self.skinName = ["MoviePlayer"]
		self.identifier = identifier
		self.started = False
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			# iPlayableService.evStart: self.__serviceStarted, -> InfoBarCueSheetSupport
			iPlayableService.evBuffering: self.__serviceStarted,  # -> May not be needed.
			iPlayableService.evVideoSizeChanged: self.__serviceStarted  # -> May not be needed.
			# iPlayableService.evEOF: self.__evEOF, -> InfoBarSeek
		})
		self.session.nav.playService(service)

	def __serviceStarted(self):  # Overwrite method from InfoBarCueSheetSupport.
		service = self.session.nav.getCurrentService()
		seekable = service.seek()
		last, length = getResumePoint(self.identifier)
		if last is None or seekable is None:
			return
		length = seekable.getLength() or (None, 0)
		# print(f"[PlutoTV] DEBUG: seekable.getLength() returned '{length}'.")
		if (last > 900000) and (not length[1] or (last < length[1] - 900000)):  # This implies we don't resume if the length is unknown.
			self.resume_point = last
			last = int(last // 90000)
			if not self.started:
				self.started = True
				msg = []
				msg.append(_("Resume position at %s") % f"{last // 3600}:{last % 3600 // 60:02d}:{last % 60:02d}")
				msg.append("")
				msg.append(_("Do you want to resume playback?"))
				AddNotificationWithCallback(self.playLastCB, MessageBox, "\n".join(msg), timeout=10, default="yes" in config.usage.on_movie_start.value.lower())

	def doEofInternal(self, playing):  # Overwrite method from MoviePlayer.
		self.close()

	def leavePlayer(self):  # Overwrite method from MoviePlayer.
		def leavePlayerCallback(answer):
			if answer:
				self.is_closing = True
				setResumePoint(self.session, self.identifier)
				self.close()

		self.session.openWithCallback(leavePlayerCallback, MessageBox, _("Stop playing this movie?"), MessageBox.TYPE_YESNO, windowTitle=_("Pluto TV Movie Player"))

	def leavePlayerOnExit(self):  # Overwrite method from MoviePlayer.
		self.leavePlayer()


class PlutoUpdater:
	EXIT_IDLE = 0
	EXIT_DONE = 0
	EXIT_RUNNING = 1
	EXIT_ABORT = 2
	EXIT_ERROR = 3

	CHANNEL_NUMBER = 0
	CHANNEL_IDENTIFIER = 1
	CHANNEL_NAME = 2
	CHANNEL_PICON_URL = 3
	CHANNEL_SERVICE_URL = 4

	TV_SERVICE_TYPES = ("1:7:1:0:0:0:0:0:0:0:(type == 1) || (type == 17) || (type == 22) || (type == 25) || (type == 134) || (type == 195)")

	def __init__(self, verbose):
		self.verbose = verbose
		self.bouquetRegionList = []
		self.updateActive = False
		self.abort = False
		# self.timer = eTimer()
		# self.timer.callback.append(self.uiUpdate)

	def uiUpdate(self, action=None, progress=None, status=None, pause=0):
		if self.verbose:
			if action is not None:
				self.setTitle(action)
				self["action"].setText(action)
			if progress is not None:
				self["progress"].setValue(progress)
				self["percentage"].setText(f"{progress}%")
			if status is not None:
				self["status"].setText(status)
			# self.timer.start(1, True)
			if pause:
				sleep(pause)

	def updateThread(self):
		def assignNumber():
			nonlocal serviceNumbers, serviceNumbersModified
			if identifier in serviceNumbers:
				number = serviceNumbers[identifier]["number"]
			else:
				number = serviceNumbers["lastNumber"] + 1
				if number <= 65535:
					serviceNumbers["lastNumber"] = number
					number = f"{number:X}"  # Convert the number to hexadecimal.
					serviceNumbers[identifier] = {}
					serviceNumbers[identifier]["number"] = number
					serviceNumbers[identifier]["name"] = name
					serviceNumbersModified = True
				else:
					self.uiUpdate(status=_("Error: Generated channel number too big!  (%s)") % number)
					number = None
			# print(f"[PlutoTV] ALERT: Identifier '{identifier}, name '{name}' number '{number}'.")
			return number

		if self.updateActive:
			print("[PlutoTV] Carousel update is already in progress.")
			return self.EXIT_RUNNING
		self.updateActive = True
		self.abort = False
		print("[PlutoTV] Carousel update started.")
		result = self.EXIT_DONE
		bouquetRegionList = self.bouquetRegionList if self.bouquetRegionList else [x.value for x in config.plugins.PlutoTV.bouquetRegion]
		serviceTypes = {config.plugins.PlutoTV.bouquetRegion[x].value: config.plugins.PlutoTV.bouquetService[x].value for x in range(config.plugins.PlutoTV.bouquetCount.value)}
		categories = []
		channelList = {}
		guideList = {}
		addSamsung = config.plugins.PlutoTV.addSamsung.value
		if not addSamsung:
			print("[PlutoTV] Samsung categories will not being added.")
		addXiaomi = config.plugins.PlutoTV.addXiaomi.value
		if not addXiaomi:
			print("[PlutoTV] Xiaomi TV categories will not being added.")
		self.liveMode = config.plugins.PlutoTV.liveMode.value
		self.channelNumbering = config.plugins.PlutoTV.channelNumbering.value
		self.piconMode = config.plugins.PlutoTV.piconMode.value
		# print(f"[PlutoTV] DEBUG: bouquetRegionList={bouquetRegionList}.")
		# print(f"[PlutoTV] DEBUG: serviceTypes={serviceTypes}.")
		# print(f"[PlutoTV] DEBUG: addSamsung={addSamsung}.")
		# print(f"[PlutoTV] DEBUG: addXiaomi={addXiaomi}.")
		# print(f"[PlutoTV] DEBUG: self.liveMode='{self.liveMode}'.")
		# print(f"[PlutoTV] DEBUG: self.channelNumbering='{self.channelNumbering}'.")
		# print(f"[PlutoTV] DEBUG: self.piconMode='{self.piconMode}'.")
		try:
			epgCache = eEPGCache.getInstance()
			serviceNumbers = {"lastNumber": 0}
			serviceNumbersModified = False
			if isfile(PLUTO_SERVICE_NUMBER_PATH):
				print("[PlutoTV] Reading service numbers.")
				try:
					with open(PLUTO_SERVICE_NUMBER_PATH, "rb") as fd:
						serviceNumbers = load(fd)
				except OSError as err:
					print(f"[PlutoTV] Error {err.errno}: Unable to load service numbers '{PLUTO_SERVICE_NUMBER_PATH}'!  ({err.strerror})")
			for region in bouquetRegionList:
				if self.abort:
					break
				print(f"[PlutoTV] Fetching {PLUTO_DATA[region][PLUTO_COUNTRY_NAME]} carousel data.")
				progress = 0
				self.uiUpdate(action=_("Pluto TV Update - %s") % PLUTO_DATA[region][PLUTO_COUNTRY_NAME], progress=progress, status=_("Fetching %s carousel data.") % PLUTO_DATA[region][PLUTO_COUNTRY_NAME], pause=0.5)
				param = {
					"deviceId": DEVICEID1_HEX,
					"sid": SID1_HEX
				}
				header = buildHeader(PLUTO_DATA[region][PLUTO_IP])
				channels = sorted(fetchURL(PLUTO_LINEUP_URL, header=header, param=param), key=lambda x: x["number"])
				# channelsDump(region, channels)
				channelCount = len(channels)
				if self.abort:
					break
				print("[PlutoTV] Building category and channel lists.")
				progress += 1
				self.uiUpdate(progress=progress, status=_("Building category and channel lists."), pause=0.5)
				for channel in channels:
					# identifier = channel.get("_id", "")
					# slug = channel.get("slug", "")
					# name = channel.get("name", "")
					# hash = channel.get("hash", "")
					# number = channel.get("number", 0)
					# summary = channel.get("summary", "")
					# visibility = channel.get("visibility", "")
					# onDemandDescription = channel.get("onDemandDescription", "")
					# category = channel.get("category", "")
					# plutoOfficeOnly = channel.get("plutoOfficeOnly", False)
					# directOnly = channel.get("directOnly", False)
					# chatRoomId = channel.get("chatRoomId", -1)
					# cohortMask = channel.get("cohortMask", 0)
					# featuredImage = channel.get("featuredImage", {})  # Typically key "path" as a URL to a background or screen shot image.
					# thumbnail = channel.get("thumbnail", {})  # Typically key "path" as a URL to a background or screen shot image.
					# tile = channel.get("tile", {})  # Typically key "path" as a URL to a background or screen shot image.
					# logo = channel.get("logo", {})  # Typically key "path" as a URL to a background or screen shot image.
					# colorLogoSVG = channel.get("colorLogoSVG", {})  # Typically key "path" as a URL to a background or screen shot image.
					# colorLogoPNG = channel.get("colorLogoPNG", {})  # Typically key "path" as a URL to a background or screen shot image.
					# solidLogoSVG = channel.get("solidLogoSVG", {})  # Typically key "path" as a URL to a background or screen shot image.
					# solidLogoPNG = channel.get("solidLogoPNG", {})  # Typically key "path" as a URL to a background or screen shot image.
					# featured = channel.get("featured", False)
					# featuredOrder = channel.get("featuredOrder", 0)
					# favorite = channel.get("favorite", False)
					# isStitched = channel.get("isStitched", False)
					# stitched = channel.get("stitched", {})  # Typically keys "urls" and "sessionURL" with "urls" a list of dictionaries with keys "type" and "url".
					# tmsid = channel.get("tmsid", "")
					if self.abort:
						break
					category = channel.get("category", "")
					if (category == "Samsung" and not addSamsung) or (category == "Xiaomi TV" and not addXiaomi):
						continue
					urls = channel.get("stitched", {}).get("urls")
					if not isinstance(urls, list) or len(urls) == 0:
						print("[PlutoTV] Categories without URLs are not being added.")
						continue
					identifier = channel["_id"]
					match self.liveMode:
						case "original":
							url = [updateQuery(x["url"], {
								"deviceType": "web",
								"deviceMake": "Chrome",
								"deviceModel": "web",
								"appName": "web",
								"deviceId": "bc83a564-4b91-11ef-8a44-83c5e90e038f"
							}) for x in urls if x["type"].lower() == "hls"][0]
						case "roku":
							url = "&".join((
								f"https://stitcher-ipv4.pluto.tv/v1/stitch/embed/hls/channel/{identifier}/master.m3u8?deviceId=PSID",
								"deviceModel=web",
								"deviceVersion=1.0",
								"appVersion=1.0",
								"deviceType=rokuChannel",
								"deviceMake=rokuChannel",
								"deviceDNT=1"
							))
						case "samsung":
							url = "&".join((
								f"https://stitcher-ipv4.pluto.tv/v1/stitch/embed/hls/channel/{identifier}/master.m3u8?deviceType=samsung-tvplus",
								"deviceMake=samsung",
								"deviceModel=samsung",
								"deviceVersion=unknown",
								"appVersion=unknown",
								"deviceLat=0",
								"deviceLon=0",
								"deviceDNT=%7BTARGETOPT%7D",
								"deviceId=%7BPSID%7D",
								"advertisingId=%7BPSID%7D",
								"us_privacy=1YNY",
								"samsung_app_domain=%7BAPP_DOMAIN%7D",
								"samsung_app_name=%7BAPP_NAME%7D",
								"profileLimit=",
								"profileFloor=",
								"embedPartner=samsung-tvplus"
							))
					if category not in channelList.keys():
						categories.append(category)
						channelList[category] = []
					name = channel["name"]
					if self.channelNumbering == "original":
						match category:
							case "Samsung":
								number = identifier[-4:].upper().lstrip("0")
							case "Xiaomi TV":
								number = identifier[-4:].upper().lstrip("0")
							case _:
								number = channel.get("number", 0)
								if number:
									number = f"{int(number):X}"
								else:
									number = assignNumber()
									if number is None:
										result = self.EXIT_ERROR
										break
					else:
						number = assignNumber()
						if number is None:
							result = self.EXIT_ERROR
							break
					piconURL = channel.get("colorLogoPNG", {}).get("path", None)
					channelList[category].append((number, identifier, name, piconURL, url))
				if self.abort:
					break
				if categories:
					print(f"[PlutoTV] Building bouquet '{region}' for '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
					progress += 1
					self.uiUpdate(progress=progress, status=_("Building bouquet '%s' for '%s'.") % (region, PLUTO_DATA[region][PLUTO_COUNTRY_NAME]))
					bouquet = f"userbouquet.pluto_tv_{region.lower()}.tv"
					serviceReferences = {}
					bouquetData = []
					bouquetData.append(f"#NAME Pluto TV {region} (TV)")
					serviceType = serviceTypes[region]
					increment = 48.0 / channelCount  # This part of the processing constitutes 49% of the total progress.
					for counter, category in enumerate(categories):
						if self.abort:
							break
						bouquetData.append(f"#SERVICE 1:64:{counter}:0:0:0:0:0:0:0::{category}")
						if config.plugins.PlutoTV.addDescriptions.value:
							bouquetData.append(f"#DESCRIPTION {category}")
						for channel in channelList[category]:
							if self.abort:
								break
							number = channel[self.CHANNEL_NUMBER]
							name = channel[self.CHANNEL_NAME]
							progress += increment
							self.uiUpdate(progress=round(progress), status=_("Downloading '%s' picon.") % name, pause=0.1)
							tids = PLUTO_DATA[region][PLUTO_TIDS]
							bouquetData.append(f"#SERVICE {serviceType}:0:1:{number}:{tids}:0:0:0:0:0:{channel[self.CHANNEL_SERVICE_URL].replace(":", "%3A")}:{name.replace(":", "%3A")}")
							if config.plugins.PlutoTV.addDescriptions.value:
								bouquetData.append(f"#DESCRIPTION {name}")
							serviceReference = f"{serviceType}:0:1:{number}:{tids}:0:0:0:0:0"
							serviceReferences[channel[self.CHANNEL_IDENTIFIER]] = f"{serviceReference}:0"
							piconURL = f"{channel[self.CHANNEL_PICON_URL]}?w=220&h=132"  # Fetch the FHD resolution image.
							match self.piconMode:
								case "srp":
									piconBaseName = serviceReference.replace(":", "_")
								case "name":
									piconBaseName = str(name).replace("/", "_")
								case "snp":
									piconBaseName = normalize("NFKD", name).encode("ASCII", "ignore").decode()
									piconBaseName = sub(r"[^a-z0-9]", "", piconBaseName.replace("&", "and").replace("+", "plus").replace("*", "star").lower())
							piconPath = join(config.plugins.PlutoTV.piconPath.value, f"{piconBaseName}.png")
							# print(f"[PlutoTV] DEBUG: piconURL={piconURL}, piconBaseName={piconBaseName}, piconPath={piconPath}.")
							if "missing.png" in piconURL or "MISSING" in piconURL:
								# print("[PlutoTV] DEBUG: Don't try fetching the 'missing.png' or 'MISSING' picon!")
								copy2(resolveFilename(SCOPE_PLUGIN_ABSOLUTE, "images/pluto_picon.png"), piconPath)
							elif not isfile(piconPath) or config.plugins.PlutoTV.forcePiconDownload.value:
								# print(f"[PlutoTV] DEBUG: Fetching '{piconURL}' as picon '{piconPath}'.")
								try:
									response = get(piconURL, timeout=30)
									response.raise_for_status()
									with open(piconPath, 'wb') as fd:
										fd.write(response.content)
								except Exception as err:
									print(f"[PlutoTV] Error: Unable to download picon '{piconURL}' as '{piconPath}'!  ({err})")
									copy2(resolveFilename(SCOPE_PLUGIN_ABSOLUTE, "images/pluto_picon.png"), piconPath)
							# else:
							# 	print(f"[PlutoTV] DEBUG: Not fetching '{piconURL}' as picon '{piconPath}' already exists.")
					progress = round(progress)  # Eliminate any rounding errors and return progress back to an integer.
					if not self.abort:
						bouquetData.append("")
						fileWriteLines(resolveFilename(SCOPE_CONFIG, bouquet), bouquetData, source=MODULE_NAME)
					print(f"[PlutoTV] Fetching EPG for region '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
					self.uiUpdate(status=_("Fetching EPG data."), pause=0.5)
					startTime = gmtime()
					param = {
						"start": strftime("%Y-%m-%dT%H:00:00Z", startTime),
						"stop": strftime("%Y-%m-%dT%H:00:00Z", gmtime(timegm(startTime) + 86400)),  # UTC startTime + 24 Hours.
						"deviceId": DEVICEID1_HEX,
						"sid": SID1_HEX,
					}
					header = buildHeader(PLUTO_DATA[region][PLUTO_IP])
					# Does the list of guides data need to be sorted?
					guides = sorted(fetchURL(PLUTO_GUIDE_URL, header=header, param=param), key=lambda x: x["number"])
					# guidesDump(region, guides)
					guidesCount = len(guides)
					if self.abort:
						break
					# Why do we need to filter the guides?  Don't all entries have an identifier?
					for counter, guide in enumerate(filter(lambda x: x.get("_id"), guides)):
						# identifier = guide.get("_id", "")
						# slug = guide.get("slug", "")
						# name = guide.get("name", "")
						# hash = guide.get("hash", "")
						# number = guide.get("number", 0)
						# summary = guide.get("summary", "")
						# visibility = guide.get("visibility", "")
						# onDemandDescription = guide.get("onDemandDescription", "")
						# category = guide.get("category", "")
						# plutoOfficeOnly = guide.get("plutoOfficeOnly", False)
						# directOnly = guide.get("directOnly", False)
						# chatRoomId = guide.get("chatRoomId", -1)
						# onDemand = guide.get("onDemand", False)
						# cohortMask = guide.get("cohortMask", 0)
						# featuredImage = guide.get("featuredImage", {})  # Typically key "path" as a URL to a background or screen shot image.
						# thumbnail = guide.get("thumbnail", {})  # Typically key "path" as a URL to a background or promotional image.
						# tile = guide.get("tile", {})  # Typically key "path" as a URL to a background or promotional image.
						# tileGrayScale = guide.get("tileGrayScale", {})  # Typically key "path" as a URL to a background or promotional image.
						# logo = guide.get("logo", {})  # Typically key "path" as a URL to a background or promotional image.
						# colorLogoSVG = guide.get("colorLogoSVG", {})  # Typically key "path" as a URL to a background or promotional image.
						# colorLogoPNG = guide.get("colorLogoPNG", {})  # Typically key "path" as a URL to a background or promotional image.
						# solidLogoSVG = guide.get("solidLogoSVG", {})  # Typically key "path" as a URL to a background or promotional image.
						# solidLogoPNG = guide.get("solidLogoPNG", {})  # Typically key "path" as a URL to a background or promotional image.
						# featured = guide.get("featured", False)
						# featuredOrder = guide.get("featuredOrder", -1)
						# favorite = guide.get("favorite", False)
						# isStitched = guide.get("isStitched", False)
						# stitched = guide.get("stitched", {})  # Typically keys "urls" and "sessionURL" with "urls" a list of dictionaries with keys "type" and "url".
						# timelines = guide.get("timelines", [{}])
						if self.abort:
							break
						identifier = guide.get("_id")
						name = guide.get("name", _("* Unknown *"))
						self.uiUpdate(progress=counter * 50 // guidesCount + 50, status=_("Processing '%s' guides.") % name, pause=0.1)
						genres = set()
						guideList[identifier] = []
						timelines = guide.get("timelines", [])
						# print(f"[PlutoTV] DEBUG: timelines={len(timelines)}.")
						for timeline in timelines:
							# identifier = timeline.get("_id", "")
							# start = timeline.get("start", "")
							# stop = timeline.get("stop", "")
							# title = timeline.get("title", "")
							# episode = timeline.get("episode", {})
							#
							# Episode data:
							# identifier = episode.get("_id", "")
							# number = episode.get("number", 0)
							# season = episode.get("season", 0)
							# description = episode.get("description", "")
							# duration = episode.get("duration", 0)
							# originalContentDuration = episode.get("originalContentDuration", 0)
							# genre = episode.get("genre", "")
							# subGenre = episode.get("subGenre", "")
							# distributeAs = episode.get("distributeAs", {})  # Typical key is AVOD which is a Boolean.
							# clip = episode.get("clip", {})  # Typically keys "actors"[], "writers"[], "directors"[], producers"[] and "originalReleaseDate".
							# rating = episode.get("rating", "")
							# name = episode.get("name", "")
							# slug = episode.get("slug", "")
							# poster = episode.get("poster", {})  # Typically key "path" as a URL to a background or promotional image.
							# firstAired = episode.get("firstAired", "")
							# thumbnail = episode.get("thumbnail", {})  # Typically key "path" as a URL to a background or promotional image.
							# liveBroadcast = episode.get("liveBroadcast", False)
							# featuredImage = episode.get("featuredImage", {})  # Typically key "path" as a URL to a background or promotional image.
							# series = episode.get("series", {})
							# ratingDescriptors = episode.get("ratingDescriptors", "")
							# poster16_9 = episode.get("poster16_9", {})  # Typically key "path" as a URL to a background or promotional image.
							# cc = episode.get("cc", False)
							#
							# Series data:
							# identifier = series.get("_id", "")
							# name = series.get("name", "")
							# slug = series.get("slug", "")
							# type = series.get("type", "")
							# tile = series.get("tile", {})  # Typically key "path" as a URL to a background or promotional image.
							# description = series.get("description", "")
							# summary = series.get("summary", "")
							# displayName = series.get("displayName", "")
							# featuredImage = series.get("featuredImage", {})  # Typically key "path" as a URL to a background or promotional image.
							# poster16_9 = series.get("poster16_9", {})  # Typically key "path" as a URL to a background or promotional image.
							if self.abort:
								break
							episode = timeline.get("episode", {}) or timeline
							series = episode.get("series", {}) or timeline
							duration = int(episode.get("duration", "0") or "0") // 1000  # In seconds.
							start = timegm(strptime(timeline["start"], "%Y-%m-%dT%H:%M:%S.%fZ"))
							title = series.get("name", "") or episode.get("name", "") or timeline.get("title", "")
							tvPlot = series.get("description", "") or series.get("summary", "") or guide.get("description", "") or guide.get("summary", "")
							episodeSeason = episode.get("season", 0)
							episodeNumber = episode.get("number", 0)
							episodeType = series.get("type", "n/a")
							episodeName = episode["name"]
							episodeRating = episode.get("rating", "")
							episodeGenre = episode.get("subGenre", "")
							episodePlot = episode.get("description", "") or tvPlot or episodeName
							if len(episodeRating) > 0 and "Not Rated" not in episodeRating:
								episodePlot = f"{episodePlot}\n{_("Rating")}: {f"FSK-{episodeRating}" if episodeRating.isdigit() else episodeRating}"
							if episodeType == "tv" and (episodeSeason > 0 and episodeNumber >= 0):
								episodePlot = f"{episodeName}\n{episodeSeason}. {_("Season, episode")} {episodeNumber}: {episodePlot}"
							elif episodeType == "film" and episodeGenre not in ("None", ""):
								episodePlot = f"{episodeGenre}\n{episodePlot}"
							genre = episode.get("genre", "")
							if any((genre in ("Classics", "Romance", "Thrillers", "Horror"), "Sci-Fi" in genre, "Action" in genre)):
								genre = 0x10
							elif "News" in genre or "Educational" in genre:
								genre = 0x20
							elif genre == "Comedy":
								genre = 0x30
							elif "Children" in genre:
								genre = 0x50
							elif genre == "Music":
								genre = 0x60
							elif genre == "Documentaries":
								genre = 0xA0
							else:
								genre = 0
							if genre not in genres:
								genres.add(genre)
								guideList[identifier].append([])
							# StartTime [long], Duration [int], EventTitle, ShortDescription, ExtendedDescription, EventType [byte], EventID [int], ParentalRatings [list of tuples (Country [3 letter string], ParentalRating [byte])]
							guideList[identifier][-1].append((start, duration, title, "", episodePlot, genre))
					self.uiUpdate(progress=99)
					if self.abort:
						break
					dvbDB = eDVBDB.getInstance()
					bouquets = fileReadLines("/etc/enigma2/bouquets.tv", [], source=MODULE_NAME)
					if bouquet not in bouquets:
						print(f"[PlutoTV] Install bouquet for region '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
						bouquetRootString = "1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"bouquets.tv\" ORDER BY bouquet" if config.usage.multibouquet.value else f"{self.TV_SERVICE_TYPES} FROM BOUQUET \"userbouquet.favourites.tv\" ORDER BY bouquet"
						bouquetRoot = eServiceReference(bouquetRootString)
						serviceHandler = eServiceCenter.getInstance()
						mutableBouquetList = serviceHandler.list(bouquetRoot).startEdit()
						if mutableBouquetList:
							newBouquetReference = eServiceReference(f"1:7:1:0:0:0:0:0:0:0:FROM BOUQUET \"{bouquet}\" ORDER BY bouquet")
							if not mutableBouquetList.addService(newBouquetReference):
								mutableBouquetList.flushChanges()
								dvbDB.reloadBouquets()
								mutableBouquet = serviceHandler.list(newBouquetReference).startEdit()
								if mutableBouquet:
									mutableBouquet.setListName(f"Pluto TV {region} (TV)")
									mutableBouquet.flushChanges()
								else:
									print("[PlutoTV] Error: Get mutable list for newly created bouquet failed!")
					dvbDB.reloadServicelist()
					dvbDB.reloadBouquets()
					print(f"[PlutoTV] Merge EPG for region '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
					eventCount = 0
					for identifier, serviceReference in serviceReferences.items():
						for epgData in guideList.get(identifier, []):
							eventCount += len(epgData)
							epgCache.importEvents(serviceReference, epgData)
					print(f"[PlutoTV] {eventCount} events merged, for {channelCount} channels.")
					self.uiUpdate(progress=100)
				else:
					print(f"[PlutoTV] Pluto TV may not be available in '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}'.")
					self.uiUpdate(status=_("Pluto TV may not be available in '%s'.") % PLUTO_DATA[region][PLUTO_COUNTRY_NAME], pause=10)
					continue
				categories.clear()
				channelList.clear()
				guideList.clear()
			if not self.abort and serviceNumbersModified:
				print("[PlutoTV] Saving service numbers.")
				try:
					with open(PLUTO_SERVICE_NUMBER_PATH, "wb") as fd:
						dump(serviceNumbers, fd, protocol=5)
						serviceNumbersModified = False
				except OSError as err:
					print(f"[PlutoTV] Error {err.errno}: Unable to save service numbers to '{PLUTO_SERVICE_NUMBER_PATH}'!  ({err.strerror})")
			serviceNumbers.clear()
			fileWriteLine(PLUTO_TIMER_PATH, f"{int(time())}\n", source=MODULE_NAME)
		except Exception as err:
			print(f"[PlutoTV] Error: Update of '{PLUTO_DATA[region][PLUTO_COUNTRY_NAME]}' has failed and been aborted!  ({err})\n{format_exc()}")
			result = self.EXIT_ERROR
		if not self.verbose:
			self.start()  # This is a background update, reset the timer for the next run.
		self.updateActive = False
		print("[PlutoTV] Carousel update finished.")
		if self.abort:
			result = self.EXIT_ABORT
		return result


def updateQuery(url, queryData, safe="", quote_via=quote_plus):
	parsed = urlparse(url)
	query = dict(parse_qsl(parsed.query, keep_blank_values=True))
	for key, value in queryData.items():  # Update the URL query with the supplied queryData.
		if value:
			query[key] = value
	queryList = []
	for key in query.keys():  # Reconstruct the query string.
		queryList.append(f"{key}={query[key]}")
	query = quote_via("&".join(queryList), safe=f"=&{safe}")
	return parsed._replace(query=query).geturl()


def buildHeader(ipAddress):
	header = {
		"Accept": "application/json, text/javascript, */*; q=0.01",
		"Host": "api.pluto.tv",
		"Connection": "keep-alive",
		"Referer": "http://pluto.tv/",
		"Origin": "http://pluto.tv"
	} | PLUTO_USER_AGENT
	if ipAddress:
		header["X-Forwarded-For"] = ipAddress
	return header


def fetchURL(url, param={}, header=PLUTO_USER_AGENT):
	try:
		response = get(url, param, headers=header)
		response.raise_for_status()
		result = response.json()
	except Exception as err:
		print(f"[PlutoTV] fetchURL Error: {err}!\n{format_exc()}")
		result = {}
	return result


# The following dump methods, and their support methods, are only needed for debugging and should be commented out for production.
#
"""
def carouselDump(region, carousel):
	data = []
	fileWriteLine(f"/tmp/PlutoTV_{region}_Carousel_raw.txt", carousel, source=MODULE_NAME)
	checkKeys(data, "Carousel", carousel, ("offset", "page", "totalCategories", "totalPages", "categories"))
	appendValue(data, "Offset", carousel, "offset")
	appendValue(data, "Page", carousel, "page")
	appendValue(data, "Total categories", carousel, "totalCategories")
	appendValue(data, "Total pages", carousel, "totalPages")
	for index1, category in enumerate(carousel.get("categories"), start=1):
		checkKeys(data, "Category", category, ("_id", "name", "plutoOfficeOnly", "kidsMode", "page", "offset", "totalItemsCount", "mainCategories", "items", "hero_carousel"))
		appendValue(data, "  Identifier", category, "_id")
		appendValue(data, "  Name", category, "name")
		appendValue(data, "  Pluto office only", category, "plutoOfficeOnly")
		appendValue(data, "  Kids mode", category, "kidsMode")
		appendValue(data, "  Page", category, "page")
		appendValue(data, "  Offset", category, "offset")
		appendValue(data, "  Total items", category, "totalItemsCount")
		appendValue(data, "  Hero carousel", category, "hero_carousel")
		for main in category.get("mainCategories"):
			checkKeys(data, "Main category", main, ("categoryID",))
			appendValue(data, "  Category ID", main, "categoryID")
		for index2, item in enumerate(category.get("items", []), start=1):
			data.append(f"  Item {index2}:")
			checkKeys(data, "Items", item, ("_id", "slug", "seriesID", "name", "summary", "description", "duration", "originalContentDuration", "allotment", "featuredImage", "rating", "genre", "type", "seasonsNumbers", "stitched", "covers", "kidsMode", "ratingDescriptors", "poweredByViaFree", "poster16_9", "clip", "entitlements", "avail", "ad", "cc"))
			appendValue(data, "    Identifier", item, "_id")
			appendValue(data, "    Slug", item, "slug")
			appendValue(data, "    Series ID", item, "seriesID")
			appendValue(data, "    Name", item, "name")
			appendValue(data, "    Summary", item, "summary")
			appendValue(data, "    Description", item, "description")
			appendValue(data, "    Duration", item, "duration")
			appendValue(data, "    Original duration", item, "originalContentDuration")
			appendValue(data, "    Allotment", item, "allotment")
			appendValue(data, "    Featured image", item, "featuredImage", subKeys=("path",))
			appendValue(data, "    Rating", item, "rating")
			appendValue(data, "    Genre", item, "genre")
			appendValue(data, "    Type", item, "type")
			appendValue(data, "    Season numbers", item, "seasonsNumbers")
			appendValue(data, "    Original duration", item, "originalContentDuration")
			appendValue(data, "    Stitched", item, "stitched", subKeys=("urls", "sessionURL"))
			for cover in item.get("covers"):
				checkKeys(data, "Covers", cover, ("aspectRatio", "url"))
				appendValue(data, "    Cover aspect ratio", cover, "aspectRatio")
				appendValue(data, "    Cover URL", cover, "url")
			appendValue(data, "    Kids mode", item, "kidsMode")
			appendValue(data, "    Rating descriptors", item, "ratingDescriptors")
			appendValue(data, "    Powered by Via Free", item, "poweredByViaFree")
			appendValue(data, "    Poster 16x9", item, "poster16_9", subKeys=("path",))
			appendValue(data, "    Clip", item, "clip", subKeys=("actors", "writers", "directors", "producers", "originalReleaseDate"))
			appendValue(data, "    Entitlements", item, "entitlements")
			checkKeys(data, "Avail", item["avail"], ("startDate",))
			appendValue(data, "    Avail", item, "avail", subKeys=("startDate",))
			appendValue(data, "    Ad", item, "ad")
			appendValue(data, "    Closed captions", item, "cc")
	fileWriteLines(f"/tmp/PlutoTV_{region}_Carousel_dump.txt", data, source=MODULE_NAME)


def seriesDump(region, series):
	data = []
	fileWriteLine(f"/tmp/PlutoTV_{region}_Series_raw.txt", series, source=MODULE_NAME)
	checkKeys(data, "Series", series, ("_id", "name", "summary", "description", "slug", "type", "rating", "featuredImage", "genre", "offset", "page", "seasons", "covers", "poster16_9", "avail"))
	appendValue(data, "Identifier", series, "_id")
	appendValue(data, "Name", series, "name")
	appendValue(data, "Summary", series, "summary")
	appendValue(data, "Description", series, "description")
	appendValue(data, "Slug", series, "slug")
	appendValue(data, "Type", series, "type")
	appendValue(data, "Rating", series, "rating")
	appendValue(data, "Featured image", series, "featuredImage", subKeys=("path",))
	appendValue(data, "Genre", series, "genre")
	appendValue(data, "Offset", series, "offset")
	appendValue(data, "Page", series, "page")
	for cover in series.get("covers"):
		checkKeys(data, "Covers", cover, ("aspectRatio", "url"))
		appendValue(data, "Cover aspect ratio", cover, "aspectRatio")
		appendValue(data, "Cover URL", cover, "url")
	appendValue(data, "Poster 16x9", series, "poster16_9", subKeys=("path",))
	checkKeys(data, "Avail", series["avail"], ("startDate",))
	appendValue(data, "Avail", series, "avail", subKeys=("startDate",))
	for season in series.get("seasons", []):
		checkKeys(data, "Season", season, ("number", "episodes"))
		appendValue(data, "  Number", season, "number")
		for episode in (season.get("episodes", [])):
			data.append(f"  Season {episode["season"]}, Episode {episode["number"]}")
			checkKeys(data, "Episode", episode, ("_id", "name", "description", "allotment", "rating", "slug", "duration", "originalContentDuration", "genre", "type", "number", "season", "stitched", "covers", "poster16_9", "clip", "cc"))
			appendValue(data, "    Identifier", episode, "_id")
			appendValue(data, "    Name", episode, "name")
			appendValue(data, "    Description", episode, "description")
			appendValue(data, "    Allotment", episode, "allotment")
			appendValue(data, "    Rating", episode, "rating")
			appendValue(data, "    Slug", episode, "slug")
			appendValue(data, "    Duration", episode, "duration")
			appendValue(data, "    Original duration", episode, "originalContentDuration")
			appendValue(data, "    Genre", episode, "genre")
			appendValue(data, "    Type", episode, "type")
			appendValue(data, "    Number", episode, "number")
			appendValue(data, "    Season", episode, "season")
			appendValue(data, "    Stitched", episode, "stitched", subKeys=("urls", "sessionURL"))
			for cover in episode.get("covers"):
				checkKeys(data, "Covers", cover, ("aspectRatio", "url"))
				appendValue(data, "    Cover aspect ratio", cover, "aspectRatio")
				appendValue(data, "    Cover URL", cover, "url")
			appendValue(data, "    Poster 16x9", episode, "poster16_9", subKeys=("path",))
			appendValue(data, "    Clip", episode, "clip", subKeys=("actors", "writers", "directors", "producers", "originalReleaseDate"))
			appendValue(data, "    Closed captions", episode, "cc")
	fileWriteLines(f"/tmp/PlutoTV_{region}_Series_dump.txt", data, source=MODULE_NAME)


def channelsDump(region, channels):
	data = []
	fileWriteLine(f"/tmp/PlutoTV_{region}_Channels_raw.txt", channels, source=MODULE_NAME)
	for index, channel in enumerate(channels, start=1):
		checkKeys(data, "Channel", channel, ("_id", "slug", "name", "hash", "number", "summary", "visibility", "onDemandDescription", "category", "plutoOfficeOnly", "directOnly", "chatRoomId", "onDemand", "cohortMask", "featuredImage", "thumbnail", "tile", "tileGrayScale", "logo", "colorLogoSVG", "colorLogoPNG", "solidLogoSVG", "solidLogoPNG", "featured", "featuredOrder", "favorite", "isStitched", "stitched", "tmsid"))
		data.append(f"Channel {index}:")
		appendValue(data, "  Identifier", channel, "_id")
		appendValue(data, "  Slug", channel, "slug")
		appendValue(data, "  Name", channel, "name")
		appendValue(data, "  Hash", channel, "hash")
		appendValue(data, "  Number", channel, "number")
		appendValue(data, "  Summary", channel, "summary")
		appendValue(data, "  Visibility", channel, "visibility")
		appendValue(data, "  On-demand description", channel, "onDemandDescription")
		appendValue(data, "  Category", channel, "category")
		appendValue(data, "  PlutoTV office only", channel, "plutoOfficeOnly")
		appendValue(data, "  Direct only", channel, "directOnly")
		appendValue(data, "  Chat room ID", channel, "chatRoomId")
		appendValue(data, "  On-demand", channel, "onDemand")
		appendValue(data, "  Cohort mask", channel, "cohortMask")
		appendValue(data, "  Featured image", channel, "featuredImage", subKeys=("path",))
		appendValue(data, "  Thumbnail", channel, "thumbnail", subKeys=("path",))
		appendValue(data, "  Tile", channel, "tile", subKeys=("path",))
		appendValue(data, "  Tile gray scale", channel, "tileGrayScale", subKeys=("path",))
		appendValue(data, "  Logo", channel, "logo", subKeys=("path",))
		appendValue(data, "  Color logo SVG", channel, "colorLogoSVG", subKeys=("path",))
		appendValue(data, "  Color logo PNG", channel, "colorLogoPNG", subKeys=("path",))
		appendValue(data, "  Solid logo SVG", channel, "solidLogoSVG", subKeys=("path",))
		appendValue(data, "  Solid logo PNG", channel, "solidLogoPNG", subKeys=("path",))
		appendValue(data, "  Featured", channel, "featured")
		appendValue(data, "  Featured order", channel, "featuredOrder")
		appendValue(data, "  Favorite", channel, "favorite")
		appendValue(data, "  Is stitched", channel, "isStitched")
		appendValue(data, "  Stitched", channel, "stitched", subKeys=("urls", "sessionURL"))
		appendValue(data, "  TMS ID", channel, "tmsid")
	fileWriteLines(f"/tmp/PlutoTV_{region}_Channels_dump.txt", data, source=MODULE_NAME)


def guidesDump(region, guides):
	data = []
	fileWriteLine(f"/tmp/PlutoTV_{region}_Guide_raw.txt", guides, source=MODULE_NAME)
	for index, guide in enumerate(guides, start=1):
		checkKeys(data, "Guide", guide, ("_id", "slug", "name", "hash", "number", "summary", "visibility", "onDemandDescription", "category", "plutoOfficeOnly", "directOnly", "chatRoomId", "onDemand", "cohortMask", "featuredImage", "thumbnail", "tile", "tileGrayScale", "logo", "colorLogoSVG", "colorLogoPNG", "solidLogoSVG", "solidLogoPNG", "featured", "featuredOrder", "favorite", "isStitched", "stitched", "timelines"))
		data.append(f"Guide {index}:")
		appendValue(data, "  Identifier", guide, "_id")
		appendValue(data, "  Slug", guide, "slug")
		appendValue(data, "  Name", guide, "name")
		appendValue(data, "  Hash", guide, "hash")
		appendValue(data, "  Number", guide, "number")
		appendValue(data, "  Summary", guide, "summary")
		appendValue(data, "  Visibility", guide, "visibility")
		appendValue(data, "  On-demand description", guide, "onDemandDescription")
		appendValue(data, "  Category", guide, "category")
		appendValue(data, "  PlutoTV office only", guide, "plutoOfficeOnly")
		appendValue(data, "  Direct only", guide, "directOnly")
		appendValue(data, "  Chat room ID", guide, "chatRoomId")
		appendValue(data, "  On-demand", guide, "onDemand")
		appendValue(data, "  Cohort mask", guide, "cohortMask")
		appendValue(data, "  Featured image", guide, "featuredImage", subKeys=("path",))
		appendValue(data, "  Thumbnail", guide, "thumbnail", subKeys=("path",))
		appendValue(data, "  Tile", guide, "tile", subKeys=("path",))
		appendValue(data, "  Tile gray scale", guide, "tileGrayScale", subKeys=("path",))
		appendValue(data, "  Logo", guide, "logo", subKeys=("path",))
		appendValue(data, "  Color logo SVG", guide, "colorLogoSVG", subKeys=("path",))
		appendValue(data, "  Color logo PNG", guide, "colorLogoPNG", subKeys=("path",))
		appendValue(data, "  Solid logo SVG", guide, "solidLogoSVG", subKeys=("path",))
		appendValue(data, "  Solid logo PNG", guide, "solidLogoPNG", subKeys=("path",))
		appendValue(data, "  Featured", guide, "featured")
		appendValue(data, "  Featured order", guide, "featuredOrder")
		appendValue(data, "  Favorite", guide, "favorite")
		appendValue(data, "  Is stitched", guide, "isStitched")
		appendValue(data, "  Stitched", guide, "stitched", subKeys=("urls", "sessionURL"))
		# appendValue(data, "  Time lines", guide, "timelines")
		for timeline in guide.get("timelines"):
			data.append("  Timeline data:")
			checkKeys(data, "Timeline", timeline, ("_id", "start", "stop", "title", "episode"))
			appendValue(data, "    Identifier", timeline, "_id")
			appendValue(data, "    Start", timeline, "start")
			appendValue(data, "    Stop", timeline, "stop")
			appendValue(data, "    Title", timeline, "title")
			# appendValue(data, "    Episode", timeline, "episode")  # This is broken down below.
			episode = timeline.get("episode")
			checkKeys(data, "Episode", episode, ("_id", "number", "season", "description", "duration", "originalContentDuration", "genre", "subGenre", "distributeAs", "clip", "rating", "name", "slug", "poster", "firstAired", "thumbnail", "liveBroadcast", "featuredImage", "series", "ratingDescriptors", "poster16_9", "cc"))
			data.append("    Episode data:")
			appendValue(data, "      Identifier", episode, "_id")
			appendValue(data, "      Number", episode, "number")
			appendValue(data, "      Season", episode, "season")
			appendValue(data, "      Description", episode, "description")
			appendValue(data, "      Original content duration", episode, "originalContentDuration")
			appendValue(data, "      Genre", episode, "genre")
			appendValue(data, "      Sub-genre", episode, "subGenre")
			appendValue(data, "      Distribute as", episode, "distributeAs", subKeys=("AVOD",))
			appendValue(data, "      Clip", episode, "clip", subKeys=("actors", "writers", "directors", "producers", "originalReleaseDate"))
			appendValue(data, "      Rating", episode, "rating")
			appendValue(data, "      Name", episode, "name")
			appendValue(data, "      Slug", episode, "slug")
			appendValue(data, "      Poster", episode, "poster", subKeys=("path",))
			appendValue(data, "      First aired", episode, "firstAired")
			appendValue(data, "      Thumbnail", episode, "thumbnail", subKeys=("path",))
			appendValue(data, "      Live broadcast", episode, "liveBroadcast")
			appendValue(data, "      Featured image", episode, "featuredImage", subKeys=("path",))
			# appendValue(data, "      Series", episode, "series")  # This is broken down below.
			appendValue(data, "      Rating descriptors", episode, "ratingDescriptors")
			appendValue(data, "      Poster 16x9", episode, "poster16_9", subKeys=("path",))
			appendValue(data, "      Closed captions", episode, "cc")
			series = episode.get("series")
			checkKeys(data, "Series", series, ("_id", "name", "slug", "type", "tile", "description", "summary", "displayName", "featuredImage", "poster16_9"))
			data.append("      Series data:")
			appendValue(data, "        Identifier", series, "_id")
			appendValue(data, "        Name", series, "name")
			appendValue(data, "        Slug", series, "slug")
			appendValue(data, "        Type", series, "type")
			appendValue(data, "        Tile", series, "tile", subKeys=("path",))
			appendValue(data, "        Description", series, "description")
			appendValue(data, "        Summary", series, "summary")
			appendValue(data, "        Display name", series, "displayName")
			appendValue(data, "        Featured image", series, "featuredImage", subKeys=("path",))
			appendValue(data, "        poster16_9", series, "poster16_9", subKeys=("path",))
			appendValue(data, "        Tile", series, "tile", subKeys=("path",))
			appendValue(data, "        Poster 16x9", series, "poster16_9", subKeys=("path",))
	fileWriteLines(f"/tmp/PlutoTV_{region}_Guide_dump.txt", data, source=MODULE_NAME)


def checkKeys(data, label, source, keys):
	keyList = list(source.keys())
	for key in keys:
		if key in keyList:
			keyList.remove(key)
	if keyList:
		data.append(f"**{label} Unaccounted key(s)={keyList}")


def appendValue(data, label, source, key, subKeys=None):
	value = source.get(key)
	match value:
		case bool() | float() | int():
			if value is not None and not (key == "originalContentDuration" and value == 0):  # "originalContentDuration" always defined, even if 0.
				data.append(f"{label}={value}")
		case dict():
			if subKeys:
				keys = list(source.get(key).keys())
				for subKey in subKeys:
					if subKey in keys:
						keys.remove(subKey)
				if keys:
					data.append(f"**{label} keys={keys}")
				for subKey in subKeys:
					if subKey in value:
						data.append(f"{label} {subKey}={value[subKey]}")
			elif value:
				data.append(f"{label}={value}")
		case list() | str():
			if value:
				data.append(f"{label}={value}")
		case None:
			# data.append(f"{label}=** Value undefined! **")
			pass
		case _:
			data.append(f"**{type(value)}**{label}={value}")
"""
#
# End of diagnostic dump methods.


# class PlutoResumePoints:
# 	def __init__(self):
# 		self.resumePointsCache = {}
resumePointsCache = {}


def getResumePoint(sid):
	def loadResumePoints(sid):
		resumePoints = {}
		path = join(PLUTO_FOLDER, f"{sid}.cue")
		if isfile(path):
			try:
				with open(path, "rb") as fd:
					resumePoints = load(fd)
			except OSError as err:
				print(f"[PlutoTV] Error {err.errno}: Failed to open resume point file '{path}'!  ({err.strerror})")
			except Exception as err:
				print(f"[PlutoTV] Error: Failed to load resume point data!  ({str(err)})")
		return resumePoints

	resumePoint = [None, None, None]  # The resumePoint is (lruTimestamp, position, length).
	if sid is not None:
		# self.resumePointsCache = self.loadResumePoints(sid)
		# resumePoint = self.resumePointsCache.get(sid, resumePoint)
		global resumePointsCache
		resumePointsCache = loadResumePoints(sid)
		resumePoint = resumePointsCache.get(sid, resumePoint)
		resumePoint[0] = int(time())  # Update lruTimestamp.
	return resumePoint[1], resumePoint[2]


def setResumePoint(session, sid=None):
	def saveResumePoints(sid):
		path = join(PLUTO_FOLDER, f"{sid}.cue")
		try:
			with open(path, "wb") as fd:
				# dump(self.resumePointsCache, fd, protocol=5)
				global resumePointsCache
				dump(resumePointsCache, fd, protocol=5)
		except OSError as err:
			print(f"[PlutoTV] Error {err.errno}: Failed to write resume point file '{path}'!  ({err.strerror})")
		except Exception as err:
			print(f"[PlutoTV] Error: Failed to dump resume point data!  ({str(err)})")

	service = session.nav.getCurrentService()
	serviceReference = session.nav.getCurrentlyPlayingServiceReference()
	if service and serviceReference:
		seek = service.seek()
		if seek:
			position = seek.getPlayPosition()
			if not position[0]:
				length = seek.getLength()
				length = length[1] if length else None
				# self.resumePointsCache[sid] = [int(time()), position[1], length]
				# self.saveResumePoints(sid)
				global resumePointsCache
				resumePointsCache[sid] = [int(time()), position[1], length]
				saveResumePoints(sid)


class PlutoUpdate(Screen, PlutoUpdater):
	# skin = """
	# <screen name="PlutoUpdate" title="Pluto TV Update" position="center,50" size="600,105" ignoreWidgets="action" resolution="1280,720">
	# 	<widget name="progress" position="0,4" size="e-70,12" backgroundColor="#00333333" borderColor="#0000C000" borderWidth="1" foregroundColor="#0000C000" />
	# 	<widget name="percentage" position="e-70,0" size="70,20" font="Regular;20" horizontalAlignment="right" transparent="1" verticalAlignment="center" />
	# 	<widget name="status" position="0,30" size="e,25" font="Regular;20" noWrap="1" transparent="1" verticalAlignment="center" />
	# 	<widget source="key_red" render="Label" position="0,e-40" size="180,40" backgroundColor="key_red" conditional="key_red" font="Regular;20" foregroundColor="key_text" horizontalAlignment="center" verticalAlignment="center">
	# 		<convert type="ConditionalShowHide" />
	# 	</widget>
	# 	<widget source="key_help" render="Label" position="e-80,e-40" size="80,40" backgroundColor="key_back" conditional="key_help" font="Regular;20" foregroundColor="key_text" horizontalAlignment="center" verticalAlignment="center">
	# 		<convert type="ConditionalShowHide" />
	# 	</widget>
	# </screen>"""

	skin = """
	<screen name="PlutoUpdate" title="Pluto TV Update" position="center,50" size="620,100" flags="wfNoBorder" ignoreWidgets="key_red,key_help" resolution="1280,720">
		<widget name="action" position="10,10" size="e-20,25" font="Regular;20" noWrap="1" transparent="1" verticalAlignment="center" />
		<widget name="progress" position="10,39" size="e-90,12" backgroundColor="#00333333" borderColor="#0000C000" borderWidth="1" foregroundColor="#0000C000" />
		<widget name="percentage" position="e-90,35" size="70,20" font="Regular;20" horizontalAlignment="right" transparent="1" verticalAlignment="center" />
		<widget name="status" position="10,65" size="e,25" font="Regular;20" noWrap="1" transparent="1" verticalAlignment="center" />
	</screen>"""

	def __init__(self, session, bouquetRegionList=None):
		Screen.__init__(self, session, enableHelp=True)
		PlutoUpdater.__init__(self, True)  # Verbose output is True.
		self.bouquetRegionList = bouquetRegionList
		self["action"] = Label(_("Pluto TV Update"))
		self["progress"] = ProgressBar()
		self["progress"].setValue(0)
		self["percentage"] = Label("0%")
		self["status"] = Label(_("Please wait..."))
		self["key_red"] = StaticText(_("Cancel"))
		self["actions"] = HelpableActionMap(self, ["CancelActions"], {
			"cancel": (self.keyCancel, _("Cancel Pluto TV update"))
		}, prio=0, description=_("Pluto TV Update Action"))
		self.timer = eTimer()
		self.timer.callback.append(self.close)
		self.onLayoutFinish.append(self.startUpdate)

	def startUpdate(self):
		def getResult(result):
			# print(f"[PlutoTV] DEBUG: Update thread returned result {result}.")
			self["key_red"].setText(_("Close"))
			match result:
				case PlutoUpdater.EXIT_DONE:
					self.setTitle(_("Pluto TV"))
					self["action"].setText(_("Pluto TV Update"))
					self["status"].setText(_("Update finished."))
					delay = 5
				case PlutoUpdater.EXIT_RUNNING:
					self.setTitle(_("Pluto TV"))
					self["action"].setText(_("Pluto TV Update"))
					self["status"].setText(_("Update already in progress!"))
					delay = 10
				case PlutoUpdater.EXIT_ABORT:
					self["status"].setText(_("Update aborted!"))
					delay = 5
				case PlutoUpdater.EXIT_ERROR:
					self["status"].setText(_("Error during update, update aborted!"))
					delay = 10
				case _:
					delay = 0
			if delay:
				self.timer.startLongTimer(delay)

		thread = threads.deferToThread(self.updateThread)
		thread.addCallback(getResult)

	def keyCancel(self):
		self.abort = True


class PlutoScheduler(PlutoUpdater):
	def __init__(self):
		PlutoUpdater.__init__(self, False)  # Verbose output is False.
		self.timer = eTimer()
		self.timer.callback.append(self.startUpdate)

	def start(self):
		repeat = config.plugins.PlutoTV.updateTimer.value
		last = int(fileReadLine(PLUTO_TIMER_PATH, default="0", source=MODULE_NAME))
		delay = (repeat * 3600) - (int(time()) - last)
		if delay <= 0 or delay > (repeat * 3600):
			delay = 1
		print(f"[PlutoTV] Next update in {delay // 3600}:{delay // 60 % 60:02d}:{delay % 60:02d} at {strftime("%Y-%b-%d %H:%M:%S", localtime(int(time()) + delay))}. Update will {f"be run every {repeat} hour(s)" if repeat else "not be rescheduled"}.")
		self.timer.startLongTimer(delay)

	def stop(self):
		self.timer.stop()
		print("[PlutoTV] Update process stopped.")

	def startUpdate(self):
		print("[PlutoTV] Update process starting.")
		reactor.callInThread(self.updateThread)


def runUpdate(session, **kwargs):
	session.open(PlutoUpdate)


def runFromMainMenu(menuid, **kwargs):
	return [(_("Pluto TV"), runPlutoTV, "plutotv", 20)] if menuid == "mainmenu" else []


def runPlutoTV(session, **kwargs):
	session.open(PlutoTV)


def autoStart(reason, session):
	def findStoragePath(minFree, default, *candidates):
		mounts = fileReadLines("/proc/mounts", [], source=MODULE_NAME)
		mountPoints = [x.split(" ", 2)[1] for x in mounts]
		result = default
		for candidate in candidates:
			if candidate.encode("UTF-8") in mountPoints:
				try:
					diskStatus = statvfs(candidate)
					freeSpace = diskStatus.f_bavail * diskStatus.f_frsize
					if freeSpace > minFree and freeSpace > 100 * 10 ** 6:
						print(f"[PlutoTV] Free space on selected mount {candidate} is {freeSpace}.")
						result = candidate
						break
					else:
						print(f"[PlutoTV] Free space on candidate mount {candidate} is {freeSpace} and insufficiet.")
				except OSError as err:
					print(f"[PlutoTV] Error {err.errno}: Failed to get filesystem status for '{candidate}'!  ({err.strerror})")
		return result

	if reason == 0:  # Starting Enigma2.
		global PLUTO_FOLDER
		PLUTO_FOLDER = join(findStoragePath(500 * 10 ** 6, "/tmp", "/media/hdd", "/media/usb", "/media/cf", "/media/mmc"), "PlutoTV")
		if not exists(PLUTO_FOLDER):
			makedirs(PLUTO_FOLDER)
		plutoScheduler.start()
	else:  # Stopping Enigma2:
		plutoScheduler.stop()


def Plugins(**kwargs):
	name = _("Pluto TV")
	description = _("Play Pluto TV videos and create Pluto TV bouquets.  (Version: %s)") % __version__
	plugin = [
		PluginDescriptor(name=_("Pluto TV Scheduler"), where=[PluginDescriptor.WHERE_SESSIONSTART], fnc=autoStart),
		PluginDescriptor(name=name, description=description, where=[PluginDescriptor.WHERE_PLUGINMENU], icon="plutotv.png", fnc=runPlutoTV),
	]
	if config.plugins.PlutoTV.addToMainMenu.value:
		# plugin.append(PluginDescriptor(name=name, description=description, where=[PluginDescriptor.WHERE_MAINMENU], icon="plutotv.png", fnc=runPlutoTV))
		plugin.append(PluginDescriptor(name=name, description=description, where=[PluginDescriptor.WHERE_MENU], icon="plutotv.png", fnc=runFromMainMenu))
	if config.plugins.PlutoTV.addToExtensionMenu.value:
		plugin.append(PluginDescriptor(name=name, description=description, where=[PluginDescriptor.WHERE_EXTENSIONSMENU], icon="plutotv.png", fnc=runPlutoTV))
	if config.plugins.PlutoTV.addUpdateToExtensionMenu.value:
		plugin.append(PluginDescriptor(name=_("Pluto TV Update"), description=_("Start Pluto TV bouquet, picons & EPG update."), where=[PluginDescriptor.WHERE_EXTENSIONSMENU], fnc=runUpdate))
	return plugin


plutoScheduler = PlutoScheduler()
