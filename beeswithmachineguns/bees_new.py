"""based on beeswithmachineguns

* separated configuration and core functionality

* output is logged instead of printed

* class based approach
  (two reasons:
    * ease testing
    * functionality easily adjustable by by overwriting methods

* thrown out subnet stuff, as I don't understand the currrent implementation
  (seems somewhat nonsensical to me ...)
"""
import inspect
import simplejson as json
import logging
from plumbum.path import LocalPath, RemotePath, LocalWorkdir

from beeswithmachineguns.bees import *
from beeswithmachineguns.obj_inspection import obj_attr


log = logging.getLogger(__name__)


class BeeSting(Exception):
    """class for exceptions raised by this module"""
    pass


class JsonConfigger(object):
    def __init__(self, configPath):
        self._configPath = LocalPath(configPath)

    def load_config(self):
        config = json.loads(self._configPath.read())
        for key, value in config.items():
            log.debug("read from _config: %s <- %s", key, value)
            setattr(self, key, value)

    def save_config(self):
        self._configPath.write(json.dumps(self.get_config()))

    def remove_config(self):
        self._configPath.delete()

    def get_config(self):
        attrs = {k: self._nrmlz(v) for k, v in self.__dict__.items()
                 if not k.startswith('_')}
        props = {k: self._nrmlz(getattr(self, k)) for k in self._publicProps}
        attrs.update(props.items())
        return attrs

    @property
    def _publicProps(self):
        return [name for (name, member) in inspect.getmembers(self.__class__)
                if not name.startswith('_') and type(member) == property]

    def _nrmlz(self, value):
        """normalize strange things to json compatible values"""
        if isinstance(value, str):
            return value

        if isinstance(value, LocalPath):
            return str(value)

        if isinstance(value, list):
            return [self._nrmlz(v) for v in value]

        return value


class ProjectConfig(JsonConfigger):
    CONFIG = 'hive.json'
    """Global configuration"""
    KEY_NAME_PREFIX = "aws-ec2"
    DEFAULT_SECURITY_GROUP = 'default'
    DEFAULT_ZONE = 'us-east-1d'
    DEFAULT_INSTANCE_ID = 'ami-ff17fb96'
    DEFAULT_INSTANCE_TYPE = 't1.micro'

    DEFAULT_NUMBER_OF_BEES = 10

    def __init__(self):
        super(ProjectConfig, self).__init__(self.CONFIG)
        self._keyContainerPaths = [self._configPath.dirname,
                                   LocalPath(os.getenv('HOME')) / '.ssh']
        self.securityGroupNames = [self.DEFAULT_SECURITY_GROUP]
        self.zone = self.DEFAULT_ZONE
        self.instanceId = self.DEFAULT_INSTANCE_ID
        self.numberOfBees = self.DEFAULT_NUMBER_OF_BEES
        self.instanceType = self.DEFAULT_INSTANCE_TYPE

    @property
    def region(self):
        """calculate region from configured zone:
            * keep unchanged for gov zones
            * chop off the last letter in e.g. "us-east-1d"
        """
        return self.zone if self.isGovZone else self.zone[:-1]

    @property
    def isGovZone(self):
        return 'gov' in self.zone

    @property
    def keyPath(self):
        if not hasattr(self, '_keyPath'):
            for path in self._keyContainerPaths:
                potentialKeyPath = path / self.keyName
                log.debug("try key path %s", potentialKeyPath)
                if potentialKeyPath.exists():
                    self._keyPath = potentialKeyPath
                    break
            else:
                raise BeeSting(
                    'no key named %s found in %s' %
                    (self.keyName, self._keyContainerPaths))

        return self._keyPath

    @property
    def keyName(self):
        return "%s-%s.pem" % (self.KEY_NAME_PREFIX, self.region)


class Ec2Connection(object):
    def __init__(self, **kwargs):
        self.zone = kwargs.get('zone')
        self.isGovZone = kwargs.get('isGovZone')
        self.region = kwargs.get('region')
        self.securityGroupNames = kwargs.get('securityGroupNames')
        self.instanceId = kwargs.get('instanceId')
        self.instanceType = kwargs.get('instanceType')
        self.numberOfBees = kwargs.get('numberOfBees')
        self.keyName = LocalPath(kwargs.get('keyName'))
        self.keyPath = LocalPath(kwargs.get('keyPath'))
        self._connection = None

    @property
    def securityGroupIds(self):
        return [group.vpc_id for group in self.securityGroups]

    @property
    def securityGroups(self):
        return [g for g in self._allSecurityGroups
                if g.name in self.securityGroupNames]

    @property
    def _allSecurityGroups(self):
        return self.connection.get_all_security_groups()

    @property
    def connection(self):
        if not self._connection:
            self._connection = boto.ec2.connect_to_region(self.region)
        return self._connection


