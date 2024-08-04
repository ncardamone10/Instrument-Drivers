import pyvisa

class Instrument:
    @staticmethod
    def find_instrument_by_model(model_id):
        """Scan for instruments by pinging IP addresses within a specified range and return the resource address of the first matching model."""
        rm = pyvisa.ResourceManager()
        base_ip = "100.100.1."
        for i in range(1, 256):  # Iterate over the range 1 to 255
            ip_address = f"{base_ip}{i}"
            resource_string = f"TCPIP::{ip_address}::INSTR"
            try:
                inst = rm.open_resource(resource_string)
                idn = inst.query("*IDN?").strip()
                #print(f"Attempting connection to: {resource_string} - Found instrument: {idn}")
                if model_id in idn:
                    inst.close()
                    print(f"Found {model_id} at {resource_string}")
                    return resource_string
                inst.close()
            except pyvisa.VisaIOError as e:
                #print(f"No response from {resource_string}: {e}")
                continue
        print(f"No instrument found for model ID {model_id} within IP range 100.100.1.x")
        return None

    def __init__(self, resource_address):
        self.resource_address = resource_address
        self.rm = pyvisa.ResourceManager()
        self.instrument = None

    def connect(self):
        """Establish a connection to the instrument."""
        try:
            self.instrument = self.rm.open_resource(self.resource_address)
            self.instrument.timeout = 50  # Set timeout to 5000 ms
            print(f"Connected to {self.resource_address}")
        except pyvisa.VisaIOError as e:
            print(f"Failed to connect to {self.resource_address}: {e}")

    def disconnect(self):
        """Close the connection to the instrument."""
        if self.instrument:
            self.instrument.close()
            print(f"Disconnected from {self.resource_address}")

    def send_command(self, command):
        print(f"Trying to send command: {command}")
        """Send a command to the instrument and return its response."""
        if self.instrument is None:
            print("Not connected to any instrument.")
            return None
        try:
            response = self.instrument.query(command)
            print(f"Command: {command} - Response: {response}")
            return response
        except pyvisa.VisaIOError as e:
            print(f"Error sending command: {e} in instrument.py")
            return None

    def __del__(self):
        """Ensure the connection is closed if the object is deleted."""
        try:
            if self.instrument:
                self.disconnect()
        except Exception as e:
            print(f"Error during cleanup: {e}")
