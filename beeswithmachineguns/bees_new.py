"""based on beeswithmachineguns

* separated configuration and core functionality

* class based approach
  (two reasons:
    * ease of testing
    * functionality easily adjustable by overwriting methods

* thrown out subnet stuff, as I don't understand the currrent implementation
  (seems somewhat nonsensical to me ...)

* thrown out (very specific) gov stuff (can be easily overriden)

* output is logged instead of printed
"""
import logging
from multiprocessing import Pool
import os
import traceback

import boto.ec2
from plumbum.path import LocalPath, LocalWorkdir
import plumbum.path.utils as plumbum_utils

import lib as beelib


log = logging.getLogger('bees')


class BattlePack(object):
    """All the bee needs to take over the process border"""
    def __init__(self, beeId, fqdn, keyPath, username, battleCry):
        self.beeId = beeId
        self.fqdn = fqdn
        # stringify keyPath: multiprocessing borks on LocalPath objects
        self.keyPath = str(keyPath)
        self.username = username
        self.battleCry = battleCry


def async_worker(pack):
    """do the work in an independent process"""
    try:
        bw = beelib.BeeWhisperer(pack.fqdn, pack.keyPath, pack.username)
        battleCry = pack.battleCry
        return bw.remote[battleCry.command](battleCry.specifics)

    except:
        return traceback.format_exc()


class Beekeeper(object):
    def __init__(self, cnf=None, connection=None):
        self.cnf = cnf or Config()
        self._connection = connection
        self.swarm = None
        self.healthcheck()

    def up(self):
        self._find_bees()

    def attack(self):
        """
        'concurrent_requests': connections_per_instance,
        'num_requests': requests_per_instance,
        """
        instances = self.swarm.instances
        pool = Pool(len(instances))
        battlePacks = []
        for instance in instances:
            fqdn = instance.public_dns_name
            keyPath = self.cnf.KEY_PATH
            username = self.cnf.username
            battlePlan = BattlePlan(fqdn, keyPath, username)
            battleCry = battlePlan.contrive()
            pack = BattlePack(beeId=instance.id, fqdn=fqdn, keyPath=keyPath,
                              username=username, battleCry=battleCry)
            battlePacks.append(pack)
        results = pool.map(async_worker, battlePacks)
        for result in results:
            print beelib.oa(result)

    def down(self):
        self._find_bees(nocreate=True)
        self._scatter_bees()

    def _find_bees(self, nocreate=False):
        if self.cnf.activeSwarmId:
            log.info("remembering bees at %s:%s",
                     self.cnf.REGION, self.cnf.activeSwarmId)
            self._connection = self._get_connection(self.cnf.REGION)
            self.swarm = self._assemble_old_bee_friends()
        else:
            log.info("no bees on my mind ...")
            if nocreate:
                return

            log.info("creating a swarm ...")
            self._connection = self._get_connection(self.cnf.REGION)
            self.swarm = self._invite_new_bee_friends()
            self._weaponize_bees()
        log.debug("using swarm %s", beelib.oa(self.swarm))

    def _weaponize_bees(self):
        log.info('waiting for bees to load their machine guns... ')
        instances = self.swarm.instances
        while True:
            beesIds = self.get_flying_bees_ids(instances)
            beeCount = len(beesIds)
            if len(beesIds) == len(instances):
                self._connection.create_tags(beesIds, {"Name": "a bee!"})
                self.cnf.activeSwarmId = self.swarm.id
                self.cnf.save()
                log.info('bees ready to attack: %s', beeCount)
                print
                break

            print '.',

    def _invite_new_bee_friends(self):
        log.info("arming the bees ...")
        swarm = self._connection.run_instances(
            image_id=self.cnf.instanceId,
            min_count=self.cnf.numberOfBees,
            max_count=self.cnf.numberOfBees,
            key_name=self.cnf.KEY_NAME,
            security_groups=self.cnf.securityGroups,
            instance_type=self.cnf.instanceType,
            placement=self.cnf.placement,
            subnet_id=self.cnf.subnetId)
        return swarm

    def _assemble_old_bee_friends(self):
        swarms = self._connection.get_all_reservations()
        for swarm in swarms:
            if swarm.id == self.cnf.activeSwarmId:
                return swarm

    def _scatter_bees(self):
        """call off the swarm"""
        ids = sorted([i.id for i in self.swarm.instances])
        log.info('scatter swarm %s', ids)
        termInstances = self._connection.terminate_instances(instance_ids=ids)
        tIds = sorted([i.id for i in termInstances])
        if ids != tIds:
            log.warning("not all bees scattered: %s != %s", ids, tIds)
        self.cnf.activeSwarmId = None
        self.cnf.save()

    def get_flying_bees_ids(self, instances):
        instanceIds = []
        for instance in instances:
            instance.update()
            if instance.state == 'running':
                instanceIds.append(instance.id)
        return instanceIds

    def healthcheck(self):
        if not self.cnf.KEY_PATH:
            raise beelib.BeeSting(
                "no key found (looked for (%s)", self.cnf.KEY_SEARCH_PATHS)

    def _get_connection(self, region):
        """ec2 connection object for commanding the swarm"""
        return boto.ec2.connect_to_region(region)