class CurrentHive(JsonConfigger):
    CONFIG = 'current.json'
    """configuration of an active bee hive (autogenerated)"""

    def __init__(self):
        super(CurrentHive, self).__init__(self.CONFIG)
        self.username = ''
        self.zone = ''
        self.beesIds = ''

    @property
    def isActive(self):
        return self._configPath.exists()


class Beekeeper(object):
    def __init__(self):
        self.bees = None

    @property
    def hive(self):
        if not hasattr(self, '_hive'):
            self._hive = CurrentHive()
        return self._hive

    @property
    def connectionWrapper(self):
        if not hasattr(self, '_connectionWrapper'):
            projectConfig = ProjectConfig()
            self._connectionWrapper = Ec2Connection(
                **projectConfig.get_config())
        return self._connectionWrapper

    @property
    def connection(self):
        if not hasattr(self, '_connection'):
            self._connection = self.connectionWrapper.connection
        return self._connection

    def _reserve_bees(self):
        if self.hive.isActive:
            log.warning("hive is up already: %s", self.hive.get_config())
            return

        if not self.connectionWrapper.keyPath.exists():
            raise BeeSting("key %s not found" % (self.connectionWrapper.keyPath))

        log.info(
            'attempting to call up %s bees' %
            (self.connectionWrapper.numberOfBees))
        reservation = self.connection.run_instances(
            image_id=self.connectionWrapper.instanceId,
            min_count=self.connectionWrapper.numberOfBees,
            max_count=self.connectionWrapper.numberOfBees,
            key_name=self.connectionWrapper.keyName,
            security_groups=self.connectionWrapper.securityGroupIds,
            instance_type=self.connectionWrapper.instanceType,
            placement=(None if self.connectionWrapper.isGovZone
                       else self.connectionWrapper.zone),
            subnet_id='')
        self._reservation = reservation

    def up(self):
        self._reserve_bees()
        while not self.allBeesAreUp:
            log.info('waiting for bees to load their machine guns... '
                     '%s bees are ready', self.activeBeesIds)
        self.connection.create_tags(self.activeBeesIds, {"Name": "a bee!"})
        self._hive.save_config()
        log.info('The swarm has assembled %i bees',
                 len(self._reservation.instances))

    @property
    def allBeesAreUp(self):
        return len(self.activeBeesIds) == self.connectionWrapper.numberOfBees

    @property
    def activeBeesIds(self):
        instanceIds = []
        for instance in self._reservation.instances:
            instance.update()
            if instance.state == 'running':
                instanceIds.append(instance.id)
        return instanceIds


class LoggingConfig(object):
    NAME = 'bees'

    def __init__(self):
        self.workPath = LocalWorkdir()
        self.localLogPath = None
        """:type: LocalPath"""

    def init_logging(self, logLevel=logging.INFO, logToFile=True):
        log.setLevel(logLevel)
        self.localLogPath = self.workPath / (self.NAME + '.log')
        fmt = '%(asctime)s %(name)s %(levelname)s: %(message)s'
        logging.basicConfig(format=fmt)
        if logToFile:
            fh = logging.FileHandler(filename=str(self.localLogPath))
            fh.setFormatter(logging.Formatter(fmt))
            log.addHandler(fh)
        log.name = self.NAME if log.name == '__main__' else log.name
        log.debug("working in %s", self.workPath)


def main(workingPath=None):
    workPath = LocalWorkdir()
    if workingPath:
        workPath.chdir(workingPath)
    log.info('working in %s', workPath)
    logCnf = LoggingConfig()
    logCnf.init_logging(logLevel=logging.DEBUG)
    cnf = ProjectConfig()

    print cnf.numberOfBees
    print cnf._config

    ec2 = Ec2Connection(**cnf._config)
    # for g in ec2._allSecurityGroups:
    #     print obj_attr(g)
    print ec2.securityGroupIds
    exit()

    print ec2.connection
    print ec2.__dict__.items()
    print type(ec2.connection)

    exit()
    hive = CurrentHive()
    print hive.isActive
    if hive.isActive:
        hive.load_config()
    print hive.isActive
    # print hive._config
    # print hive.isConfigured
    print hive._config


if __name__ == '__main__':
    main('../tests/fake_project_dir')

    # time.sleep(0.01)
    # for k, v in cnf.__dict__.items():
    #     print k, v
    # print cnf.beesIds
