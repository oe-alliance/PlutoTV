from gettext import bindtextdomain, dgettext, gettext

from Components.Language import language
from Tools.Directories import SCOPE_PLUGINS, resolveFilename

PluginLanguageDomain = "PlutoTV"
PluginLanguagePath = "Extensions/PlutoTV/locale"

__version__ = "3.0.1"


def localeInit():
	bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(text):
	if translated := dgettext(PluginLanguageDomain, text):
		return translated
	else:
		# print(f"[{PluginLanguageDomain}] fallback to default translation for {text}")
		return gettext(text)


localeInit()
language.addCallback(localeInit)
