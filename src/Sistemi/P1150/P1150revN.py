# -*- coding: utf-8 -*-
"""
P1150revN - Easy-to-use dataclass wrapper around the P1150 instrument
- Auto-detects and connects (handles bootloader FW load + calibration)
- Exposes enable/disable output (probe connect)
- Set/get output voltage
- Start/wait/stop acquisitions
- Average current helper
- Console prints plus logging

Sphinx documentation
--------------------
This module provides Sphinx-friendly docstrings on public classes and methods.
You can include it in your docs using autodoc::

    .. automodule:: P1150revN
       :members:
       :undoc-members:
       :show-inheritance:

Quickstart
----------

.. code-block:: ipython

    from P1150revN import P1150

    # Connect (auto-detect port) and enable output
    psu = P1150(auto_enable_output=False)

    # Set 3.3V
    psu.set_vout(3300)

    # Take a single-shot capture and compute mean current
    avg_ma = psu.average_current()
    print('Average current (mA):', avg_ma)

    # Always close when finished
    psu.close()
"""
from __future__ import annotations

import os
import time
import struct
import hashlib
from dataclasses import dataclass, field
from threading import Lock, Event
from collections import deque
from typing import Optional, Dict, Any, Iterable
import sys

import serial
import serial.tools.list_ports
import cbor2

import uclog

# ------------------------------
# Load API constants from TOML
# ------------------------------
try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    tomllib = None  # fallback disabled to avoid import errors when not needed

_API: Dict[str, Any] = {}
_API_PATH = os.path.join(os.path.dirname(__file__), "p1150_api.toml")
if tomllib and os.path.exists(_API_PATH):
    with open(_API_PATH, "rb") as f:
        _API = tomllib.load(f)
else:
    raise RuntimeError("tomllib not available, cannot load p1150_api.toml")

# Derived maps
TIMEBASE_MAP = _API.get("timebases", {
   # "TBASE_SPAN_100MS": 0.100
})
# Command map (must be defined in TOML)
COMMANDS: Dict[str, str] = _API.get("commands", {})

def CMD(name: str) -> str:
    c = COMMANDS.get(name)
    if not c:
        raise KeyError(f"API command '{name}' not defined in p1150_api.toml")
    return c

ACQUIRE_MODE_LIST = _API.get("acquire_modes", {}).get("list", [
    "ACQUIRE_MODE_RUN", "ACQUIRE_MODE_SINGLE", "ACQUIRE_MODE_LOGGER"
])
ACQUIRE_MODE_RUN = ACQUIRE_MODE_LIST[0] if len(ACQUIRE_MODE_LIST) > 0 else 'DEFAULT'  #"ACQUIRE_MODE_RUN"
ACQUIRE_MODE_SINGLE = ACQUIRE_MODE_LIST[1] if len(ACQUIRE_MODE_LIST) > 1 else 'DEFAULT'  #"ACQUIRE_MODE_SINGLE"
ACQUIRE_MODE_LOGGER = ACQUIRE_MODE_LIST[2] if len(ACQUIRE_MODE_LIST) > 2 else 'DEFAULT'  #"ACQUIRE_MODE_LOGGER"

TRIG_SRC_LIST = _API.get("trigger_sources", {}).get("list", [
    # "TRIG_SRC_NONE","TRIG_SRC_CUR","TRIG_SRC_D0","TRIG_SRC_D1","TRIG_SRC_A0A"
])
# TRIG_SRC_NONE = TRIG_SRC_LIST[0] if TRIG_SRC_LIST else "TRIG_SRC_NONE"
# TRIG_SRC_CUR  = "TRIG_SRC_CUR"
# TRIG_SRC_D0   = "TRIG_SRC_D0"
# TRIG_SRC_D1   = "TRIG_SRC_D1"
# TRIG_SRC_A0A  = "TRIG_SRC_A0A"

TRIG_POS_LIST = _API.get("trigger_positions", {}).get("list", [
    # "TRIG_POS_CENTER","TRIG_POS_LEFT","TRIG_POS_RIGHT"
])
# TRIG_POS_CENTER = "TRIG_POS_CENTER"
# TRIG_POS_LEFT   = "TRIG_POS_LEFT"
# TRIG_POS_RIGHT  = "TRIG_POS_RIGHT"

TRIG_SLOPE_LIST = _API.get("trigger_slopes", {}).get("list", [
    # "TRIG_SLOPE_RISE","TRIG_SLOPE_FALL","TRIG_SLOPE_EITHER"
])
# TRIG_SLOPE_RISE = "TRIG_SLOPE_RISE"
# TRIG_SLOPE_FALL = "TRIG_SLOPE_FALL"
# TRIG_SLOPE_EITHER = "TRIG_SLOPE_EITHER"

# ------------------------------
# Minimal logger stub
# ------------------------------
class StubLogger:
    """Minimal logger stub used when no logger is supplied.

    Methods in this class are no-ops and mirror the standard logging API so that
    the driver can call ``info``, ``error``, etc. without checking for a logger.
    """
    def info(self, *a, **k): print(*a)
    def error(self, *a, **k): print(*a)
    def debug(self, *a, **k): print(*a)
    def warning(self, *a, **k): print(*a)

