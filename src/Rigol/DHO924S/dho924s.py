#python -m src.Rigol.DHO924S.dho924s
from ...InstrumentTemplate.scope import Oscilloscope

class DHO924S(Oscilloscope):
    def __init__(self, number_of_channels=4):
        resource_address = Oscilloscope.find_instrument_by_model("DHO924S")
        if resource_address:
            super().__init__(resource_address, number_of_channels)
        else:
            raise ValueError("Instrument not found on the network")
        print("Initializing DHO924S Oscilloscope")



#     def set_timebase(self, time_per_div):
#         """Override to set the timebase specifically for DHO924S."""
#         command = f":TIMebase:SCALe {time_per_div}"
#         self.send_command(command)
#         print(f"DHO924S: Timebase set to {time_per_div} s/div")

#     def set_channel(self, channel, scale, coupling='DC', bandwidth_limit=False):
#         """Customize channel settings specific to DHO924S."""
#         super().set_channel(channel, scale)
#         self.send_command(f":CHANNEL{channel}:COUPLING {coupling}")
#         bw_limit_cmd = 'ON' if bandwidth_limit else 'OFF'
#         self.send_command(f":CHANNEL{channel}:BANDWIDTH {bw_limit_cmd}")
#         print(f"Channel {channel} configured with {coupling} coupling and bandwidth limit {bw_limit_cmd}")

#     def auto_scale(self):
#         """Add an auto-scale method specific for DHO924S."""
#         self.send_command(":AUTOSCALE")
#         print("Auto-scale executed")

# # Example of using the DHO924S class
if __name__ == "__main__":
    try:
        scope = DHO924S()  # Assume DHO924S is a part of the model string returned by *IDN?
        scope.connect()
        scope.channel[1].label = "Test 5"
        scope.channel[1].offset = -2
        # scope.set_timebase(0.01)
        # scope.set_channel(1, 0.5, 'AC', True)
        # scope.auto_scale()
        scope.disconnect()
    except ValueError as e:
        print(e)