class Config(beelib.BeeBrain):
    NAME = 'bees_config.json'
    """Global configuration"""
    KEY_NAME_PREFIX = "aws-ec2"
    DEFAULT_KEY_EXT = '.pem'
    DEFAULTS = dict(
        numberOfBees=3,
        zone='us-east-1d',
        instanceType='t1.micro',
        instanceId='ami-ff17fb96',
        securityGroups=['default'],
        placement=None,
        subnetId='',
        keyPath=None,
        username='newsapps',
        activeSwarmId=None)

    def __init__(self):
        super(Config, self).__init__(self.NAME)
        self.numberOfBees = self.DEFAULTS['numberOfBees']
        self.zone = self.DEFAULTS['zone']
        self.instanceType = self.DEFAULTS['instanceType']
        self.instanceId = self.DEFAULTS['instanceId']
        self.securityGroups = self.DEFAULTS['securityGroups']
        self.placement = self.DEFAULTS['placement']  # fixme gov?
        self.subnetId = self.DEFAULTS['subnetId']  # fixme useless atm
        self._keyPath = self.DEFAULTS['keyPath']
        self._keyExt = self.DEFAULT_KEY_EXT
        self.username = self.DEFAULTS['username']
        self.activeSwarmId = self.DEFAULTS['activeSwarmId']
        self.load()

    @beelib.cached_property
    def REGION(self):
        """ region = zone without last letter """
        return self.zone[:-1]

    @beelib.cached_property
    def KEY_PATH(self):
        for candidate in self.KEY_SEARCH_PATHS:
            if candidate.exists():
                return candidate

        # todo implement usage of ssh agent
        raise beelib.BeeSting("no key found in %s", self.KEY_SEARCH_PATHS)

    @beelib.cached_property
    def KEY_SEARCH_PATHS(self):
        searchPaths = [self._workPath, LocalPath(os.getenv('HOME')) / '.ssh']
        return [path / (self.KEY_NAME + self._keyExt) for path in searchPaths]

    @beelib.cached_property
    def KEY_NAME(self):
        if self._keyPath:
            name, ext = os.path.splitext(os.path.basename(self._keyPath))
            self._keyExt = ext
            return name

        return "%s-%s" % (self.KEY_NAME_PREFIX, self.REGION)


class BattlePlan(beelib.BeeBrain, beelib.BeeWhisperer):
    NAME = 'bees_battle_plan.json'
    DEFAULTS = dict(
        command='ab',
        numberOfRequests=100,
        concurrency=10,
        url='http://update-bridge-oliver-y5rxgpaear.elasticbeanstalk.com/',
        postfilePath='bees_post_data.json',
        mimeType='application/json;charset=UTF-8',
        additionalOptions=['-r'])

    def __init__(self, fqdn, keyFilePath, username):
        beelib.BeeBrain.__init__(self, self.NAME)
        beelib.BeeWhisperer.__init__(self, fqdn, keyFilePath, username)
        self.url = self.DEFAULTS['url']
        self.command = self.DEFAULTS['command']
        self.numberOfRequests = self.DEFAULTS['numberOfRequests']
        self.concurrency = self.DEFAULTS['concurrency']
        self.postfilePath = self.DEFAULTS['postfilePath']
        self.mimeType = self.DEFAULTS['mimeType']
        self.additionalOptions = self.DEFAULTS['additionalOptions']
        self.load()
        self.post_process()
        self._battleCry = BattleCry(self.command)

    def post_process(self):
        if not os.path.isabs(self.postfilePath):
            self.postfilePath = self._workPath / self.postfilePath

    def contrive(self):
        self._battleCry.clarify(['-n', str(self.numberOfRequests)])
        self._battleCry.clarify(['-c', str(self.concurrency)])
        self._create_exchange_file()
        self._battleCry.clarify(self.additionalOptions)
        if self.postfilePath:
            self._prepare_post()
        self._battleCry.clarify(self.url)
        return self._battleCry

    def _create_exchange_file(self):
        tmpFilePath = self.remote['mktemp']().strip()
        self._battleCry.clarify(['-e', tmpFilePath])

    def _prepare_post(self):
        plumbum_utils.copy(self.postfilePath, self.remote.cwd)
        self._battleCry.clarify(['-T', self.mimeType, '-p',
                                self.postfilePath.basename])


class BattleCry(object):
    def __init__(self, command):
        super(BattleCry, self).__init__()
        self.command = command
        self._elems = []

    def clarify(self, fragment):
        if isinstance(fragment, str):
            fragment = fragment.split(' ')
        self._elems.extend(fragment)

    @property
    def specifics(self):
        return self._elems

    def __str__(self):
        return '%s %s' % (self.command, ' '.join(self._elems))


def main():
    pass

if __name__ == '__main__':
    workPath = LocalWorkdir()
    workPath.chdir('../tests/fake_project_dir')
    beelib.LoggingConfig().init_logging()
    main()
