"""based on beeswithmachineguns

* separated configuration and core functionality

* class based approach
  (two reasons:
    * ease testing
    * functionality easily adjustable by by overwriting methods

* thrown out subnet stuff, as I don't understand the currrent implementation
  (seems somewhat nonsensical to me ...)

* thrown out (very specific) gov stuff (can easily overriden)

* output is logged instead of printed
"""
import logging
import os

import boto
import boto.ec2
from boto.ec2.ec2object import EC2Object
from plumbum import SshMachine
from plumbum.path import LocalPath, LocalWorkdir
import plumbum.path.utils as plumbum_utils

import lib as beelib


log = logging.getLogger('bees')


class Beekeeper(object):
    def __init__(self, cnf=None, mem=None, connection=None):
        self.cnf = cnf or Config()
        self.mem = mem or SwarmMemory()
        self.connection = connection
        self.swarm = None
        self.healthcheck()

    def up(self):
        self._find_bees()

    def attack(self):
        pass

    def down(self):
        self._find_bees(nocreate=True)
        self._scatter_bees()

    def _find_bees(self, nocreate=False):
        if self.mem:
            log.info("remembering bees at %s", self.mem.asDict)
            self.connection = self._get_connection(self.mem.region)
            self.swarm = self._assemble_old_bee_friends()
        else:
            log.info("no bees on my mind ...")
            if nocreate:
                return

            log.info("creating a swarm ...")
            self.connection = self._get_connection(self.cnf.REGION)
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
                self.connection.create_tags(beesIds, {"Name": "a bee!"})
                self.mem.swarmId = self.swarm.id
                self.mem.region = self.cnf.REGION
                self.mem.remember()
                log.info('bees ready to attack: %s', beeCount)
                print
                break

            print '.',

    def _invite_new_bee_friends(self):
        log.info("arming the bees ...")
        swarm = self.connection.run_instances(
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
        swarms = self.connection.get_all_reservations()
        for swarm in swarms:
            if swarm.id == self.mem.swarmId:
                return swarm

    def _scatter_bees(self):
        """call off the swarm"""
        ids = sorted([i.id for i in self.swarm.instances])
        log.info('scatter swarm %s', ids)
        termInstances = self.connection.terminate_instances(instance_ids=ids)
        tIds = sorted([i.id for i in termInstances])
        if ids != tIds:
            log.warning("not all bees scattered: %s != %s", ids, tIds)
        self.mem.forget()

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


class Config(beelib.JsonStorage):
    NAME = 'bees_config.json'
    """Global configuration"""
    KEY_NAME_PREFIX = "aws-ec2"
    KEY_EXT = '.pem'
    DEFAULT_NUMBER_OF_BEES = 10
    DEFAULT_ZONE = 'us-east-1d'
    DEFAULT_INSTANCE_ID = 'ami-ff17fb96'
    DEFAULT_SECURITY_GROUPS = ['default']
    DEFAULT_INSTANCE_TYPE = 't1.micro'
    DEFAULT_PLACEMENT = None
    DEFAULT_SUBNET_ID = ''

    def __init__(self):
        super(Config, self).__init__(self.NAME)
        self.numberOfBees = self.DEFAULT_NUMBER_OF_BEES
        self.zone = self.DEFAULT_ZONE
        self.securityGroups = self.DEFAULT_SECURITY_GROUPS
        self.instanceId = self.DEFAULT_INSTANCE_ID
        self.instanceType = self.DEFAULT_INSTANCE_TYPE
        self.placement = self.DEFAULT_PLACEMENT  # fixme for gov stuff?
        self.subnetId = self.DEFAULT_SUBNET_ID  # fixme useless atm
        self.load()

    @property
    def REGION(self):
        """ region = zone without last letter """
        return self.zone[:-1]

    @beelib.cached_property
    def KEY_PATH(self):
        for candidate in self.KEY_SEARCH_PATHS:
            if candidate.exists():
                return candidate

        log.warning("no key found in %s", self.KEY_SEARCH_PATHS)

    @beelib.cached_property
    def KEY_SEARCH_PATHS(self):
        searchPaths = [self._workPath, LocalPath(os.getenv('HOME')) / '.ssh']
        return [path / (self.KEY_NAME + self.KEY_EXT) for path in searchPaths]

    @property
    def KEY_NAME(self):
        return "%s-%s" % (self.KEY_NAME_PREFIX, self.REGION)


class SwarmMemory(beelib.JsonStorage):
    NAME = 'bees_swarm_memory.json'
    """reservation id of bee active swarm"""

    def __init__(self):
        super(SwarmMemory, self).__init__(self.NAME)
        self.swarmId = None
        self.load()

    def remember(self):
        self.save()

    def forget(self):
        self.remove()


class BattlePlan(beelib.JsonStorage):
    NAME = 'bees_battle_plan.json'
    DEFAULTS = dict(
        url='update-bridge-oliver-y5rxgpaear.elasticbeanstalk.com',
        numberOfRequests=100,
        concurrency=10,
        postfilePath='bees_post_data.json',
        mimeType='application/json; charset=UTF-8')

    def __init__(self):
        super(BattlePlan, self).__init__(self.NAME)
        self.url = self.DEFAULTS.get('url')
        self.numberOfRequests = self.DEFAULTS.get('numberOfRequests')
        self.concurrency = self.DEFAULTS.get('concurrency')
        self.postfilePath = self.DEFAULTS.get('postfilePath')
        self.mimeType = self.DEFAULTS.get('mimeType')
        self.load()
        self.post_process()

    def post_process(self):
        if not os.path.isabs(self.postfilePath):
            self.postfilePath = self._workPath / self.postfilePath


class BattleCry(object):
    def __init__(self, cmd='ab'):
        super(BattleCry, self).__init__()
        self._cmd = cmd
        self._elems = []

    def enhance(self, fragment):
        self._elems.extend(fragment.split(' '))

    def enunciate(self):
        return [self._cmd] + self._elems

    def __str__(self):
        return '%s %s' % (self._cmd, ' '.join(self._elems))


class BeeWisperer(object):
    DEFAULT_USER = 'newsapps'

    # todo swarm? instance?
    def __init__(self, fqdn, keyFilePath, username=None, battlePlan=None):
        self.fqdn = fqdn
        self.username = username or self.DEFAULT_USER
        self.keyFilePath = keyFilePath
        self.battlePlan = battlePlan or BattlePlan()
        self._whisperer = None
        self.battleCry = BattleCry()
        self._sshKwargs = dict(
            host=self.fqdn, user=self.username, keyfile=self.keyFilePath,
            ssh_opts=['-oStrictHostKeyChecking=no'])

    def __del__(self):
        try:
            self.remote.close()
        except:
            log.warning('tidy up failed', exc_info=True)

    def contrive_battle_plan(self):
        self._create_exchange_file()
        if self.battlePlan.postfilePath:
            self._prepare_post()
        self.battleCry.enhance('http://avira.com/')

    def _create_exchange_file(self):
        tmpFilePath = self.remote['mktemp']().strip()
        self.battleCry.enhance('-e %s' % (tmpFilePath))

    def _prepare_post(self):
        plumbum_utils.copy(self.battlePlan.postfilePath, self.remote.cwd)
        self.battleCry.enhance(
            '-T "%s" -p %s' %
            (self.battlePlan.mimeType,
             self.battlePlan.postfilePath.basename))

    def attack(self):
        """
        params.append({
        'i': i,
        'instance_id': instance.id,
        'instance_name': instance.public_dns_name,
        'url': url,
        'concurrent_requests': connections_per_instance,
        'num_requests': requests_per_instance,
        'username': username,
        'key_name': key_name,
        'headers': headers,
        'cookies': cookies,
        'post_file': options.get('post_file'),
        'keep_alive': options.get('keep_alive'),
        'mime_type': options.get('mime_type', ''),
        'tpr': options.get('tpr'),
        'rps': options.get('rps'),
        'basic_auth': options.get('basic_auth')
        })
        """
        with SshMachine(**self._sshKwargs) as rem:
            plumbum_utils.copy(self.battlePlan.postfilePath, rem.cwd)
            # print rem['ab']('-n 1000 -c 200 -u http://google.de/'.split(' '))
            print rem['ls']('-la')
        # todo just fetch raw data for starters

    @beelib.cached_property
    def remote(self):
        return SshMachine(**self._sshKwargs)


def main():
    pass

if __name__ == '__main__':
    workPath = LocalWorkdir()
    workPath.chdir('../tests/fake_project_dir')
    beelib.LoggingConfig().init_logging()
    main()

    # time.sleep(0.01)
    # for k, v in cnf.__dict__.items():
    #     print k, v
    # print cnf.beesIds
