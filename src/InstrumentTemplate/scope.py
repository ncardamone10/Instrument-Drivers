'''
set channel (vertical)
    - scale {min, max} [V/div]
    - offset {min, max} [V]
    - probe attenuation {0.001X ... 50000X}
    - coupling {AC, DC, GND}
    - unit {W, A, V, U}
    - BW limit {ON, OFF}
    - invert {ON, OFF}
    - ch-ch skew {min, max} [s]
    - label {string}
    - bias {min, max} [V]
    - display {ON, OFF}
    - fine {ON, OFF}
# # Scale properties
        # self._scale = None
        # self._scale_query = f":CHAN{self.channel_number}:SCAL?"
        # self._scale_command = f":CHAN{self.channel_number}:SCAL "
        # self._scale_min = 0.001
        # self._scale_max = 10

        # # Offset properties
        # self._offset = None
        # self._offset_query = f":CHAN{self.channel_number}:OFFS?"
        # self._offset_command = f":CHAN{self.channel_number}:OFFS "
        # self._offset_min = -10
        # self._offset_max = 10

        # # Coupling properties
        # self._coupling = None
        # self._coupling_query = f":CHAN{self.channel_number}:COUP?"
        # self._coupling_command = f":CHAN{self.channel_number}:COUP "

        # # Bandwidth limit properties
        # self._bandwidth_limit = None
        # self._bandwidth_limit_query = f":CHAN{self.channel_number}:BAND?"
        # self._bandwidth_limit_command = f":CHAN{self.channel_number}:BAND "

        # # Invert properties
        # self._invert = None
        # self._invert_query = f":CHAN{self.channel_number}:INV?"
        # self._invert_command = f":CHAN{self.channel_number}:INV "

        # # Display properties
        # self._display = None
        # self._display_query = f":CHAN{self.channel_number}:DISP?"
        # self._display_command = f":CHAN{self.channel_number}:DISP "

        # # Fine adjustment properties
        # self._fine = None
        # self._fine_query = f":CHAN{self.channel_number}:FINE?"
        # self._fine_command = f":CHAN{self.channel_number}:FINE "

        #         # Probe attenuation properties
        # self._probe_attenuation = None
        # self._probe_attenuation_command = f":CHAN{self.channel_number}:PROB "
        # self._probe_attenuation_query = f":CHAN{self.channel_number}:PROB?"
        # self._probe_attenuation_values = ["0.001X", "0.002X", "0.005X", "0.01X", "0.02X", "0.05X", 
        #                                   "0.1X", "0.2X", "0.5X", "1X", "2X", "5X", "10X", "20X", "50X", 
        #                                   "100X", "200X", "500X", "1000X", "2000X", "5000X", "10000X", "20000X", "50000X"]
 
        # # Unit properties
        # self._unit = None
        # self._unit_command = f":CHAN{self.channel_number}:UNIT "
        # self._unit_query = f":CHAN{self.channel_number}:UNIT?"
        

        # # Channel-to-channel skew properties
        # self._ch_ch_skew = None
        # self._ch_ch_skew_command = f":CHAN{self.channel_number}:SKEW "
        # self._ch_ch_skew_query = f":CHAN{self.channel_number}:SKEW?"
        # self._ch_ch_skew_min = -10
        # self._ch_ch_skew_max = 10

        # # Label properties
        # self._label = None
        # self._label_command = f":CHAN{self.channel_number}:LAB "
        # self._label_query = f":CHAN{self.channel_number}:LAB?"

        # # Bias properties
        # self._bias = None
        # self._bias_command = f":CHAN{self.channel_number}:BIAS "
        # self._bias_query = f":CHAN{self.channel_number}:BIAS?"
        # self._bias_min = -10
        # self._bias_max = 10

set acquisition (settings)
    - acquisition {Normal, Average, Peak, UltraAcquire}
    In Normal Mode:
        - mem depth {AUTO, 1K, 10K, 100K, 1M, 10M}
    In Average Mode:
        - mem depth {AUTO, 1K, 10K, 100K, 1M, 10M}
        - averages {min, max}
    In Peak Mode:
        - mem depth {AUTO, 1K, 10K, 100K, 1M, 10M}
    In UltraAcquire Mode:
        - mem depth {AUTO, 1K, 10K, 100K, 1M, 10M}
        - display frame {min, max}
        - or timeout {min, max} [s]
        - display mode {Adjacent, Overlay, Waterfall, perspective, mosaic}

set timebase (horizontal)
    - roll {Auto, OFF}
    - expand {Center, Left, Right, Trigger, User}
    - scale {min, max} [s/div]
    - position {min, max} [s]
    - vernier {OFF, ON}
    - zoom {OFF, ON} 

set trigger
    - type {Edge, Pulse, Video, Slope, Pattern, Duration, Timeout, Runt, Over, Delay, Setup/Hold, NthEdge, RS232, I2C, SPI, CAN, LIN}
    - force (this is an action)
    - sweep {Auto, Normal, Single}
    - hold off {min, max} [s]
    - noise reject {OFF, ON}
    In Edge Trigger Mode
        - slope (Rising, Falling, Either)
        - source {CH1, CH2, CH3, CH4}
        - coupling {DC, AC, LFR, HFR}
        - level {min, max} [V]
'''


