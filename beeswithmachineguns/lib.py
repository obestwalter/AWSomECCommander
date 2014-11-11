import functools
import inspect
import json
import logging
import os
from types import FunctionType, MethodType

from plumbum import LocalPath
from plumbum.path import LocalWorkdir


log = logging.getLogger(__name__)
log.setLevel(logging.ERROR)


__all__ = [
    'JsonConfigger',
    'oa',
    'oac',
    'obj_attr',
    'cached_property',
    'expire_cached_properties',
    'caller',
]


class JsonConfigger(object):
    def __init__(self, configPath):
        self._path = LocalPath(configPath)

    def load_config(self):
        if not self._path.exists():
            log.info("nothing to load at %s", self._path)
            return self

        config = json.loads(self._path.read())
        for attrName, value in config.items():
            setattr(self, attrName, value)
        return self

    def save_config(self):
        self._path.write(json.dumps(self.asDict, indent=True))

    def remove_config(self):
        self._path.delete()

    @property
    def HAS_SAVED_STATE(self):
        return self._path.exists()

    @property
    def asDict(self):
        config = {k: self._nrmlz(v) for k, v in self.__dict__.items()
                  if not k.startswith('_') and not k.isupper()}
        props = {k: self._nrmlz(getattr(self, k)) for k in self._publicProps}
        config.update(props.items())
        return config

    @property
    def _publicProps(self):
        return [name for (name, member) in inspect.getmembers(self.__class__)
                if not name.startswith('_') and name != 'asDict' and
                not name.isupper() and type(member) == property]

    def _nrmlz(self, value):
        """normalize strange things to json compatible values"""
        if isinstance(value, LocalPath):
            return str(value)

        if isinstance(value, list):
            return [self._nrmlz(v) for v in value]

        return value


SPECIAL_ATTR_NAMES = [
    "str", "repr", "dict", "doc", "class", "delattr", "format",
    "getattribute", "hash", "init", "module", "new", "reduce", "reduce_ex",
    "setattr", "sizeof", "subclasshook", "weakref"]

SIMPLE_OBJECTS = [basestring, list, tuple, dict, set, int, float]


def obj_attr(obj, hideString='', filterMethods=True, filterPrivate=True,
             sanitize=False, excludeAttrs=None, indent=0, objName=""):
    try:
        if any(isinstance(obj, t) for t in SIMPLE_OBJECTS):
            return ("[simple obj_attr] %s (%s): %s" %
                    (objName or "(anon)", type(obj).__name__, str(obj)))

        return _obj_attr(
            obj, hideString, filterMethods, filterPrivate,
            sanitize, excludeAttrs, indent, objName)

    except Exception:
        msg = "problems calling obj_attr"
        log.error(msg, exc_info=True)
        return msg


def _obj_attr(obj, hideString='', filterMethods=True, filterPrivate=True,
              sanitize=False, excludeAttrs=None, indent=0, objName=""):
    """show attributes of any object - generic representation of objects"""
    excludeAttrs = excludeAttrs or []
    names = dir(obj)
    for specialObjectName in SPECIAL_ATTR_NAMES:
        n = "__%s__" % (specialObjectName)
        if n in names:
            names.remove(n)
    if hideString:
        names = [n for n in names if hideString not in n]
    if filterPrivate:
        names = [n for n in names if not n.startswith('_')]
    out = []
    for name in sorted([d for d in names if d not in excludeAttrs]):
        try:
            attr = getattr(obj, name)
            attrType = type(attr)
            if attr is obj:
                continue  # recursion avoidance

            if filterMethods and (attrType in [FunctionType, MethodType]):
                continue

            if attrType in (FunctionType, MethodType):
                try:
                    value = attr.__doc__.split("\n")[0]
                except:
                    value = "<<func>>"
            else:
                value = str(attr).replace("\n", "\n|  ")
            out.append((name, attrType.__name__, value))
        except AssertionError as e:
            out.append(("[A] %s" % (name), e.__class__.__name__, e.message))

        except Exception as e:
            out.append(
                ("[E] %s" % (name), e.__class__.__name__, e.message[:80]))
    out = out or [(objName, str(type(obj)), repr(obj))]
    boundTo = "'%s' " % (objName) if objName else ""
    header = "|# %s%s (0x%X) #|" % (boundTo, type(obj).__name__, (id(obj)))
    numDashes = 41 - len(header) / 2
    out = (
        ["\n," + "-" * (numDashes - 1) + header + "-" * numDashes] +
        [_prepare_content(content) for content in out] +
        ["'" + "-" * 82])
    if sanitize:
        out = [o.replace('<', '(').replace('>', ')') for o in out]
    if indent:
        out = ["%s%s" % (" " * indent, o) for o in out]
    return os.linesep.join(out) + "\n  "
    #return _os.linesep.join(out) + "\ncaller: %s" % (caller(10))