# ------------------------------
# Transport/command layer (port 0/1/2/3 via uclog)
# ------------------------------
class UCLogger:
    """Transport and command multiplexer over ucLog.

    This class wraps the serial transport and ucLog mux to provide a convenient
    API for sending commands (port 0) and receiving logs, async messages, plots,
    and ADC stream frames (ports 1..3).

    Parameters
    ----------
    port : str
        Serial port (e.g., ``COM3`` or ``/dev/ttyACM0``).
    logger : object
        Logger with ``info``, ``debug``, ``warning``, ``error`` methods.
    app : str
        Target app identifier ("a43" default). Determines which .logdata to load.
    verbose : bool
        Enable extra prints.

    Examples
    --------
    Basic usage for sending a ping command:

    .. code-block:: ipython

        uc = UCLogger('COM3')
        ok, rsp = uc.send_cmd({'f': 'cmd_ping'})
        uc.close()
    """
    DEFAULT_CMD_RETRIES = 60
    def __init__(self, port: str, logger=StubLogger(), app: str = "a43", verbose: bool=False):
        """Initialize and open transport, attach decoders, and start worker threads."""
        self._port = port
        self.logger = logger
        self._verbose = verbose
        self._lock_responses = Lock()
        self._cmd_responses: Dict[str, list] = {}
        self._result_event = Event()
        self._cb_uclog_async = None
        self._cb_uclog_adc = None
        self._ucLogServer = None
        self._connect_uc(app)

    def _connect_uc(self, app: str):
        """Create the LogClientServer with appropriate decoders.

        Parameters
        ----------
        app : str
            App name that selects the .logdata file to decode target logs.
        """
        try:
            base_dir = os.path.dirname(__file__)
            if app == "a43":
                elf_file = os.path.join(base_dir, "assets", "a43_app.logdata")
            elif app == "a57":
                elf_file = os.path.join(base_dir, "assets", "a57_app.logdata")
            else:
                raise ValueError("app must be a43 or a57")
            bl_elf_file = os.path.join(base_dir, "assets", "a51_bl.logdata")
            decoders = uclog.decoders([elf_file, bl_elf_file])
            self._ucLogServer = uclog.LogClientServer(self._port, decoders, {
                'log': self._uclog_log, 0: self._uclog_cmdres, 1: self._uclog_async, 2: self._uclog_plot, 3: self._uclog_adc
            })
            self.logger.info(f"Opened {self._port} (app {app})")
        except Exception as e:
            self.logger.error(f"Failed to connect {self._port}: {e}")
            self._ucLogServer = None

    def is_connected(self) -> bool:
        """Return True if the transport is connected and running."""
        return self._ucLogServer is not None

    def _uclog_plot(self, item):
        """Internal callback for plot stream (unused in this driver)."""
        pass

    def _uclog_log(self, item):
        """Internal callback for decoded target logs.

        Notes
        -----
        The tuple is ``(count, ts, level, file, line, message)`` and is already
        decoded to human-readable strings by the logdata decoder.
        """
        try:
            _, _, lvl, file, line, msg = item
            if lvl == "ERROR": self.logger.error(f"== {lvl:5}:{file:30}:{line:4}: {msg}")
            else: self.logger.info(f"== {lvl:5}:{file:30}:{line:4}: {msg}")
        except Exception:
            self.logger.info(str(item))

    def _uclog_async(self, _item):
        """Internal callback for asynchronous messages from the target.

        The payload is CBOR encoded JSON-like dictionary.
        """
        try:
            item = cbor2.loads(_item)
            if self._cb_uclog_async: self._cb_uclog_async(item)
        except Exception:
            pass

    def _uclog_adc(self, _item):
        """Internal callback for ADC stream (port 3).

        Decodes packed binary samples to lists and forwards a normalized CBOR
        frame to the high-level driver callback.
        """
        try:
            # Decode CBOR frame from device
            item = cbor2.loads(_item)

            # Current (source) in mA from packed float32 microamps
            if isinstance(item.get("i"), (bytes, bytearray)):
                fcnt = len(item["i"]) // 4
                item["i"] = [v / 1_000_000.0 for v in struct.unpack('<' + 'f'*fcnt, item["i"])]

            # Current (sink) in mA
            if isinstance(item.get("isnk"), (bytes, bytearray)):
                fcnt = len(item["isnk"]) // 4
                item["isnk"] = [v / 1_000_000.0 for v in struct.unpack('<' + 'f'*fcnt, item["isnk"])]

            # Aux A0 in mV
            if isinstance(item.get("a0"), (bytes, bytearray)):
                icnt = len(item["a0"]) // 2
                item["a0"] = list(struct.unpack('<' + 'H'*icnt, item["a0"]))

            # Digital combined -> logical d0/d1 (0/1)
            if isinstance(item.get("d01"), (bytes, bytearray)):
                dbytes = struct.unpack('<' + 'B'*len(item["d01"]), item["d01"])
            elif isinstance(item.get("d01"), list):
                dbytes = item["d01"]
            else:
                dbytes = None
            if dbytes is not None:
                item["d0"] = [1 if (b & 0x01) else 0 for b in dbytes]
                item["d1"] = [1 if (b & 0x02) else 0 for b in dbytes]

            # Forward normalized frame as CBOR bytes to keep callback signature
            if self._cb_uclog_adc:
                self._cb_uclog_adc(cbor2.dumps(item))
        except Exception:
            # Fallback: forward raw
            if self._cb_uclog_adc:
                self._cb_uclog_adc(_item)

    def _uclog_cmdres(self, _item):
        """Internal callback for command responses (port 0).

        Collects responses keyed by ``f`` and notifies waiting threads.
        """
        try:
            item = cbor2.loads(_item)
            if 'f' not in item:
                return
            with self._lock_responses:
                f = item['f']
                if f in self._cmd_responses:
                    self._cmd_responses[f].append(item)
                    self._result_event.set()
                else:
                    self._cmd_responses[f] = [item]
        except Exception:
            pass

    def send_cmd(self, payload: dict):
        """Send a command to the target and wait for a response.

        Parameters
        ----------
        payload : dict
            Command payload with ``'f'`` field set to the function name and any arguments.

        Returns
        -------
        tuple[bool, list|None]
            ``(success, responses)`` where responses is the list of response dicts, or ``None`` on error.

        Examples
        --------
        .. code-block:: ipython

            ok, rsp = uc.send_cmd({'f': 'cmd_ping'})
        """
        if not self._ucLogServer:
            return False, None
        f = payload.get('f', '?')
        with self._lock_responses:
            self._cmd_responses[f] = []
            self._result_event.clear()
            try:
                self._ucLogServer[0](cbor2.dumps(payload))
            except Exception as e:
                self.logger.error(e)
                return False, None
        retries = self.DEFAULT_CMD_RETRIES
        while retries > 0:
            retries -= 1
            got = self._result_event.wait(timeout=0.15)
            if not got:
                continue
            with self._lock_responses:
                bucket = self._cmd_responses.get(f, [])
                if bucket:
                    success = bucket[-1].get('s', False)
                    resp = self._cmd_responses.pop(f)
                    return success, resp
        self.logger.error(f"Timeout waiting for {f}")
        return False, None

    def close(self):
        """Shutdown transport threads and release the serial port.

        Examples
        --------
        .. code-block:: ipython

            uc.close()
        """
        if self._ucLogServer:
            try:
                self._ucLogServer.shutdown()
            except Exception:
                pass
            self._ucLogServer = None
            self.logger.info("closed")

