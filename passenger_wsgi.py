import os
import sys
from importlib import import_module

sys.path.insert(0, os.path.dirname(__file__))

wsgi = import_module('wsgi')
application = wsgi.application
