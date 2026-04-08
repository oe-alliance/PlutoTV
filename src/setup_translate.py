from glob import glob
from os import listdir, makedirs, system
from os.path import exists, join
from setuptools import Command
from setuptools.command.build import build as _build


class build_trans(Command):
	description = 'Compile .po files into .mo files'

	def initialize_options(self):
		pass  # Will be called by setuptools, but we don't have any options to initialize

	def finalize_options(self):
		pass  # Will be called by setuptools, but we don't have any options to initialize

	def run(self):
		s = join('PlutoTV', 'locale')
		lang_domains = glob(join(s, '*.pot'))
		if len(lang_domains):
			for lang in listdir(s):
				if lang.endswith('.po'):
					src = join(s, lang)
					lang = lang[:-3]
					destdir = join(s, lang, 'LC_MESSAGES')
					if not exists(destdir):
						makedirs(destdir)
					for lang_domain in lang_domains:
						lang_domain = lang_domain.rsplit('/', 1)[1]
						dest = join(destdir, lang_domain[:-3] + 'mo')
						print(f"Language compile {src} -> {dest}")
						if system(f"msgfmt '{src}' -o '{dest}'") != 0:
							raise Exception  # NOSONAR - we want to fail if
		else:
			print("we got no domain -> no translation was compiled")


class build(_build):
	sub_commands = _build.sub_commands + [('build_trans', None)]

	def run(self):
		_build.run(self)


cmdclass = {
	'build': build,
	'build_trans': build_trans,
}