def _prepare_content(contentTuple):
    """add line breaks within an attribute line"""
    name, typeName, value = contentTuple
    pattern = "| %-30s %15s: %%s" % (name, typeName.rpartition(".")[-1])
    if not isinstance(value, basestring):
        value = str(value)
    if str(value).strip().startswith("| "):
        return pattern % (value)

    windowSize = 78
    firstLineLength = len(pattern) - 7
    curPos = windowSize - firstLineLength
    lines = [pattern % value[:curPos]]
    while True:
        curString = value[curPos:curPos + windowSize]
        if not curString:
            break

        lines.append("\n|    %s" % (curString))
        curPos += windowSize
    return "".join(lines)


def caller(depth=1):
    """return the caller of the calling function. """

    def get_caller_path(depth):
        callers = [inspect.stack()[1 + depth][3]
                   for depth in range(depth, 0, -1)]
        return ".".join(callers)

    for depth in range(depth, 0, -1):
        try:
            return get_caller_path(depth)

        except Exception:
            if depth == 1:
                log.error("caller failed", exc_info=True)
    return "unknown caller"


def oa(obj):
    return obj_attr(obj)


def oac(obj):
    return obj_attr(obj, filterMethods=False, filterPrivate=False)


def cached_property(meth):
    """Cache this property until the cache is expired explicitly"""
    @property
    @functools.wraps(meth)
    def _cached_property(self):
        try:
            return self._propertyCache[meth]

        except AttributeError:
            self._propertyCache = {}
            result = self._propertyCache[meth] = meth(self)
            return result

        except KeyError:
            result = self._propertyCache[meth] = meth(self)
            return result

    return _cached_property


def expire_cached_properties(meth):
    """if this method is called all cached properties are expired"""
    @functools.wraps(meth)
    def _expire_cached_properties(self, *args, **kwargs):
        cache = getattr(self, "_propertyCache", None)
        if type(cache) == dict:
            #print(cache)
            cache.clear()
            #print("expired %s.propertyCache" % (self.__class__.__name__))
        return meth(self, *args, **kwargs)

    return _expire_cached_properties


class BeeSting(Exception):
    """For exceptions raised by this module

    Provides log style message passing like::

            raise BeeSting("%s bla %s", arg1, arg2)
    """
    def __init__(self, msg, *args):
        if args:
            try:
                msg = msg % (args)
            except:
                msg = "[PLEASE FIX MESSAGE]: %s %s" % (msg, str(args))
        Exception.__init__(self, msg)


class LoggingConfig(object):
    NAME = 'bees'

    def __init__(self):
        self.workPath = LocalWorkdir()
        self.localLogPath = None
        """:type: LocalPath"""

    def init_logging(self, logLevel=logging.INFO, logToFile=True):
        log.setLevel(logLevel)
        self.localLogPath = self.workPath / (self.NAME + '.log')
        fmt = ('%(asctime)s %(name)s %(funcName)s:%(lineno)d '
               '%(levelname)s : %(message)s')
        logging.basicConfig(format=fmt)
        if logToFile:
            fh = logging.FileHandler(filename=str(self.localLogPath))
            fh.setFormatter(logging.Formatter(fmt))
            log.addHandler(fh)
        log.name = self.NAME if log.name == '__main__' else log.name
        log.debug("working in %s", self.workPath)
