from setuptools import setup
import setup_translate

pkg = 'Extensions.PlutoTV'
setup(name='enigma2-plugin-extensions-plutotv',
       version='3.0',
       description='PlutoTV for E2',
       package_dir={pkg: 'PlutoTV'},
       packages=[pkg],
       package_data={pkg: ['images/*.png', '*.png', '*.xml', 'locale/*/LC_MESSAGES/*.mo']},
       cmdclass=setup_translate.cmdclass,  # for translation
      )
