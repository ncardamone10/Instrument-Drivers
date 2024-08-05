from .instrument import Instrument


class Autoset:
    pass
class Acquire:
    pass
class Bus:
    pass
class Bodeplot:
    pass
class Channel:
    pass
class Counter:
    pass
class Cursor:
    pass
class Display:
    pass
class Dvm:
    pass
class Histogram:
    pass
class LogicAnalyzer:
    pass
class Mask:
    pass
class Math:
    pass
class Measure:
    pass
class Record:
    pass
class Reference:
    pass
class Save:
    pass
class Search:
    pass
class Navigate:
    pass
class FunctionGen:
    pass
class Timebase:
    pass
class Trigger:
    pass
class Waveform:
    pass

class Oscilloscope(Instrument):
    @staticmethod
    def find_instrument_by_model(model_id):
        """Use the Instrument class method to find by model."""
        return Instrument.find_instrument_by_model(model_id)


    def __init__(self, resource_address, number_of_channels=4, number_of_math=4):
        super().__init__(resource_address)
        self.autoset = Autoset()
        self.acquire = Acquire()
        self.bus = Bus()
        self.bodeplot = Bodeplot()
        self.channel = [None] + [Channel() for i in range(number_of_channels)]
        self.counter = Counter()
        self.cursor = Cursor()
        self.display = Display()
        self.dvm = Dvm()
        self.histogram = Histogram()
        self.logic_analyzer = LogicAnalyzer()
        self.mask = Mask()
        self.math = [None] + [Math() for i in range(number_of_math)]
        self.measure = Measure()
        self.record = Record()
        self.reference = Reference()
        self.save = Save()
        self.search = Search()
        self.navigate = Navigate()
        self.function_gen = FunctionGen()
        self.timebase = Timebase()

