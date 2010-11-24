from robot.utils import normalizing

def find_attribute(obj, attr, prefix):
    attr = str(attr)
    for i_attr in dir(obj):
        normalized_i_attr = normalizing.normalize(i_attr, ignore='_')
        normalized_attr = normalizing.normalize(prefix + attr,
                ignore='_')
        if normalized_i_attr == normalized_attr:
            return getattr(obj, i_attr)

    try:
        attr = int(attr, 0)
        return attr
    except ValueError:
        raise RuntimeError('Attribute "%s" in "%s" not found.' % (attr, obj))

def int_any_base(i, base=0):
    try:
        return int(i, base)
    except TypeError:
        return i
    except ValueError:
        raise RuntimeError('Could not parse integer "%s"' % i)

class PerConnectionStorage:
    def __init__(self, propname):
        self._cp_propname = propname
        self._cp_storage = dict()

    @property
    def _cp(self):
        """Property storage per connection."""
        if not hasattr(self, self._cp_propname):
            raise RuntimeError('No/wrong active connection property set.')
        active_connection = getattr(self, self._cp_propname)
        if active_connection is None:
            raise RuntimeError('No connection active')
        if active_connection not in self._cp_storage:
            self._cp_storage[active_connection] = dict()
        return self._cp_storage[active_connection]


class Logging:
    def _warn(self, fmt, *args):
        self._log_format(fmt, level='WARN')

    def _info(self, fmt, *args):
        self._log_format(fmt, level='INFO')

    def _debug(self, fmt, *args):
        self._log_format(fmt, level='DEBUG')

    def _trace(self, fmt, *args):
        self._log_format(fmt, level='TRACE')

    def _log_format(self, fmt, *args, **kwargs):
        level=None
        if 'level' in kwargs:
            level=kwargs['level']

        self._log(fmt % args, level=level)

    def _log(self, msg, level=None):
        self._is_valid_log_level(level, raise_if_invalid=True)
        msg = msg.strip()
        if level is None:
            level = self._default_log_level
        if msg != '':
            print '*%s* %s' % (level.upper(), msg)

    def _is_valid_log_level(self, level, raise_if_invalid=False):
        if level is None:
            return True
        if isinstance(level, basestring) and \
                level.upper() in ['TRACE', 'DEBUG', 'INFO', 'WARN', 'HTML']:
            return True
        if not raise_if_invalid:
            return False
        raise RuntimeError("Invalid log level '%s'" % level)