from .instrument import Instrument

class Channel:
    def __init__(self, config, send_command_callback, query_command_callback):
        self.channel_number = config['channel_number']
        #print(f"Initializing Channel {self.channel_number}")
        self.send_command = send_command_callback
        self.query_command = query_command_callback
        
        # Initialize all properties from the config
        self._scale_query = config['scale']['query']
        self._scale_command = config['scale']['command']
        self._scale_min = config['scale']['min']
        self._scale_max = config['scale']['max']
        
        self._offset_query = config['offset']['query']
        self._offset_command = config['offset']['command']
        self._offset_min = config['offset']['min']
        self._offset_max = config['offset']['max']
        
        self._coupling_query = config['coupling']['query']
        self._coupling_command = config['coupling']['command']
        
        self._bandwidth_limit_query = config['bandwidth_limit']['query']
        self._bandwidth_limit_command = config['bandwidth_limit']['command']
        
        self._invert_query = config['invert']['query']
        self._invert_command = config['invert']['command']
        
        self._display_query = config['display']['query']
        self._display_command = config['display']['command']
        
        self._fine_query = config['fine']['query']
        self._fine_command = config['fine']['command']

        self._probe_attenuation_query = config['probe_attenuation']['query']
        self._probe_attenuation_command = config['probe_attenuation']['command']

        self._unit_query = config['unit']['query']
        self._unit_command = config['unit']['command']

        self._ch_ch_skew_query = config['ch_ch_skew']['query']
        self._ch_ch_skew_command = config['ch_ch_skew']['command']
        self._ch_ch_skew_min = config['ch_ch_skew']['min']
        self._ch_ch_skew_max = config['ch_ch_skew']['max']

        self._label_query = config['label']['query']
        self._label_command = config['label']['command']
        self._label_show_query = config['label_show']['query']
        self._label_show_command = config['label_show']['command']

        self._bias_query = config['bias']['query']
        self._bias_command = config['bias']['command']
        self._bias_min = config['bias']['min']
        self._bias_max = config['bias']['max']

        

    # Scale property
    @property
    def scale(self):
        return self.query_command(self._scale_query)

    @scale.setter
    def scale(self, value):
        if self._scale_min <= value <= self._scale_max:
            self.send_command(self._scale_command + str(value))
            self._scale = self.query_command(self._scale_query)
            if self._scale != value:
                print(f"Warning: Scale value not set to {value} V/div")
                print(f"Actual value: {self._scale} V/div")
        else:
            raise ValueError("Scale value out of range")

    # Offset property
    @property
    def offset(self):
        return self.query_command(self._offset_query)

    @offset.setter
    def offset(self, value):
        if self._offset_min <= value <= self._offset_max:
            self.send_command(self._offset_command + str(value))
            self._offset = self.query_command(self._offset_query)
            if self._offset != value:
                print(f"Warning: Offset value not set to {value} V")
                print(f"Actual value: {self._offset} V")
        else:
            raise ValueError("Offset value out of range")

    # Coupling property
    @property
    def coupling(self):
        return self.query_command(self._coupling_query)

    @coupling.setter
    def coupling(self, value):
        if value in ["AC", "DC", "GND"]:
            self.send_command(self._coupling_command + value)
            self._coupling = self.query_command(self._coupling_query)
            if self._coupling != value:
                print(f"Warning: Coupling not set to {value}")
                print(f"Actual value: {self._coupling}")
        else:
            raise ValueError("Invalid coupling type")

    # Bandwidth Limit property
    @property
    def bandwidth_limit(self):
        return self.query_command(self._bandwidth_limit_query)

    @bandwidth_limit.setter
    def bandwidth_limit(self, state):
        if state in ["ON", "OFF"]:
            self.send_command(self._bandwidth_limit_command + state)
            self._bandwidth_limit = self.query_command(self._bandwidth_limit_query)
            if self._bandwidth_limit != state:
                print(f"Warning: Bandwidth limit not set to {state}")
                print(f"Actual value: {self._bandwidth_limit}")
        else:
            raise ValueError("Invalid bandwidth limit state")

    # Invert property
    @property
    def invert(self):
        return self.query_command(self._invert_query)

    @invert.setter
    def invert(self, state):
        if state in ["ON", "OFF"]:
            self.send_command(self._invert_command + state)
            self._invert = self.query_command(self._invert_query)
            if self._invert != state:
                print(f"Warning: Invert not set to {state}")
                print(f"Actual value: {self._invert}")
        else:
            raise ValueError("Invalid invert state")

    # Display property
    @property
    def display(self):
        return self.query_command(self._display_query)

    @display.setter
    def display(self, state):
        if state in ["ON", "OFF"]:
            self.send_command(self._display_command + state)
            self._display = self.query_command(self._display_query)
            if self._display != state:
                print(f"Warning: Display not set to {state}")
                print(f"Actual value: {self._display}")
        else:
            raise ValueError("Invalid display state")

    # Fine property
    @property
    def fine(self):
        return self.query_command(self._fine_query)

    @fine.setter
    def fine(self, state):
        if state in ["ON", "OFF"]:
            self.send_command(self._fine_command + state)
            self._fine = self.query_command(self._fine_query)
            if self._fine != state:
                print(f"Warning: Fine not set to {state}")
                print(f"Actual value: {self._fine}")
        else:
            raise ValueError("Invalid fine state")
    
    # Probe attenuation property
    @property
    def probe_attenuation(self):
        return self.query_command(self._probe_attenuation_query)

    @probe_attenuation.setter
    def probe_attenuation(self, value):
        if value in self._probe_attenuation_values:
            self.send_command(self._probe_attenuation_command + str(value))
            self._probe_attenuation = self.query_command(self._probe_attenuation_query)
            if self._probe_attenuation != value:
                print(f"Warning: Probe attenuation not set to {value}")
                print(f"Actual value: {self._probe_attenuation}")
        else:
            raise ValueError("Invalid probe attenuation value")

    # Unit property
    @property
    def unit(self):
        return self.query_command(self._unit_query)

    @unit.setter
    def unit(self, value):
        if value in ["W", "A", "V", "U"]:
            self.send_command(self._unit_command + value)
            self._unit = self.query_command(self._unit_query)
            if self._unit != value:
                print(f"Warning: Unit not set to {value}")
                print(f"Actual value: {self._unit}")
        else:
            raise ValueError("Invalid unit type")

    # Channel-to-channel skew property
    @property
    def ch_ch_skew(self):
        return self.query_command(self._ch_ch_skew_query)

    @ch_ch_skew.setter
    def ch_ch_skew(self, value):
        if self._ch_ch_skew_min <= value <= self._ch_ch_skew_max:
            self.send_command(self._ch_ch_skew_command + str(value))
            self._ch_ch_skew = self.query_command(self._ch_ch_skew_query)
            if self._ch_ch_skew != value:
                print(f"Warning: Channel-to-channel skew not set to {value} s")
                print(f"Actual value: {self._ch_ch_skew} s")
        else:
            raise ValueError("Channel-to-channel skew value out of range")

    # Label property
    @property
    def label(self):
        return self.query_command(self._label_query)

    @label.setter
    def label(self, value):
        if type(value) is str:
            self.send_command(self._label_command + value)
            self._label = self.query_command(self._label_query)
            if self._label != value:
                print(f"Warning: Label not set to {value}")
                print(f"Actual value: {self._label}")
        else:
            raise ValueError("Invalid label type")

    # Label Show property
    @property
    def label_show(self):
        return self.query_command(self._label_show_query)
    
    @label_show.setter
    def label_show(self, value):
        if value in ["ON", "OFF"]:
            self.send_command(self._label_show_command + value)
            self._label_show = self.query_command(self._label_show_query)
            if self._label_show != value:
                print(f"Warning: Label show not set to {value}")
                print(f"Actual value: {self._label_show}")
        else:
            raise ValueError("Invalid label show state")

    # Bias property
    @property
    def bias(self):
        return self.query_command(self._bias_query)

    @bias.setter
    def bias(self, value):
        if self._bias_min <= value <= self._bias_max:
            self.send_command(self._bias_command + str(value))
            self._bias = self.query_command(self._bias_query)
            if self._bias != value:
                print(f"Warning: Bias not set to {value} V")
                print(f"Actual value: {self._bias} V")
        else:
            raise ValueError("Bias value out of range")

