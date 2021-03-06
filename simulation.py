#import matplotlib.pyplot as plt

'''
This is the meat of this entire project.
'''
from assets import Assets
from market_data import getInflation
from portfolio import Portfolio
import json
from json import encoder
#encoder.FLOAT_REPR = lambda o: format(o, '.2f')

def runSimulation(length, initialPortfolio, failureThreshhold, initStrategies, minSimYear, maxSimYear, ignoreInflation=False):
    simulation = Simulation(minSimYear, maxSimYear, length, ignoreInflation, initialPortfolio, failureThreshhold)
    strategies = []
    initPortfolios = []
    totalWeight = 0.0
    for s in initStrategies:
        strategies.append(s[0])
        initPortfolios.append(Portfolio(s[1], s[2] * initialPortfolio))
        totalWeight += s[2]

    if abs(totalWeight - 1.0) > .0009:
        raise RuntimeError("Your weights don't add up to 1.0")

    simulationIteration = 0
    # why 2? python and last year of the simlulation are both exclusive
    for startYear in range(minSimYear, maxSimYear - length + 2):
        for i in range(0, len(strategies)):
            portfolio = initPortfolios[i].copy()
            strategies[i].reset(portfolio)

        candidateFailureYear = None
        inflationRate = None
        try:
            underflow= 0.0
            overflow = 0.0
            for simulationYear in range(startYear, startYear + length + 1):
                candidateFailureYear = simulationYear
                inflationRate = getInflation(startYear - 1, simulationYear - 1)
                if ignoreInflation:
                    inflationRate = 1.0
                failMin = failureThreshhold * inflationRate
                numPeriodsPerYear = 12 # 12 == months, etc. Actually it is a farce to pretend anything other than 12 works here.
                for month in range(1, numPeriodsPerYear + 1):
                    monthGrowth = Assets.getMarketReturns(simulationYear, month)
                    actualWithdrawal = 0.0
                    for i in range(0, len(strategies)):
                        actualWithdrawal += strategies[i].withdraw(inflationRate, numPeriodsPerYear)
                        strategies[i].grow(monthGrowth)
                    currentPortfolioValue = sum(s.getPortfolioValue() for s in strategies) / inflationRate
                    simulation.recordData(simulationIteration, simulationYear, month, actualWithdrawal / inflationRate, currentPortfolioValue)
                    diff = actualWithdrawal - (sum(s.getInitialWithDrawal() / numPeriodsPerYear for s in strategies) * inflationRate)
                    if actualWithdrawal <= .99999 * failMin / numPeriodsPerYear:
                        raise StopIteration
                    if diff < 0:
                        underflow += diff / inflationRate
                    else:
                        overflow += diff / inflationRate
            simulation.recordSuccess()
        except StopIteration:
            simulation.recordFailure(startYear, candidateFailureYear)
        finally:
            simulation.endPortfolioValue.append(sum(s.getPortfolioValue() for s in strategies) / inflationRate)
            simulation.underflow.append(underflow)
            simulation.overflow.append(overflow)
            simulation.endRelativeInflation.append(inflationRate)
            simulationIteration += 1
    simulation.finalize()
    return simulation

class Simulation:
    def __init__(self, minYear, maxYear, length, ignoreInflation, initialPortfolio, failureThreshhold):
        self.minYear = minYear
        self.maxYear = maxYear
        self.length = length
        self.ignoreInflation = ignoreInflation
        self.initialPortfolio = initialPortfolio
        self.failureThreshhold = failureThreshhold
        self.iterations = 0
        self.failures = []
        self.underflow = []
        self.overflow = []
        self.endPortfolioValue = []
        self.endRelativeInflation = []

        # this is a list of lists, where the top level list is per simulation and the second
        # dimension list is a tuple of (year, month, withdrawal, portfolioValue). Year and
        # month aren't strictly necessary (can be inferred from other data),but make it easier to debug.
        self.recordedData = []

    def getSimResults(self):
        results = []
        for i in range(0, self.iterations):
            ps = []
            ws = []

            p = None
            for y in range(0, self.length + 1):
                wAccumulator = 0
                for m in range(0,12):
                    if len(self.recordedData[i]) > m+(y*12):
                        wAccumulator += self.recordedData[i][m+(y*12)][2]
                        p = self.recordedData[i][m+(y*12)][3]
                    else:
                        wAccumulator += 0
                ps.append(p)
                ws.append(wAccumulator)

            results.append({"portfolio_values" : ps, "withdrawals" : ws})
        return results

    def getStats(self):
        stats = {
            "success_rate": self.getSuccessRate(),
            "underflow": gatherWebResponseData(self.underflow),
            "overflow": gatherWebResponseData(self.overflow),
            "legacy": gatherWebResponseData(self.endPortfolioValue)
        }
        return stats

    def recordData(self, simIteration, year, month, withdrawal, portfolioValue):
        if len(self.recordedData) < simIteration + 1:
            self.recordedData.append([])
        self.recordedData[simIteration].append((year, month, withdrawal, portfolioValue))

    def recordSuccess(self):
        self.iterations += 1

    def recordFailure(self, startYear, endYear):
        self.iterations += 1
        self.failures.append((startYear, endYear))

    def getSuccessRate(self):
        return 1 - (len(self.failures) / self.iterations)

    def finalize(self):
        if self.iterations != len(self.underflow):
            raise RuntimeError
        if self.iterations != len(self.overflow):
            raise RuntimeError
        if self.iterations != len(self.endPortfolioValue):
            raise RuntimeError
        if self.iterations != len(self.endRelativeInflation):
            raise RuntimeError

    def __str__(self):
        output = []
        output.append("Simulation run over all {0} year periods from {1} to {2}"
                      .format(self.length, self.minYear, self.maxYear))
        if self.ignoreInflation:
            output.append("You have opted to ignore inflation (why?!) so all numbers given are not inflation adjusted")
        else:
            output.append("All numbers are inflation adjusted")

        output.append("Success Rate: {0:.2f} Initial Portfolio: {1} Failure Threshhold: {2}"
                      .format(self.getSuccessRate(), self.initialPortfolio, self.failureThreshhold))

        output.append("")
        output.append("Measure   \tMean\tMin\t5%tile\t50%tile\t95%tile\tMax")
        output.append('\t'.join(gatherData("Legacy    ", self.endPortfolioValue)))
        output.append('\t'.join(gatherData("UnderFlow ", self.underflow)))
        output.append('\t'.join(gatherData("OverFlow  ", self.overflow)))

        return '\n'.join(output)

def gatherData(name, iter):
    return (name,
            "{0:.2f}".format(getMean(iter)),
            "{0:.2f}".format(min(iter)),
            "{0:.2f}".format(getPercentile(iter, .05)),
            "{0:.2f}".format(getPercentile(iter, .50)),
            "{0:.2f}".format(getPercentile(iter, .95)),
            "{0:.2f}".format(max(iter)))

def getMean(iter):
    return sum(iter) / len(iter)

def getPercentile(iter, percentile):
    sort = sorted(iter)
    length = len(iter) - 1
    index = int(round(percentile * length))
    return sort[index]


def gatherWebResponseData(iter):
    return {
        "mean": getMean(iter),
        "min": min(iter),
        "max": max(iter),
        "fifth_percentile": getPercentile(iter, .05),
        "nintey_fifth_percentile": getPercentile(iter, .95)
    }