# ------------------------------
# High-level instrument dataclass
# ------------------------------
@dataclass
class P1150:
    """High-level P1150 instrument API.

    This class provides a minimal, ipythonic interface to the P1150 device for
    common tasks: connecting, setting output voltage, starting acquisitions,
    reading data, and convenience helpers.

    Parameters
    ----------
    port : str | None
        Serial port. If ``None``, the driver auto-detects by pinging available ports.
    app : str
        Target application ("a43" default).
    verbose : bool
        Enable extra prints.
    logger : object
        Logger with ``info``, ``debug``, ``warning``, ``error``.
    auto_enable_output : bool
        If True, enable the probe output after connect.

    Examples
    --------
    Connect, set voltage, capture, and close:

    .. code-block:: ipython

        from P1150revN import P1150
        psu = P1150(auto_enable_output=False)
        psu.set_vout(5000)
        psu.set_timebase('TBASE_SPAN_100MS')
        psu.acquisition_start('ACQUIRE_MODE_SINGLE')
        data = psu.wait_for_acquisition(2.0)
        print(len(data['i']))
        psu.close()
    """
    port: Optional[str] = None
    app: str = "a43"
    verbose: bool = False
    logger: object = field(default_factory=StubLogger)
    auto_enable_output: bool = False

    # runtime
    _uc: UCLogger = field(init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _lock_stream: Lock = field(default_factory=Lock, init=False, repr=False)
    _timebase_span: float = field(default=TIMEBASE_MAP.get("TBASE_SPAN_100MS", None), init=False)
    _adc: Dict[str, deque] = field(default_factory=dict, init=False, repr=False)
    _acquire: bool = field(default=False, init=False, repr=False)
    _acquire_datardy: Event = field(default_factory=Event, init=False, repr=False)
    _mode: str = field(default=ACQUIRE_MODE_RUN, init=False, repr=False)
    # _trig_src: str = field(default=TRIG_SRC_NONE, init=False, repr=False)
    # _trig_pos: str = field(default=TRIG_POS_CENTER, init=False, repr=False)
    # _trig_slope: str = field(default=TRIG_SLOPE_RISE, init=False, repr=False)
    _trig_src: str = field(default='DEFAULT', init=False, repr=False)
    _trig_pos: str = field(default='DEFAULT', init=False, repr=False)
    _trig_slope: str = field(default='DEFAULT', init=False, repr=False)
    _trig_level: int = field(default=1, init=False, repr=False)

    ADC_SAMPLE_RATE: float = 125000.0
    TIME_RECONNECT_AFTER_FWLOAD_S: float = 5.0
    
    def __post_init__(self):
        """Auto-detect port (if needed), open transport, connect, and init buffers."""
        if self.port is None:
            self.port = self._auto_detect_port()
        print(f"Opening {self.port} (app {self.app})")
        self._uc = UCLogger(self.port, logger=self.logger, app=self.app, verbose=self.verbose)
        self._uc._cb_uclog_adc = self._adc_stream_in
        ok, info = self.ez_connect()
        print(f"Connected on {self.port}: {info}")
        if self.auto_enable_output:
            self.enable_output()
        self._reset_adc()
    
    def _reopen_transport(self):
        """Close and reopen the transport (used after firmware load)."""
        try:
            if self._uc:
                self._uc.close()
        except Exception:
            pass
        self._uc = UCLogger(self.port, logger=self.logger, app=self.app, verbose=self.verbose)
        # reattach stream callback
        self._uc._cb_uclog_adc = self._adc_stream_in



    @staticmethod
    def _auto_detect_port() -> str:
        """Return the first port that responds to a ping.

        Returns
        -------
        str
            The detected serial port.
        
        Raises
        ------
        RuntimeError
            If no serial ports are found.

        Examples
        --------
        .. code-block:: ipython

            port = P1150._auto_detect_port()
            print('Detected:', port)
        """
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            raise RuntimeError("No serial ports found")
        # Try each port with a quick ping
        for port in ports:
            try:
                uc = UCLogger(port, logger=StubLogger())
                ok, rsp = uc.send_cmd({'f': CMD('ping')})
                uc.close()
                if ok:
                    return port
            except Exception:
                continue
        # fallback
        return ports[0]

    # ------------- ADC streaming -----------------
    def _reset_adc(self):
        """Reset acquisition buffers to match the current timebase span."""
        n = int(self.ADC_SAMPLE_RATE * self._timebase_span)
        self._adc = {k: deque(maxlen=n) for k in ['t','i','a0','d0','d1','isnk']}
        self._acquire_datardy.clear()

    def _adc_stream_in(self, raw_bytes: bytes):
        """ADC stream handler.

        Parameters
        ----------
        raw_bytes : bytes
            CBOR-encoded frame normalized by the transport layer.
        """
        if not self._acquire:
            return
        try:
            frame = cbor2.loads(raw_bytes)
        except Exception:
            return
        # normalize
        keys = ['i','a0','d0','d1','isnk']
        n = None
        for k in keys:
            v = frame.get(k)
            if v is None: continue
            if not isinstance(v, list): v = [v]
            frame[k] = v
            if n is None: n = len(v)
        if not n:
            return
        start_idx = len(self._adc['i'])
        for idx in range(n):
            self._adc['t'].append((start_idx+idx)/self.ADC_SAMPLE_RATE)
        for k in keys:
            v = frame.get(k)
            if v is None: continue
            for val in v:
                self._adc[k].append(val)
        if len(self._adc['i']) >= self._adc['i'].maxlen:
            self._acquire_datardy.set()

    # ------------- Core commands -----------------
    def _cmd(self, payload: dict):
        """Internal helper to send a command via the transport."""
        return self._uc.send_cmd(payload)

    def ping(self):
        """Ping the device.

        Returns
        -------
        tuple[bool, list]
            ``(success, responses)`` with device metadata in the last response on success.

        Examples
        --------
        .. code-block:: ipython

            ok, rsp = psu.ping()
            if ok:
                print(rsp[-1])
        """
        ok, rsp = self._cmd({'f': CMD('ping')})
        if ok and rsp and len(rsp)==1 and 'serial' in rsp[0]:
            serial_raw = struct.unpack('<III', rsp[0]['serial'])
            s = f'{serial_raw[2]:08X}-{serial_raw[1]:08X}-{serial_raw[0]:08X}'
            rsp[0]['serial'] = s
            rsp[0]['serial_hash'] = hashlib.shake_128(s.encode()).hexdigest(4).upper()
        return ok, rsp

    def status(self):
        """Query device status.

        Returns
        -------
        tuple[bool, list]
            ``(success, responses)``; last dict contains fields like ``cal_done``, ``probe``, ``vout``, etc.

        Examples
        --------
        .. code-block:: ipython

            ok, st = psu.status()
            print(st[-1] if ok else st)
        """
        return self._cmd({'f': CMD('status')})

    def vout_metrics(self):
        """Get VOUT capabilities (min/max/step).

        Returns
        -------
        tuple[bool, list]
            Response payload with voltage range information.

        Examples
        --------
        .. code-block:: ipython

            ok, m = psu.vout_metrics()
            if ok:
                print(m[-1])
        """
        return self._cmd({'f': CMD('vout_metrics')})

    def set_vout(self, mv: int):
        """Set output voltage.

        Parameters
        ----------
        mv : int
            Voltage in millivolts.

        Examples
        --------
        .. code-block:: ipython

            psu.set_vout(1800)
            psu.voltage_mv  # read back
        """
        print(f"Set VOUT {mv} mV")
        return self._cmd({'f': CMD('vout'), 'mv': mv})

    # Friendly aliases
    def set_voltage(self, mv: int):
        """Alias for :meth:`set_vout`.

        Examples
        --------
        .. code-block:: ipython

            psu.set_voltage(3300)
        """
        return self.set_vout(mv)

    def get_voltage(self) -> Optional[int]:
        """Read current output voltage from status.

        Returns
        -------
        int | None
            Voltage in millivolts, or ``None`` if unavailable.

        Examples
        --------
        .. code-block:: ipython

            v = psu.get_voltage()
            print(v)
        """
        ok, st = self.status()
        if not ok or not st:
            return None
        try:
            return int(st[-1].get('vout'))
        except Exception:
            return None

    def set_timebase(self, span_key: str):
        """Set acquisition timebase span.

        Parameters
        ----------
        span_key : str
            One of the keys from ``[timebases]`` in the TOML.

        Returns
        -------
        tuple[bool, None]
            Always ``(True, None)``; adjusts buffers on the client only.

        Examples
        --------
        .. code-block:: ipython

            psu.set_timebase('TBASE_SPAN_200MS')
        """
        self._timebase_span = TIMEBASE_MAP.get(span_key, self._timebase_span)
        self._reset_adc()
        return True, None

    def set_trigger(self,
                    src: str = 'DEFAULT',
                    pos: str = 'DEFAULT',
                    slope: str = 'DEFAULT',
                    level: int = 1):
        """Configure acquisition trigger (client-side only).

        Parameters
        ----------
        src : str
            Trigger source; must be one of ``trigger_sources``. Defaults to NONE if not provided.
        pos : str
            Trigger position; one of ``trigger_positions``.
        slope : str
            Trigger slope; one of ``trigger_slopes``.
        level : int
            Trigger level (units depend on source).

        Returns
        -------
        tuple[bool, None]
            Always ``(True, None)``.

        Examples
        --------
        .. code-block:: ipython

            psu.set_trigger(src='TRIG_SRC_NONE')
        """
        self._trig_src = src if src in TRIG_SRC_LIST else 'DEFAULT' #TRIG_SRC_NONE
        self._trig_pos = pos if pos in TRIG_POS_LIST else 'DEFAULT' #TRIG_POS_CENTER
        self._trig_slope = slope if slope in TRIG_SLOPE_LIST else 'DEFAULT' #TRIG_SLOPE_RISE
        self._trig_level = int(level)
        print(f"Trigger set: src={self._trig_src} pos={self._trig_pos} slope={self._trig_slope} level={self._trig_level}")
        return True, None

    def probe(self, connect: bool=True, hard: bool=False):
        """Enable or disable the probe output.

        Parameters
        ----------
        connect : bool
            ``True`` to connect/enable output, ``False`` to disable.
        hard : bool
            If supported by FW, bypass soft-start when ``True``.

        Examples
        --------
        .. code-block:: ipython

            psu.probe(connect=True)
            psu.probe(connect=False)
        """
        print(f"Probe {'enable' if connect else 'disable'} hard={hard}")
        return self._cmd({'f': CMD('probe'), 'v': connect, 'hard': hard})

    def enable_output(self, hard=False):
        """Enable output (alias).

        Examples
        --------
        .. code-block:: ipython

            psu.enable_output()
        """
        return self.probe(True, hard)

    def disable_output(self):
        """Disable output (alias).

        Examples
        --------
        .. code-block:: ipython

            psu.disable_output()
        """
        return self.probe(False, False)

    def clear_error(self):
        """Clear device error flags if any.

        Examples
        --------
        .. code-block:: ipython

            psu.clear_error()
        """
        return self._cmd({'f': CMD('error_clear')})

    # ------------- Connect/firmware/calibration -------------
    def ez_connect(self):
        """Connect to the device, load firmware if needed, and ensure calibration.

        Steps
        -----
        1. Ping device and verify high-speed link.
        2. If in bootloader, send firmware via bootloader commands and reconnect.
        3. Fetch status; start/poll calibration if required.

        Returns
        -------
        tuple[bool, dict]
            ``(True, info)`` with ping info on success; ``(False, {"ERROR": msg})`` on failure.

        Examples
        --------
        .. code-block:: ipython

            ok, info = psu.ez_connect()
            print(ok, info)
        """
        ok, response = self.ping()
        if not ok:
            return False, {"ERROR":"ping failed"}
        info = response[-1] if isinstance(response, list) else response
        if not info.get('hs', True):
            return False, {"ERROR":"high speed required"}
        if info.get('app') == 'a51':
            ok, res = self._cmd({'f': CMD('bl_init')})
            if not ok: return False, {"ERROR":"bootloader_init failed"}
            mtu = res[0]['mtu']
            fw = os.path.join(os.path.dirname(__file__), 'assets', 'a43_app.signed.ico')
            with open(fw, 'rb') as f: data = f.read()
            while data:
                chunk, data = data[:mtu], data[mtu:]
                ok, _ = self._cmd({'f': CMD('bl_block'), 'data': chunk})
                if not ok:
                    return False, {"ERROR":"bootloader_block failed"}
            ok, _ = self._cmd({'f': CMD('bl_done')})
            if not ok:
                return False, {"ERROR":"bootloader_done failed"}
            #time.sleep(1.0)
            # Device will reboot into app; give USB CDC time to re-enumerate
            print(f"Firmware loaded; waiting {self.TIME_RECONNECT_AFTER_FWLOAD_S}s for app to start...")
            time.sleep(self.TIME_RECONNECT_AFTER_FWLOAD_S)
            # Reopen transport and wait for app ping
            self._reopen_transport()
            t0 = time.time()
            while time.time() - t0 < 8.0:
                ok, response = self.ping()
                if ok:
                    info = response[-1]
                    if info.get('app') == 'a43':
                        break
                time.sleep(0.25)
            else:
                return False, {"ERROR":"app did not come up after FW load"}
        ok, st = self.status()
        if not ok: return False, {"ERROR":"status failed"}
        st = st[-1]
        # print some device info from ping + status
        print(f"Device: app={info.get('app')} hs={info.get('hs')} ver={info.get('version', '?')} "
              f"serial={info.get('serial_hash', info.get('serial', '?'))}")
        print(f"Status: cal_done={st.get('cal_done')} probe={st.get('probe')} vout={st.get('vout')} err=0x{st.get('err',0):X}")
        
        
        if not st.get('cal_done', True):
            # ok, _ = self._cmd({'f': CMD('cal_start'), 'force': True})
            # if not ok: return False, {"ERROR":"cal start failed"}
            # # poll
            # for _ in range(60):
            #     time.sleep(0.5)
            #     ok, r = self._cmd({'f': CMD('cal_status')})
            #     if ok and r[-1].get('cal_done'): break
            self.calibrate(force=True, poll_interval=0.5, timeout=60.0)
        return True, info

    def calibrate(self,
                  force: bool = True,
                  poll_interval: float = 0.5,
                  timeout: float = 60.0):
        """Run a calibration cycle and print status updates until completion.

        Parameters
        ----------
        force : bool
            If True, force a new calibration run on the device.
        poll_interval : float
            Seconds between successive cal_status polls.
        timeout : float
            Maximum time to wait in seconds before giving up.

        Returns
        -------
        tuple[bool, dict]
            (True, final_status) on success; (False, {"ERROR": msg, "last": last_status}) on failure.

        Examples
        --------
        .. code-block:: ipython

            ok, st = psu.calibrate(force=True, poll_interval=0.5, timeout=90)
            print(ok, st)
        """
        print(f"Calibration start force={force}")
        ok, _ = self._cmd({'f': CMD('cal_start'), 'force': bool(force)})
        if not ok:
            return False, {"ERROR": "cal start failed"}
        t0 = time.time()
        last = {}
        while time.time() - t0 < timeout:
            ok, r = self._cmd({'f': CMD('cal_status')})
            if ok and r:
                st = r[-1]
                last = st
                prog = st.get('progress')
                vset = st.get('vout_set')
                vout = st.get('vout')
                err = st.get('err', 0)
                print(f"Calibration status: cal_done={st.get('cal_done')} progress={prog} vout_set={vset} vout={vout} err=0x{int(err):X}")
                if st.get('cal_done'):
                    print("Calibration complete")
                    return True, st
            time.sleep(poll_interval)
        return False, {"ERROR": "calibration timeout", "last": last}

    # ------------- Acquisition helpers -------------
    def acquisition_start(self, mode: str = ACQUIRE_MODE_RUN):
        """Start acquisition.

        Parameters
        ----------
        mode : str
            One of ``acquire_modes`` from the TOML.

        Examples
        --------
        .. code-block:: ipython

            psu.set_timebase('TBASE_SPAN_100MS')
            psu.acquisition_start('ACQUIRE_MODE_SINGLE')
        """
        print(f"Acquisition start mode={mode}")
        self._mode = mode
        self._reset_adc()
        self._acquire = True
        return self._cmd({'f': CMD('adc'), 'en': True})

    def acquisition_stop(self):
        """Stop/abort acquisition.

        Examples
        --------
        .. code-block:: ipython

            psu.acquisition_stop()
        """
        print("Acquisition stop")
        self._acquire = False
        return self._cmd({'f': CMD('adc'), 'en': False})

    def acquisition_complete(self):
        """Return whether a full buffer of data has been received.

        Examples
        --------
        .. code-block:: ipython

            ok, st = psu.acquisition_complete()
            print(st['triggered'])
        """
        return True, {'triggered': self._acquire_datardy.is_set()}

    def acquisition_get_data(self):
        """Get the current acquisition buffer and clear internal buffers.

        Returns
        -------
        tuple[bool, dict|str]
            ``(True, data)`` on success, or ``(False, "No data")`` if buffer not ready.

        Examples
        --------
        .. code-block:: ipython

            ok, data = psu.acquisition_get_data()
            if ok:
                print(len(data['i']))
        """
        if not self._acquire_datardy.is_set():
            return False, "No data"
        data = {k: list(self._adc[k]) for k in ['t','i','a0','d0','d1','isnk']}
        self._reset_adc()
        return True, data

    def wait_for_acquisition(self, timeout: float = 2.0):
        """Block until a full buffer is collected or timeout expires.

        Parameters
        ----------
        timeout : float
            Timeout in seconds.

        Returns
        -------
        dict
            Acquisition data dictionary with keys ``t``, ``i``, ``a0``, ``d0``, ``d1``, ``isnk``.

        Raises
        ------
        TimeoutError
            If the buffer is not ready before ``timeout``.

        Examples
        --------
        .. code-block:: ipython

            data = psu.wait_for_acquisition(2.0)
            print(data.keys())
        """
        print(f"Waiting for acquisition up to {timeout}s")
        t0 = time.time()
        while time.time()-t0 < timeout:
            ok, st = self.acquisition_complete()
            if ok and st.get('triggered'):
                return self.acquisition_get_data()[1]
            time.sleep(0.02)
        raise TimeoutError("Acquisition timeout")

    # Aliases for convenience
    def start_acquisition(self, mode: str = ACQUIRE_MODE_RUN):
        """Alias for :meth:`acquisition_start`.

        Examples
        --------
        .. code-block:: ipython

            psu.start_acquisition('ACQUIRE_MODE_RUN')
        """
        return self.acquisition_start(mode)

    def stop_acquisition(self):
        """Alias for :meth:`acquisition_stop`.

        Examples
        --------
        .. code-block:: ipython

            psu.stop_acquisition()
        """
        return self.acquisition_stop()

    # ------------- Convenience properties -------------
    @property
    def voltage_mv(self) -> Optional[int]:
        """Current output voltage in millivolts from :meth:`status`.

        Returns
        -------
        int | None
            Voltage in mV or ``None`` if unavailable.

        Examples
        --------
        .. code-block:: ipython

            print(psu.voltage_mv)
        """
        ok, st = self.status()
        if not ok or not st:
            return None
        try:
            return int(st[-1].get('vout'))
        except Exception:
            return None

    @voltage_mv.setter
    def voltage_mv(self, mv: int):
        """Set output voltage via :meth:`set_vout`.

        Examples
        --------
        .. code-block:: ipython

            psu.voltage_mv = 1200
        """
        self.set_vout(mv)

    def average_current(self, span_key: str = 'TBASE_SPAN_100MS', mode: str = ACQUIRE_MODE_SINGLE, timeout: float = 2.0) -> Optional[float]:
        """Capture a single buffer and compute average current.

        Parameters
        ----------
        span_key : str
            Timebase key from TOML ``[timebases]``.
        mode : str
            Acquisition mode (typically ``ACQUIRE_MODE_SINGLE``).
        timeout : float
            Timeout for data readiness.

        Returns
        -------
        float | None
            Average current in mA, or ``None`` if data unavailable.

        Examples
        --------
        .. code-block:: ipython

            avg = psu.average_current('TBASE_SPAN_100MS', 'ACQUIRE_MODE_SINGLE', 2.0)
            print(avg)
        """
        print(f"Average current capture span={span_key} mode={mode}")
        self.set_timebase(span_key)
        self.acquisition_start(mode)
        data = self.wait_for_acquisition(timeout)
        if not data or not data.get('i'):
            return None
        arr = data['i']
        avg = sum(arr)/len(arr)
        print(f"Average current: {avg} mA")
        return avg

    def capture_and_plot_current(self,
                                 span_key: str = 'TBASE_SPAN_100MS',
                                 mode: str = ACQUIRE_MODE_SINGLE,
                                 timeout: float = 2.0,
                                 show: bool = True,
                                 save_path: Optional[str] = None,
                                 include_sink: bool = False):
        """Capture a current trace and plot it versus time with PDF and CDF.

        Parameters
        ----------
        span_key : str
            Timebase key from TOML ``[timebases]`` used for buffer span.
        mode : str
            Acquisition mode (e.g., ``ACQUIRE_MODE_SINGLE``).
        timeout : float
            Seconds to wait for data readiness.
        show : bool
            If True, call ``plt.show()`` before returning.
        save_path : str | None
            If set, save the figure to this path.
        include_sink : bool
            If True and available, plot sink current (``isnk``) and its PDF/CDF as well.

        Returns
        -------
        tuple
            ``(fig, axes, data)`` where ``axes`` is a tuple ``(ax_time, ax_hist)``.

        Notes
        -----
        - The time axis is automatically scaled to engineering units (ns/us/ms/s).
        - The histogram is normalized as a probability density function (PDF) and the
          empirical cumulative distribution function (CDF) is overlaid on a secondary y-axis.

        Examples
        --------
        .. code-block:: ipython

            fig, (ax_time, ax_hist), data = psu.capture_and_plot_current(
                'TBASE_SPAN_100MS', 'ACQUIRE_MODE_SINGLE', 2.0)
        """
        print(f"Capture+plot span={span_key} mode={mode}")
        self.set_timebase(span_key)
        self.acquisition_start(mode)
        try:
            data = self.wait_for_acquisition(timeout)
        finally:
            # Ensure we stop streaming so only a single buffer is captured/used
            try:
                self.acquisition_stop()
            except Exception:
                pass
        if not data or 'i' not in data:
            raise RuntimeError("No data available for plotting")
        try:
            import matplotlib.pyplot as plt
        except Exception as e:
            raise ImportError("matplotlib is required for plotting") from e

        # Build time axis and apply engineering unit scaling
        t = data.get('t')
        #print(f"Data points: {len(data['t'])} span={self._timebase_span}s")
        #print(f"Current: min={min(data['t'])} s, max={max(data['t'])} s")
        if not t:
            n = len(data['i'])
            t = [idx / self.ADC_SAMPLE_RATE for idx in range(n)]
        t0 = t[0] if t else 0.0
        span = (t[-1] - t0) if t else 0.0
        if span < 1e-6:
            scale, unit = 1e9, 'ns'
        elif span < 1e-3:
            scale, unit = 1e6, 'us'
        elif span < 1.0:
            scale, unit = 1e3, 'ms'
        else:
            scale, unit = 1.0, 's'
        x = [(ti - t0) * scale for ti in t]

        y = data['i']
        # Ensure time vector matches number of current samples
        x = x[:len(y)]
        fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(8, 6), constrained_layout=True)

        # Time-series plot
        ax0.plot(x, y, label='I_src (mA)')
        if include_sink and data.get('isnk'):
            d_isnk = data['isnk']
            ax0.plot(x[:len(d_isnk)], d_isnk, label='I_snk (mA)', alpha=0.7)
        ax0.set_xlabel(f'Time ({unit})')
        ax0.set_ylabel('Current (mA)')
        avg = (sum(y) / len(y)) if y else 0.0
        ax0.set_title(f'Current capture (avg {avg:.3f} mA)')
        ax0.grid(True, alpha=0.3)
        ax0.legend(loc='best')

        # PDF and CDF as continuous curves (KDE + cumulative integral)
        try:
            import numpy as np
        except Exception:
            np = None

        ax1b = ax1.twinx()
        if np is not None:
            vals_src = np.asarray(y, dtype=float)
            vals_snk = np.asarray(data.get('isnk', []), dtype=float) if (include_sink and data.get('isnk')) else None

            # Determine grid over combined range with small padding
            vmin = np.nanmin(vals_src if vals_snk is None else np.concatenate([vals_src, vals_snk]))
            vmax = np.nanmax(vals_src if vals_snk is None else np.concatenate([vals_src, vals_snk]))
            if not np.isfinite([vmin, vmax]).all() or vmin == vmax:
                pad = 1e-6 if not np.isfinite([vmin, vmax]).all() else max(1e-6, abs(vmin)*1e-3 + 1e-6)
                vmin, vmax = (vmin - pad, vmax + pad) if np.isfinite([vmin, vmax]).all() else (-pad, pad)
            span_v = vmax - vmin
            pad = 0.05 * span_v
            x_grid = np.linspace(vmin - pad, vmax + pad, 512)

            def kde_pdf(samples, grid):
                samples = samples[np.isfinite(samples)]
                n = samples.size
                if n == 0:
                    return np.zeros_like(grid)
                std = np.std(samples)
                if std == 0:
                    # degenerate: all points equal -> approximate with narrow Gaussian
                    h = max(1e-6, 0.1 * (span_v if span_v > 0 else 1.0))
                else:
                    h = 1.06 * std * (n ** (-1/5))
                    h = max(h, 1e-6)
                z = (grid[:, None] - samples[None, :]) / h
                pdf = (np.exp(-0.5 * z*z).sum(axis=1) / (n * h * np.sqrt(2*np.pi)))
                return pdf

            # Source PDF/CDF
            pdf_src = kde_pdf(vals_src, x_grid)
            # CDF via cumulative trapezoid
            dx = np.diff(x_grid)
            cdf_src = np.empty_like(x_grid)
            cdf_src[0] = 0.0
            if len(x_grid) > 1:
                cdf_src[1:] = np.cumsum(0.5 * (pdf_src[:-1] + pdf_src[1:]) * dx)
                if cdf_src[-1] > 0:
                    cdf_src /= cdf_src[-1]
            ax1.plot(x_grid, pdf_src, color='#1f77b4', lw=2.0, label='I_src PDF')
            ax1b.plot(x_grid, cdf_src, color='#1f77b4', lw=1.8, linestyle='--', label='I_src CDF')

            # Sink PDF/CDF if requested
            if vals_snk is not None and vals_snk.size:
                pdf_snk = kde_pdf(vals_snk, x_grid)
                cdf_snk = np.empty_like(x_grid)
                cdf_snk[0] = 0.0
                if len(x_grid) > 1:
                    cdf_snk[1:] = np.cumsum(0.5 * (pdf_snk[:-1] + pdf_snk[1:]) * dx)
                    if cdf_snk[-1] > 0:
                        cdf_snk /= cdf_snk[-1]
                ax1.plot(x_grid, pdf_snk, color='#ff7f0e', lw=2.0, label='I_snk PDF')
                ax1b.plot(x_grid, cdf_snk, color='#ff7f0e', lw=1.8, linestyle='--', label='I_snk CDF')

            # Calculate std dev and variance
            if np is not None:
                std_src = np.std(vals_src) if vals_src.size else 0
                var_src = np.var(vals_src) if vals_src.size else 0
                ax1.annotate(f'Average: {np.mean(vals_src):.3f} mA\nStd Dev: {std_src:.3f} mA\nVariance: {var_src:.3f} mA²', xy=(0.05, 0.75), xycoords='axes fraction',
                             fontsize=10, bbox=dict(boxstyle='round,pad=0.3', edgecolor='black', facecolor='white'))

            ax1.set_xlabel('Current (mA)')
            ax1.set_ylabel('Density (1/mA)')
            ax1.grid(True, alpha=0.3)
            ax1b.set_ylabel('Cumulative probability')
            ax1b.set_ylim(0.0, 1.0)
        else:
            # Fallback without numpy: draw ECDF line; approximate PDF by connecting many-bin histogram centers
            ys = sorted(y)
            n = len(ys)
            if n:
                cdf = [(i+1)/n for i in range(n)]
                ax1b.plot(ys, cdf, color='#1f77b4', lw=1.8, linestyle='--', label='I_src CDF')
            if include_sink and data.get('isnk'):
                ys2 = sorted(data['isnk'])
                n2 = len(ys2)
                if n2:
                    cdf2 = [(i+1)/n2 for i in range(n2)]
                    ax1b.plot(ys2, cdf2, color='#ff7f0e', lw=1.8, linestyle='--', label='I_snk CDF')
            # crude PDF from centers
            centers = []
            dens = []
            if n:
                nb = max(16, min(128, int(np.sqrt(n)) if np else 32))
                # manual bins
                lo, hi = ys[0], ys[-1]
                width = (hi - lo)/nb if hi > lo else 1.0
                counts = [0]*nb
                for v in ys:
                    idx = int((v - lo)/width)
                    idx = min(nb-1, max(0, idx))
                    counts[idx] += 1
                centers = [lo + (i+0.5)*width for i in range(nb)]
                total = sum(counts) * width
                dens = [(c/total) for c in counts]
                ax1.plot(centers, dens, color='#1f77b4', lw=1.8, label='I_src PDF')
            if include_sink and data.get('isnk'):
                ys2 = sorted(data['isnk'])
                n2 = len(ys2)
                if n2:
                    nb = max(16, min(128, int(np.sqrt(n2)) if np else 32))
                    lo2, hi2 = ys2[0], ys2[-1]
                    width2 = (hi2 - lo2)/nb if hi2 > lo2 else 1.0
                    counts2 = [0]*nb
                    for v in ys2:
                        idx2 = int((v - lo2)/width2)
                        idx2 = min(nb-1, max(0, idx2))
                        counts2[idx2] += 1
                    centers2 = [lo2 + (i+0.5)*width2 for i in range(nb)]
                    total2 = sum(counts2) * width2
                    dens2 = [(c/total2) for c in counts2]
                    ax1.plot(centers2, dens2, color='#ff7f0e', lw=1.8, label='I_snk PDF')
            ax1.set_xlabel('Current (mA)')
            ax1.set_ylabel('Density (1/mA)')
            ax1.grid(True, alpha=0.3)
            ax1b.set_ylabel('Cumulative probability')
            ax1b.set_ylim(0.0, 1.0)

        # Unified legend for PDF and CDF
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax1b.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc='best')

        if save_path:
            fig.savefig(save_path, dpi=120, bbox_inches='tight')
        if show:
            plt.show()
        return fig, (ax0, ax1), data

    def close(self):
        """Gracefully stop streaming, disable output, and close transport.

        Examples
        --------
        .. code-block:: ipython

            psu.close()
        """
        print("Closing P1150")
        with self._lock:
            try:
                if self._acquire:
                    self._uc.send_cmd({'f': CMD('adc'), 'en': False})
            except Exception:
                pass
            try:
                # Best-effort to disable output
                self.disable_output()
            except Exception:
                pass
            try:
                if hasattr(self, '_uc') and self._uc:
                    self._uc.close()
            except Exception:
                pass
            self._acquire = False
            self._acquire_datardy.clear()

    def __del__(self):
        """Destructor that ensures resources are released by calling :meth:`close`."""
        try:
            self.close()
        except Exception:
            pass

    # ------------- Class-level convenience -------------
    @classmethod
    def auto(cls, enable_output: bool=False) -> "P1150":
        """Auto-detect and connect to a P1150.

        Parameters
        ----------
        enable_output : bool
            If True, enable output after connecting.

        Returns
        -------
        P1150
            Connected P1150 instance.

        Examples
        --------
        .. code-block:: ipython

            psu = P1150.auto(enable_output=True)
        """
        print("Auto-detecting and connecting to P1150...")
        return cls(auto_enable_output=enable_output)

# Convenience factory
def auto(enable_output=False) -> P1150:
    """Factory wrapper for :meth:`P1150.auto`.

    Examples
    --------
    .. code-block:: ipython

        psu = auto(enable_output=False)
    """
    return P1150.auto(enable_output=enable_output)



'''
import logging

# Configure logging
logging.basicConfig(
    filename="./test.log",       # Log file path
    filemode="a",                # Append mode ("w" for overwrite)
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.DEBUG          # Minimum level: DEBUG, INFO, WARNING, ERROR, CRITICAL
)

# Create a logger instance
logger = logging.getLogger(__name__)



'''