class Timebase:
    def __init__(self, config, send_command_callback, query_command_callback):
        self.send_command = send_command_callback
        self.query_command = query_command_callback

        # Initialize all properties from the config
        self._scale_query = config['scale']['query']
        self._scale_command = config['scale']['command']
        self._scale_min = config['scale']['min']
        self._scale_max = config['scale']['max']

        self._roll_query = config['roll']['query']
        self._roll_command = config['roll']['command']
        
        self._expand_query = config['expand']['query']
        self._expand_command = config['expand']['command']

        self._position_query = config['position']['query']
        self._position_command = config['position']['command']
        self._position_min = config['position']['min']
        self._position_max = config['position']['max']

        self._vernier_query = config['vernier']['query']
        self._vernier_command = config['vernier']['command']

        self._zoom_query = config['zoom']['query']
        self._zoom_command = config['zoom']['command']

    # Roll property
    @property
    def roll(self):
        return self.query_command(self._roll_query)
    
    @roll.setter
    def roll(self, value):
        if value in ["Auto", "OFF"]:
            self.send_command(self._roll_command + value)
            self._roll = self.query_command(self._roll_query)
            if self._roll != value:
                print(f"Warning: Roll not set to {value}")
                print(f"Actual value: {self._roll}")
        else:
            raise ValueError("Invalid roll state")

    # Expand property
    @property
    def expand(self):
        return self.query_command(self._expand_query)
        
    @expand.setter
    def expand(self, value):
        if value in ["Center", "Left", "Right", "Trigger", "User"]:
            self.send_command(self._expand_command + value)
            self._expand = self.query_command(self._expand_query)
            if self._expand != value:
                print(f"Warning: Expand not set to {value}")
                print(f"Actual value: {self._expand}")
        else:
            raise ValueError("Invalid expand state")

    # Scale property
    @property
    def scale(self):
        return self.query_command(self._scale_query)

    @scale.setter
    def scale(self, value):
        if self._scale_min <= value <= self._scale_max:
            self.send_command(self._scale_command + str(value))
            self._scale = self.query_command(self._scale_query)
            if self._scale != value:
                print(f"Warning: Scale value not set to {value} s/div")
                print(f"Actual value: {self._scale} s/div")
        else:
            raise ValueError("Scale value out of range")

    # Position property
    @property
    def position(self):
        return self.query_command(self._position_query)

    @position.setter
    def position(self, value):
        if self._position_min <= value <= self._position_max:
            self.send_command(self._position_command + str(value))
            self._position = self.query_command(self._position_query)
            if self._position != value:
                print(f"Warning: Position not set to {value} s")
                print(f"Actual value: {self._position} s")
        else:
            raise ValueError("Position value out of range")

    # Vernier property
    @property
    def vernier(self):
        return self.query_command(self._vernier_query)

    @vernier.setter
    def vernier(self, value):
        if value in ["OFF", "ON"]:
            self.send_command(self._vernier_command + value)
            self._vernier = self.query_command(self._vernier_query)
            if self._vernier != value:
                print(f"Warning: Vernier not set to {value}")
                print(f"Actual value: {self._vernier}")
        else:
            raise ValueError("Invalid vernier state")

    # Zoom property
    @property
    def zoom(self):
        return self.query_command(self._zoom_query)
    
    @zoom.setter
    def zoom(self, value):
        if value in ["OFF", "ON"]:
            self.send_command(self._zoom_command + value)
            self._zoom = self.query_command(self._zoom_query)
            if self._zoom != value:
                print(f"Warning: Zoom not set to {value}")
                print(f"Actual value: {self._zoom}")
        else:
            raise ValueError("Invalid zoom state")




