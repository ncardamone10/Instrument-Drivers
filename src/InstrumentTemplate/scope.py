from .instrument import Instrument

class Oscilloscope(Instrument):
    @staticmethod
    def find_instrument_by_model(model_id):
        """Use the Instrument class method to find by model."""
        return Instrument.find_instrument_by_model(model_id)
    
    def __init__(self, resource_address):
        super().__init__(resource_address)

    def set_timebase(self, time_per_div):
        """Set the timebase of the oscilloscope to time_per_div seconds/div."""
        command = f":TIMEBASE:SCALE {time_per_div}"
        self.send_command(command)
        print(f"Timebase set to {time_per_div} s/div")

    def set_channel(self, channel, scale, offset=0):
        """Configure a specific channel on the oscilloscope."""
        self.send_command(f":CHANNEL{channel}:SCALE {scale}")
        self.send_command(f":CHANNEL{channel}:OFFSET {offset}")
        print(f"Channel {channel} set with scale {scale} V/div and offset {offset} V")

    def get_waveform(self, channel):
        """Acquire the current waveform from a specified channel."""
        self.send_command(f":WAVEFORM:SOURCE CH{channel}")
        self.send_command(":WAVEFORM:FORMAT ASCII")
        data = self.send_command(":WAVEFORM:DATA?")
        print(f"Waveform data from channel {channel} acquired")
        return data

    def measure_voltage_peak_to_peak(self, channel):
        """Measure and return the peak-to-peak voltage of a specified channel."""
        voltage = self.send_command(f":MEASURE:VPP? CH{channel}")
        print(f"Peak-to-peak voltage for channel {channel} is {voltage} V")
        return voltage

