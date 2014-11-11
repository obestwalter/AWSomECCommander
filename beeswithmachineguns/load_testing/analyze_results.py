from beeswithmachineguns.lib import cached_property, oa


class LoadInformer(object):
    def __init__(self, resultsPath='results.txt'):
        """All times in milliseconds"""
        self.resultsPath = resultsPath
        self.numberOfTests = 0
        self.timePerRequest = []
        """Time per request:		12.510200 [ms] (mean of bees)"""
        self.failedRequests = []
        """Failed requests:		0"""
        self.requestsPerSecond = []
        """Requests per second:	10215.130000 [#/sec] (mean of bees)"""
        self.fiftyPercentFasterThan = []
        """50% responses faster than:	8.594000 [ms]"""
        self.ninetyPercentFasterThan = []
        """90% responses faster than:	24.440000 [ms]"""

    def get_avg(self, l):
        return sum(l) / len(l)

    def populate(self):
        txtAttrMap = {
            'Time per request': 'timePerRequest',
            'Failed requests': 'failedRequests',
            'Requests per second': 'requestsPerSecond',
            '50% responses faster than': 'fiftyPercentFasterThan',
            '90% responses faster than': 'ninetyPercentFasterThan',
        }
        for line in self._lines:
            for trigger, attrName in txtAttrMap.items():
                if trigger in line:
                    attr = getattr(self, attrName)
                    attr.append(self.get_number(line))

    def get_number(self, line):
        rightSide = line.split('\t')[-1]
        return float(rightSide.split(' ')[0])

    @cached_property
    def _lines(self):
        with open(self.resultsPath) as f:
            lines = []
            for line in f:
                if line.startswith('    '):
                    lines.append(line.strip())
        return lines


if __name__ == '__main__':
    li = LoadInformer()
    li.populate()
    print oa(li)