class Oscilloscope(Instrument):
    @staticmethod
    def find_instrument_by_model(model_id):
        """Use the Instrument class method to find by model."""
        return Instrument.find_instrument_by_model(model_id)
    
    def create_channel_config(self, channel_number):
        return {
            'channel_number': channel_number,
            'scale': {
                'query': f":CHAN{channel_number}:SCAL?",
                'command': f":CHAN{channel_number}:SCAL ",
                'min': 0.001,
                'max': 10
            },
            'offset': {
                'query': f":CHAN{channel_number}:OFFS?",
                'command': f":CHAN{channel_number}:OFFS ",
                'min': -10,
                'max': 10
            },
            'coupling': {
                'query': f":CHAN{channel_number}:COUP?",
                'command': f":CHAN{channel_number}:COUP "
            },
            'bandwidth_limit': {
                'query': f":CHAN{channel_number}:BAND?",
                'command': f":CHAN{channel_number}:BAND "
            },
            'invert': {
                'query': f":CHAN{channel_number}:INV?",
                'command': f":CHAN{channel_number}:INV "
            },
            'display': {
                'query': f":CHAN{channel_number}:DISP?",
                'command': f":CHAN{channel_number}:DISP "
            },
            'fine': {
                'query': f":CHAN{channel_number}:FINE?",
                'command': f":CHAN{channel_number}:FINE "
            },
            'probe_attenuation': {
                'query': f":CHAN{channel_number}:PROB?",
                'command': f":CHAN{channel_number}:PROB ",
                'values': ["0.001X", "0.002X", "0.005X", "0.01X", "0.02X", "0.05X",
                        "0.1X", "0.2X", "0.5X", "1X", "2X", "5X", "10X", "20X", "50X",
                        "100X", "200X", "500X", "1000X", "2000X", "5000X", "10000X", "20000X", "50000X"]
            },
            'unit': {
                'query': f":CHAN{channel_number}:UNIT?",
                'command': f":CHAN{channel_number}:UNIT "
            },
            'ch_ch_skew': {
                'query': f":CHAN{channel_number}:SKEW?",
                'command': f":CHAN{channel_number}:SKEW ",
                'min': -10,
                'max': 10
            },
            'label': {
                'query': f":CHAN{channel_number}:LABEL:CONTENT?",
                'command': f":CHAN{channel_number}:LABEL:CONTENT "
            },
            'label_show' : {
                'query': f":CHAN{channel_number}:LAB:SHOW?",
                'command': f":CHAN{channel_number}:LAB:SHOW "
            },
            'bias': {
                'query': f":CHAN{channel_number}:BIAS?",
                'command': f":CHAN{channel_number}:BIAS ",
                'min': -10,
                'max': 10
            }
        }
    
    def create_timebase_config(self):
        return {
            'roll': {
                'command': 'TIMEBASE:ROLL ',
                'query': 'TIMEBASE:ROLL?',
                'valid': ['Auto', 'OFF']
            },
            'expand': {
                'command': 'TIMEBASE:EXPAND ',
                'query': 'TIMEBASE:EXPAND?',
                'valid': ['Center', 'Left', 'Right', 'Trigger', 'User']
            },
            'scale': {
                'command': 'TIMEBASE:SCALE ',
                'query': 'TIMEBASE:SCALE?',
                'min': 0.00001,  # Example: 10 ns/div
                'max': 1         # Example: 1 s/div
            },
            'position': {
                'command': 'TIMEBASE:POSITION ',
                'query': 'TIMEBASE:POSITION?',
                'min': -50,      # Example: -50 s
                'max': 50        # Example: 50 s
            },
            'vernier': {
                'command': 'TIMEBASE:VERNIER ',
                'query': 'TIMEBASE:VERNIER?',
                'valid': ['OFF', 'ON']
            },
            'zoom': {
                'command': 'TIMEBASE:ZOOM ',
                'query': 'TIMEBASE:ZOOM?',
                'valid': ['OFF', 'ON']
            }
        }


    def __init__(self, resource_address, number_of_channels=4):
        super().__init__(resource_address)
        self.channel_configs = [self.create_channel_config(i + 1) for i in range(number_of_channels)]
        self.channel = [None] + [Channel(config, self.send_command, self.send_command) for config in self.channel_configs]
        self.timebase_config = self.create_timebase_config()
        self.timebase = Timebase(self.timebase_config, self.send_command, self.send_command)


    # def set_timebase(self, time_per_div):
    #     """Set the timebase of the oscilloscope to time_per_div seconds/div."""
    #     command = f":TIMEBASE:SCALE {time_per_div}"
    #     self.send_command(command)
    #     print(f"Timebase set to {time_per_div} s/div")

    # def set_channel(self, channel, scale, offset=0):
    #     """Configure a specific channel on the oscilloscope."""
    #     self.send_command(f":CHANNEL{channel}:SCALE {scale}")
    #     self.send_command(f":CHANNEL{channel}:OFFSET {offset}")
    #     print(f"Channel {channel} set with scale {scale} V/div and offset {offset} V")

    # def get_waveform(self, channel):
    #     """Acquire the current waveform from a specified channel."""
    #     self.send_command(f":WAVEFORM:SOURCE CH{channel}")
    #     self.send_command(":WAVEFORM:FORMAT ASCII")
    #     data = self.send_command(":WAVEFORM:DATA?")
    #     print(f"Waveform data from channel {channel} acquired")
    #     return data

    # def measure_voltage_peak_to_peak(self, channel):
    #     """Measure and return the peak-to-peak voltage of a specified channel."""
    #     voltage = self.send_command(f":MEASURE:VPP? CH{channel}")
    #     print(f"Peak-to-peak voltage for channel {channel} is {voltage} V")
    #     return voltage

