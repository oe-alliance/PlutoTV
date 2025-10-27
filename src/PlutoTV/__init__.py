from gettext import bindtextdomain, dgettext, gettext

from Components.Language import language
from Tools.Directories import SCOPE_PLUGINS, resolveFilename

PluginLanguageDomain = "PlutoTV"
PluginLanguagePath = "Extensions/PlutoTV/locale"

__version__ = "3.0"


def localeInit():
	bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
	if dgettext(PluginLanguageDomain, txt):
		return dgettext(PluginLanguageDomain, txt)
	else:
		# print("[" + PluginLanguageDomain + "] fallback to default translation for " + txt)
		return gettext(txt)


localeInit()
language.addCallback(localeInit)
