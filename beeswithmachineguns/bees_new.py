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
import os

import boto
import boto.ec2
from plumbum.path import LocalPath, LocalWorkdir
import plumbum.path.utils as plumbum_utils

import lib as beelib


log = logging.getLogger('bees')


class Beekeeper(object):
    def __init__(self, cnf=None, connection=None):
        self.cnf = cnf or Config()
        self.connection = connection
        self.swarm = None
        self.healthcheck()

    def up(self):
        self._find_bees()

    def attack(self):
        pass
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
        # print self.remote[self.battleCry.command](self.battleCry.specifics)
        # todo just fetch raw data for starters

    def down(self):
        self._find_bees(nocreate=True)
        self._scatter_bees()

    def _find_bees(self, nocreate=False):
        if self.cnf.activeSwarmId:
            log.info("remembering bees at %s:%s",
                     self.cnf.REGION, self.cnf.activeSwarmId)
            self.connection = self._get_connection(self.cnf.REGION)
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
                self.cnf.activeSwarmId = self.swarm.id
                self.cnf.save()
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
            if swarm.id == self.cnf.activeSwarmId:
                return swarm

    def _scatter_bees(self):
        """call off the swarm"""
        ids = sorted([i.id for i in self.swarm.instances])
        log.info('scatter swarm %s', ids)
        termInstances = self.connection.terminate_instances(instance_ids=ids)
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
    KEY_EXT = '.pem'
    DEFAULTS = dict(
        numberOfBees=10,
        zone='us-east-1d',
        instanceType='t1.micro',
        instanceId='ami-ff17fb96',
        securityGroups=['default'],
        placement=None,
        subnetId='',
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
        self.activeSwarmId = self.DEFAULTS['activeSwarmId']
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

    def __init__(self, fqdn, keyFilePath):
        beelib.BeeBrain.__init__(self, self.NAME)
        beelib.BeeWhisperer.__init__(self, fqdn, keyFilePath)
        self.url = self.DEFAULTS['url']
        self.command = self.DEFAULTS['command']
        self.numberOfRequests = self.DEFAULTS['numberOfRequests']
        self.concurrency = self.DEFAULTS['concurrency']
        self.postfilePath = self.DEFAULTS['postfilePath']
        self.mimeType = self.DEFAULTS['mimeType']
        self.additionalOptions = self.DEFAULTS['additionalOptions']
        self.load()
        self.post_process()
        self.battleCry = BattleCry(self.command)

    def post_process(self):
        if not os.path.isabs(self.postfilePath):
            self.postfilePath = self._workPath / self.postfilePath

    def contrive_battle_plan(self):
        self._create_exchange_file()
        if self.postfilePath:
            self._prepare_post()
        self.battleCry.clarify(self.url)

    def _create_exchange_file(self):
        tmpFilePath = self.remote['mktemp']().strip()
        self.battleCry.clarify(['-e', tmpFilePath])

    def _prepare_post(self):
        plumbum_utils.copy(self.postfilePath, self.remote.cwd)
        self.battleCry.clarify(['-T', self.mimeType, '-p',
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

    # time.sleep(0.01)
    # for k, v in cnf.__dict__.items():
    #     print k, v
    # print cnf.beesIds
