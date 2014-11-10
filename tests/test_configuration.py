from beeswithmachineguns.bees_new import Environment


class TestBeeConfigurator(object):
    def test_env(self):
        env = Environment()
        assert env.home.startswith('/home')
