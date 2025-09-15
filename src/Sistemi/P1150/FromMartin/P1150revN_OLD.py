# -*- coding: utf-8 -*-
"""
P1150revN - Working driver wrapper for Sistemi Corp P1150
=========================================================

This file restores the full manufacturer driver API while adding a few
convenience helpers (scan(), auto(), start_acquisition(), wait_for_acquisition(),
enable_output()/disable_output() aliases) so existing examples keep working.

It is derived from the original `P1150.py` (MIT License) and meant to be a
non-destructive evolution. If you need the latest modern refactor, build on
this known-good baseline first.
"""
from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass, field
from threading import Lock, Event
from collections import deque
from time import sleep
from timeit import default_timer as timer
import traceback
import hashlib
import serial
import serial.tools.list_ports
import cbor2
import uclog

# ---------------------------------------------------------------------------
#  Manufacturer baseline (copied / minimally adjusted)
# ---------------------------------------------------------------------------

class StubLogger(object):
    def info(self, *a, **k): pass
    def error(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def critical(self, *a, **k): pass

@dataclass(frozen=True)
class P1150API:
    ACQUIRE_MODE_RUN = "ACQUIRE_MODE_RUN"
    ACQUIRE_MODE_SINGLE = "ACQUIRE_MODE_SINGLE"
    ACQUIRE_MODE_LOGGER = "ACQUIRE_MODE_LOGGER"
    ACQUIRE_MODE_LIST = [ACQUIRE_MODE_RUN, ACQUIRE_MODE_SINGLE, ACQUIRE_MODE_LOGGER]

    TRIG_SRC_NONE = "TRIG_SRC_NONE"
    TRIG_SRC_CUR  = "TRIG_SRC_CUR"
    TRIG_SRC_D0   = "TRIG_SRC_D0"
    TRIG_SRC_D1   = "TRIG_SRC_D1"
    TRIG_SRC_A0A  = "TRIG_SRC_A0A"
    TRIG_SRC_LIST = [TRIG_SRC_NONE, TRIG_SRC_CUR, TRIG_SRC_D0, TRIG_SRC_D1, TRIG_SRC_A0A]

    TRIG_POS_CENTER = "TRIG_POS_CENTER"
    TRIG_POS_LEFT   = "TRIG_POS_LEFT"
    TRIG_POS_RIGHT  = "TRIG_POS_RIGHT"

    TRIG_SLOPE_RISE = "TRIG_SLOPE_RISE"
    TRIG_SLOPE_FALL = "TRIG_SLOPE_FALL"
    TRIG_SLOPE_EITHER = "TRIG_SLOPE_EITHER"

    TBASE_SPAN_10MS  = "TBASE_SPAN_10MS"
    TBASE_SPAN_20MS  = "TBASE_SPAN_20MS"
    TBASE_SPAN_50MS  = "TBASE_SPAN_50MS"
    TBASE_SPAN_100MS = "TBASE_SPAN_100MS"
    TBASE_SPAN_200MS = "TBASE_SPAN_200MS"
    TBASE_SPAN_500MS = "TBASE_SPAN_500MS"
    TBASE_SPAN_1S    = "TBASE_SPAN_1S"
    TBASE_SPAN_2S    = "TBASE_SPAN_2S"
    TBASE_SPAN_5S    = "TBASE_SPAN_5S"
    TBASE_SPAN_10S   = "TBASE_SPAN_10S"
    TBASE_SPAN_LIST = [TBASE_SPAN_10MS, TBASE_SPAN_20MS, TBASE_SPAN_50MS, TBASE_SPAN_100MS,
                       TBASE_SPAN_200MS, TBASE_SPAN_500MS, TBASE_SPAN_1S, TBASE_SPAN_2S,
                       TBASE_SPAN_5S, TBASE_SPAN_10S]

    DEMO_CAL_LOAD_NONE = "DEMO_CAL_LOAD_NONE"
    DEMO_CAL_LOAD_2M   = "DEMO_CAL_LOAD_2M_"
    DEMO_CAL_LOAD_200K = "DEMO_CAL_LOAD_200K_"
    DEMO_CAL_LOAD_20K  = "DEMO_CAL_LOAD_20K_"
    DEMO_CAL_LOAD_2K   = "DEMO_CAL_LOAD_2K_"
    DEMO_CAL_LOAD_400  = "DEMO_CAL_LOAD_400_"
    DEMO_CAL_LOAD_200  = "DEMO_CAL_LOAD_200_"
    DEMO_CAL_LOAD_100  = "DEMO_CAL_LOAD_100_"
    DEMO_CAL_LOAD_40   = "DEMO_CAL_LOAD_40_"
    DEMO_CAL_LOAD_20   = "DEMO_CAL_LOAD_20_"
    DEMO_CAL_LOAD_10   = "DEMO_CAL_LOAD_10_"
    DEMO_CAL_LOAD_LIST = [DEMO_CAL_LOAD_NONE, DEMO_CAL_LOAD_2M, DEMO_CAL_LOAD_200K, DEMO_CAL_LOAD_20K,
                          DEMO_CAL_LOAD_2K, DEMO_CAL_LOAD_400, DEMO_CAL_LOAD_200, DEMO_CAL_LOAD_100,
                          DEMO_CAL_LOAD_40, DEMO_CAL_LOAD_20, DEMO_CAL_LOAD_10]

    AUX_D01_DISABLE = 0
    AUX_D01_ENABLE = 1

    ERROR_NONE = 0
    ERROR_I2C = (1 << 0)
    ERROR_HAL = (1 << 1)
    ERROR_INIT = (1 << 2)
    ERROR_INIT_TMP = (1 << 3)
    ERROR_INIT_VMAIN = (1 << 4)
    ERROR_INIT_ADC = (1 << 5)
    ERROR_INIT_USBPD = (1 << 6)
    ERROR_TEMPERATURE = (1 << 8)
    ERROR_VOUT_FAILURE = (1 << 9)
    ERROR_CAL = (1 << 10)
    ERROR_PROBE_CON = (1 << 11)
    ERROR_SRC_CURRENT = (1 << 12)
    ERROR_SNK_CURRENT = (1 << 13)

    ERROR_ACT_DISCONNECT = (1 << 0)
    ERROR_ACT_RESET = (1 << 1)
    ERROR_ACT_LOCKOUT = (1 << 2)
    ERROR_ACT_SENDLOG = (1 << 3)

class UCLogger(object):
    TIMEOUT_CMD = 0.02
    DEFAULT_CMD_RETRIES = 30  # increased for reliability
    def __init__(self, port="COM1", cb_uclog_log=None, cb_uclog_plot=None, cb_uclog_async=None, logger=StubLogger(), **kw):
        self._port = port
        self.connected = False
        self.logger = logger
        # auto-create a basic console logger if user passed StubLogger (no attributes beyond methods)
        try:
            import logging
            if isinstance(self.logger, StubLogger):
                _lg = logging.getLogger(f"P1150[{port}]")
                if not _lg.handlers:
                    h = logging.StreamHandler()
                    h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
                    _lg.addHandler(h)
                    _lg.setLevel(logging.INFO)
                self.logger = _lg
        except Exception:
            pass
        self._ucLogServer = None
        self._cb_uclog_log = cb_uclog_log
        self._cb_uclog_plot = cb_uclog_plot
        self._cb_uclog_async = cb_uclog_async
        self._cb_uclog_adc = None
        self._lock_responses = Lock()
        self._cmd_responses = {}
        self._result_event = Event()
        self._adc_frame_count = None
        self._verbose = kw.get('verbose', False)
        try:
            _t = self._port
            _h = uclog.hostport(None)
            base_dir = os.path.dirname(__file__)
            app = kw.get('app', "a43")
            if app == "a43":
                elf_file = os.path.join(base_dir, "assets", "a43_app.logdata")
            elif app == "a57":
                elf_file = os.path.join(base_dir, "assets", "a57_app.logdata")
            else:
                raise ValueError("app must be a43, a57")
            self.logger.info(f"Opening {app} on {self._port} using {elf_file}")
            bl_elf_file = os.path.join(base_dir, "assets", "a51_bl.logdata")
            _e = uclog.decoders([elf_file, bl_elf_file])
            self._ucLogServer = uclog.LogClientServer(_t, _e, {'log': self._uclog_log, 0: self._uclog_cmdres, 1: self._uclog_async, 2: self._uclog_plot, 3: self._uclog_adc})
            self.connected = True
        except serial.SerialException as e:
            self.connected = False
            self.logger.error(f"SerialException opening {self._port}: {e}")
        except Exception as e:
            self.connected = False
            self.logger.error(f"Connection setup failed: {e}")
            traceback.print_exc()
            if self._ucLogServer:
                self._ucLogServer.shutdown()
            self._ucLogServer = None
    def set_verbose(self, enable: bool=True):
        self._verbose = enable
    def is_connected(self): return self.connected
    def _uclog_plot(self, item):
        if self._cb_uclog_plot: self._cb_uclog_plot(item)
    def _uclog_log(self, item):
        if self._cb_uclog_log: self._cb_uclog_log.uclog_item(item)
        try:
            _, _, lvl, file, line, msg = item
            if lvl == "ERROR": self.logger.error(f"== {lvl:5}:{file:30}:{line:4}: {msg}")
            else: self.logger.info(f"== {lvl:5}:{file:30}:{line:4}: {msg}")
        except Exception as e:
            self.logger.error(e); self.logger.error(item)
    def _uclog_async(self, _item):
        item = cbor2.loads(_item)
        if self._verbose:
            self.logger.debug(f"ASYNC: {item}")
        with self._lock_responses:
            if self._cb_uclog_async: self._cb_uclog_async(item)
    def _uclog_adc(self, _item): pass  # implemented in subclass
    def _uclog_cmdres(self, _item):
        item = cbor2.loads(_item)
        if "f" not in item:
            self.logger.error(f"Malformed response: {item}"); return
        with self._lock_responses:
            f = item["f"]
            if f in self._cmd_responses:
                self._cmd_responses[f].append(item)
                self._result_event.set()
            else:
                self._cmd_responses[f] = [item]
                # Unexpected response could indicate stale command id reuse
                self.logger.warning(f"Unexpected response bucket created for {f}: {item}")
    def uclog_response(self, payload: dict):
        if not self._ucLogServer:
            self.logger.error("No transport available (device not connected)")
            return False, None
        f = payload["f"]
        send_ts = time.time()
        with self._lock_responses:
            self._cmd_responses[f] = []
            try:
                if self._verbose:
                    self.logger.debug(f"TX {f}: {payload}")
                self._result_event.clear()
                self._ucLogServer[0](cbor2.dumps(payload))
            except Exception as e:
                self.logger.error(e); return False, None
        retries = self.DEFAULT_CMD_RETRIES
        while retries > 0:
            retries -= 1
            got = self._result_event.wait(timeout=0.15)
            if not got:
                continue
            with self._lock_responses:
                bucket = self._cmd_responses.get(f, [])
                if bucket:
                    success = bucket[-1]["s"]
                    resp = self._cmd_responses.pop(f)
                    if self._verbose:
                        self.logger.debug(f"RX {f} ({time.time()-send_ts:0.3f}s) -> {resp}")
                    return success, resp
        self.logger.error(f"Timeout waiting for {f} after {time.time()-send_ts:0.2f}s")
        return False, None
    def uclog_close(self):
        with self._lock_responses:
            if self._ucLogServer:
                self._ucLogServer.shutdown(); self._ucLogServer = None
            self._cb_uclog_log = self._cb_uclog_plot = self._cb_uclog_async = None
        self.logger.info("closed")

@dataclass(eq=False)
class P1150(UCLogger):
    # Public configuration fields -------------------------------------------------
    port: str = "COM1"
    app: str = "a43"  # target application (a43 normal, a57 optional)
    verbose: bool = False
    auto_connect: bool = True   # perform ez_connect in __post_init__
    auto_enable_output: bool = False  # enable probe output after connect
    cb_acquisition_get_data: callable | None = None  # user callback for acquisition frames completion
    logger: object = field(default_factory=StubLogger)

    # Internal (non-init) --------------------------------------------------------
    _lock: Lock = field(init=False, repr=False)
    _lock_stream: Lock = field(init=False, repr=False)
    _hwver: str | None = field(default=None, init=False, repr=False)
    _buffered_adc_frame_count: int | None = field(default=None, init=False, repr=False)
    _acquire: bool = field(default=False, init=False, repr=False)
    _acquire_mode: str = field(default=P1150API.ACQUIRE_MODE_RUN, init=False, repr=False)
    _acquire_triggered: Event = field(default_factory=Event, init=False, repr=False)
    _acquire_datardy: Event = field(default_factory=Event, init=False, repr=False)
    _trigger_level: int = field(default=1, init=False, repr=False)
    _trigger_pos: str = field(default=P1150API.TRIG_POS_CENTER, init=False, repr=False)
    _trigger_slope: str = field(default=P1150API.TRIG_SLOPE_RISE, init=False, repr=False)
    _trigger_src: str = field(default=P1150API.TRIG_SRC_NONE, init=False, repr=False)
    _trigger_idx: int = field(default=0, init=False, repr=False)
    _trigger_idx_precond: bool = field(default=False, init=False, repr=False)
    _mahr_stop_time_s: float = field(default=60.0, init=False, repr=False)
    _timebase_span: float = field(default=0.100, init=False, repr=False)
    NUM_SAMPLES: int = field(default=0, init=False)
    _trig_src_map: dict = field(default_factory=dict, init=False, repr=False)
    _adc: dict | None = field(default=None, init=False, repr=False)
    _adc_buf: dict = field(default_factory=dict, init=False, repr=False)
    _verbose_user_enabled: bool = field(default=False, init=False, repr=False)

    # Constants reused
    D0_VLOW = 20; D1_VLOW = 40; D0_VHIGH = 1000; D1_VHIGH = 1100
    TIME_RECONNECT_AFTER_FWLOAD_S = 5.0
    DELAY_WAIT_CALIBRATION_START_S = 15
    DELAY_WAIT_CALIBRATION_POLL_S = 1
    RETRIES_CALIBRATION_POLL = 60
    RETRIES_ACQUISITION_COMPLETE = 10
    DELAY_WAIT_ACQUISITION_POLL_S = 0.01
    ADC_SAMPLE_RATE = 125000.0
    TBASE_MAP = {P1150API.TBASE_SPAN_10MS:0.010,P1150API.TBASE_SPAN_20MS:0.020,P1150API.TBASE_SPAN_50MS:0.050,
                 P1150API.TBASE_SPAN_100MS:0.100,P1150API.TBASE_SPAN_200MS:0.200,P1150API.TBASE_SPAN_500MS:0.500,
                 P1150API.TBASE_SPAN_1S:1.0,P1150API.TBASE_SPAN_2S:2.0,P1150API.TBASE_SPAN_5S:5.0,P1150API.TBASE_SPAN_10S:10.0}
    EVENT_SHUTDOWN = "EVENT_SHUTDOWN"

    # ---------------------------------------------------------------------
    # Dataclass post initialization (replaces previous __init__)
    # ---------------------------------------------------------------------
    def __post_init__(self):
        # Initialize parent transport/logger
        super().__init__(port=self.port, logger=self.logger, app=self.app, verbose=self.verbose)
        self._lock = Lock(); self._lock_stream = Lock()
        self._cb_uclog_adc = self.adc_stream_in  # hook ADC stream
        self._timebase_span = self.TBASE_MAP[P1150API.TBASE_SPAN_100MS]
        self.NUM_SAMPLES = int(self._timebase_span * self.ADC_SAMPLE_RATE)
        self._trig_src_map = {P1150API.TRIG_SRC_CUR: "i", P1150API.TRIG_SRC_A0A: "a0", P1150API.TRIG_SRC_D0: "d0", P1150API.TRIG_SRC_D1: "d1"}
        self._adc_buf = {k: deque(maxlen=12500) for k in ["t","i","a0","d0","d1","isnk"]}
        self._event_clear_datardy(); self._set_trigger_idx()
        if self.auto_connect:
            ok, info = self.ez_connect()
            self._echo(f"Auto connect {'OK' if ok else 'FAIL'}: {info}")
            if ok and self.auto_enable_output:
                self.enable_output()

    # ------------------------------------------------------------------
    # Utility internal helpers
    # ------------------------------------------------------------------
    def _echo(self, msg: str, level: str = "info"):
        # Always print for interactive friendliness
        print(msg)
        # Mirror to logger
        log = getattr(self.logger, level, None)
        if callable(log):
            try: log(msg)
            except Exception: pass

    # ---- ADC data path (simplified but functional) ---------------------
    def adc_stream_in(self, item):
        if not self._acquire:
            return
        with self._lock_stream:
            self._event_adc_stream_in(item)

    def _event_adc_stream_in(self, item):
        # Attempt CBOR decode
        try:
            frame = cbor2.loads(item)
        except Exception:
            return
        if self._adc is None:
            self._event_clear_datardy()
        # Collect sample vectors (assume lists; coerce scalars)
        keys = ["i","a0","d0","d1","isnk"]
        # Determine number of samples in frame
        n = None
        for k in keys:
            if k in frame:
                v = frame[k]
                if not isinstance(v, list):
                    v = [v]
                    frame[k] = v
                if n is None:
                    n = len(v)
        if n is None or n == 0:
            return
        # Time vector generation (client side incremental)
        start_idx = len(self._adc['i']) if self._adc and 'i' in self._adc else 0
        for idx in range(n):
            t_val = (start_idx + idx) / self.ADC_SAMPLE_RATE
            self._adc['t'].append(t_val)
        for k in keys:
            data = frame.get(k)
            if data is None:
                continue
            dq = self._adc[k]
            for v in data:
                dq.append(v)
        # Trigger/data ready condition (simple: buffer full OR single mode and reached samples)
        if len(self._adc['i']) >= self.NUM_SAMPLES:
            self._acquire_datardy.set()
            if self.cb_acquisition_get_data:
                try:
                    snapshot = {ch: list(self._adc[ch]) for ch in ["t","i","a0","d0","d1","isnk"]}
                    self.cb_acquisition_get_data(snapshot)
                except Exception as e:
                    self._echo(f"Callback error: {e}", 'error')
            if self._acquire_mode == P1150API.ACQUIRE_MODE_SINGLE:
                self._acquire = False  # stop capturing further

    def _event_clear_datardy(self):
        self.NUM_SAMPLES = int(self.ADC_SAMPLE_RATE * self._timebase_span)
        self._adc = {k: deque(maxlen=self.NUM_SAMPLES) for k in ["t","i","a0","d0","d1","isnk"]}
        self._acquire_triggered.clear(); self._acquire_datardy.clear()

    def _set_trigger_idx(self):
        if self._trigger_pos == P1150API.TRIG_POS_CENTER:
            self._trigger_idx = int(self.NUM_SAMPLES/2)
        elif self._trigger_pos == P1150API.TRIG_POS_LEFT:
            self._trigger_idx = int(self.NUM_SAMPLES/4)
        else:
            self._trigger_idx = int(self.NUM_SAMPLES - self.NUM_SAMPLES/4)

    # Public high-level API (wrappers adding printing) ------------------
    def close(self):
        self._echo("Disconnecting")
        self.uclog_close()

    # Voltage convenience property --------------------------------------
    @property
    def voltage_mv(self) -> int | None:
        ok, resp = self.vout_metrics()
        if not ok or not resp:
            return None
        try:
            data = resp[-1]
            # Attempt common keys
            for k in ("mv", "vout_mv", "vout"):
                if k in data:
                    return int(data[k])
        except Exception:
            return None
        return None

    @voltage_mv.setter
    def voltage_mv(self, mv: int):
        self.set_vout(mv)

    def temperature_update(self):
        self._echo("Query temperature")
        with self._lock: return self.uclog_response({"f":"cmd_temp102_trigger"})

    def status(self):
        with self._lock:
            ok, resp = self.uclog_response({"f":"cmd_status"})
            self._echo(f"Status -> {resp}")
            return ok, resp

    def vout_metrics(self):
        with self._lock:
            ok, resp = self.uclog_response({"f":"cmd_vout_metrics"})
            self._echo(f"VOUT metrics -> {resp}")
            return ok, resp

    def set_vout(self, mv):
        self._echo(f"Set VOUT {mv} mV")
        with self._lock: return self.uclog_response({"f":"cmd_vout", "mv": mv})

    def set_ovc(self, ma):
        self._echo(f"Set OVC {ma} mA")
        with self._lock: return self.uclog_response({"f":"cmd_ovrcur", "ma": ma})

    def set_timebase(self, span):
        self._echo(f"Set timebase {span}")
        with self._lock_stream:
            self._timebase_span = self.TBASE_MAP[span]
            self._event_clear_datardy(); self._set_trigger_idx(); return True, None

    def set_trigger(self, src=P1150API.TRIG_SRC_NONE, pos=P1150API.TRIG_POS_LEFT, slope=P1150API.TRIG_SLOPE_RISE, level=1):
        self._echo(f"Set trigger src={src} pos={pos} slope={slope} level={level}")
        with self._lock_stream:
            self._trigger_level = int(self.D0_VHIGH/2) if src in [P1150API.TRIG_SRC_D0, P1150API.TRIG_SRC_D1] else level
            self._trigger_pos = pos; self._trigger_slope = slope; self._trigger_src = src
            return True, None

    def set_cal_sweep(self, sweep: bool):
        self._echo(f"Set cal sweep {sweep}")
        with self._lock: return self.uclog_response({"f":"cmd_iload_sweep", "en": sweep})

    def acquisition_start(self, mode):
        self._echo(f"Acquisition start mode={mode}")
        with self._lock:
            if self._acquire:
                return self.uclog_response({"f":"cmd_adc", "en": True})
            self.NUM_SAMPLES = int(self.ADC_SAMPLE_RATE * self._timebase_span)
            self._set_trigger_idx(); self._acquire_mode = mode; self._event_clear_datardy(); self._acquire = True
            return self.uclog_response({"f":"cmd_adc", "en": True})

    def acquisition_stop(self):
        self._echo("Acquisition stop")
        with self._lock:
            self._acquire = False; self._acquire_triggered.clear(); self._event_clear_datardy(); self._buffered_adc_frame_count = 0
            for k in ["i","a0","d0","d1","isnk"]: self._adc_buf[k].clear()
            return self.uclog_response({"f":"cmd_adc", "en": False})

    def acquisition_complete(self):
        with self._lock:
            ready = self._acquire_datardy.is_set()
            return True, {"triggered": ready}

    def acquisition_get_data(self):
        if not self._acquire_datardy.is_set():
            return False, "No data"
        d = {k: [*self._adc[k]] for k in ["t","i","a0","d0","d1","isnk"]}
        self._event_clear_datardy(); return True, d

    def probe(self, connect=True, hard_connect=False):
        self._echo(f"Probe {'enable' if connect else 'disable'} hard={hard_connect}")
        with self._lock: return self.uclog_response({"f":"cmd_probe", "v": connect, "hard": hard_connect})

    def enable_output(self, hard=False):
        return self.probe(connect=True, hard_connect=hard)

    def disable_output(self):
        return self.probe(connect=False)

    def clear_error(self):
        self._echo("Clear error")
        with self._lock: return self.uclog_response({"f":"cmd_error_clear"})

    def ping(self):
        with self._lock:
            rsp = self.uclog_response({"f":"cmd_ping"})
            if (len(rsp)==2) and rsp[1] and len(rsp[1])==1 and 'serial' in rsp[1][0]:
                serial_raw = struct.unpack('<III', rsp[1][0]['serial'])
                s = f'{serial_raw[2]:08X}-{serial_raw[1]:08X}-{serial_raw[0]:08X}'
                rsp[1][0]['serial'] = s
                ser = hashlib.shake_128(s.encode()).hexdigest(4).upper()
                rsp[1][0]['serial_hash'] = ser
            self._echo(f"Ping -> {rsp}")
            return rsp

    def bootloader_init(self):
        with self._lock: return self.uclog_response({"f":"bl_init"})

    def bootloader_block(self, data: bytes):
        with self._lock: return self.uclog_response({"f":"bl_block", "data": data})

    def bootloader_done(self):
        with self._lock: return self.uclog_response({"f":"bl_done"})

    def cmd(self, cmd: dict):
        with self._lock: return self.uclog_response(cmd)

    def ez_connect(self):
        self._echo("Performing ez_connect sequence")
        success, response = self.ping()
        if not success:
            self._echo(f"Ping failed: {response}", 'error')
            return False, {"ERROR":"ping failed"}
        _response = response[-1]
        if not _response.get("hs", True):
            self._echo("High speed required", 'error')
            return False, {"ERROR":"high speed required"}
        if _response.get("app") == "a51":
            self._echo("Bootloader mode: starting firmware update")
            success, result = self.bootloader_init()
            if not success:
                return False, {"ERROR":"bootloader_init failed"}
            mtu = result[0]['mtu']
            firmware_file = os.path.join(os.path.dirname(__file__), "assets", "a43_app.signed.ico")
            with open(firmware_file,'rb') as f: data = f.read()
            total = len(data); sent=0
            while data:
                d, data = data[:mtu], data[mtu:]
                sent += len(d)
                success, result = self.bootloader_block(d)
                if not success:
                    return False, {"ERROR":"bootloader_block failed"}
                if sent % (mtu*50) == 0:
                    self._echo(f"FW {sent}/{total} bytes")
            success, result = self.bootloader_done()
            if not success: return False, {"ERROR":"bootloader_done failed"}
            self._echo("Firmware flashed; waiting for reconnect")
            self.close(); time.sleep(0.2)
            start = time.time(); found=False
            while time.time()-start < self.TIME_RECONNECT_AFTER_FWLOAD_S:
                if self.port in [p.device for p in serial.tools.list_ports.comports()]:
                    found=True; break
                time.sleep(0.05)
            if not found:
                return False, {"ERROR":f"P1150 not found on port {self.port} after FW update"}
            time.sleep(1)
            return True, _response
        success, response_status = self.status()
        if not success:
            return False, {"ERROR":"status failed"}
        response_status = response_status[-1]
        if not response_status.get('cal_done', True):
            self._echo("Calibration required; starting")
            success, result = self.calibrate(blocking=False, force=True)
            if not success:
                return False, {"ERROR":"calibrate start failed"}
            while True:
                time.sleep(0.5)
                success, result = self.cal_status()
                if not success:
                    return False, {"ERROR":"calibrate in progress failed"}
                if result[-1].get('cal_done'):
                    self._echo("Calibration complete")
                    break
        else:
            self._echo("Calibration already complete")
        return True, _response

    # Convenience wrappers (compatibility) ------------------------------
    def start_acquisition(self, mode=P1150API.ACQUIRE_MODE_RUN):
        self.acquisition_start(mode)

    def wait_for_acquisition(self, timeout=2.0):
        start_t = time.time()
        while time.time()-start_t < timeout:
            success, state = self.acquisition_complete()
            if success and state.get("triggered"):
                return self.acquisition_get_data()[1]
            time.sleep(0.02)
        raise TimeoutError("Acquisition timeout")

    # High-level helper: average current --------------------------------
    def average_current(self, span=P1150API.TBASE_SPAN_100MS, mode=P1150API.ACQUIRE_MODE_SINGLE, timeout=2.0):
        self.set_timebase(span)
        self.acquisition_start(mode)
        try:
            data = self.wait_for_acquisition(timeout=timeout)
            if not data or not data.get('i'):
                return None
            return sum(data['i'])/len(data['i'])
        except TimeoutError:
            # fallback to vout metrics
            ok, resp = self.vout_metrics()
            if ok and resp and isinstance(resp, list):
                last = resp[-1]
                for k in ('i_ma','imain_ma','ma','current_ma'):
                    if k in last:
                        return float(last[k])
            return None

    # Class-level helpers -------------------------------------------------
    @classmethod
    def auto(cls, ports=None, enable_output=False, hard=False, calibrate=True, logger=None, verbose=False):
        if ports is None:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        last_error = None
        for port in ports:
            dev = None
            try:
                dev = cls(port=port, logger=logger or StubLogger(), verbose=verbose, auto_connect=False)
                if verbose:
                    dev.set_verbose(True)
                dev._echo(f"Trying port {port}")
                ok, info = dev.ez_connect()
                if not ok:
                    dev._echo(f"Port {port} not a ready P1150: {info}")
                    dev.close(); continue
                dev._echo(f"Connected on {port}: {info}")
                if calibrate:
                    pass  # handled in ez_connect
                if enable_output:
                    dev._echo("Enabling probe output")
                    dev.enable_output(hard=hard)
                return dev
            except Exception as e:
                last_error = e
                if dev: dev.close()
                continue
        raise RuntimeError(f"No P1150 device found. Last error: {last_error}")

# ---------------------------------------------------------------------------
#  Added utility functions (scan / auto)
# ---------------------------------------------------------------------------

def scan(include_non_p1150=False, quick=True):
    """Scan serial ports for P1150 devices.
    quick=True performs a lightweight ping (no ez_connect) to minimize delay.
    Returns list of (port, info_dict_or_None)."""
    found = []
    ports = [p.device for p in serial.tools.list_ports.comports()]
    for port in ports:
        dev = None
        try:
            dev = P1150(port=port, logger=StubLogger())
            if quick:
                ok, res = dev.ping()
            else:
                ok, res = dev.ez_connect()
            info = res[-1] if (ok and res) else None
            found.append((port, info if ok else None))
        except Exception:
            if include_non_p1150:
                found.append((port, None))
        finally:
            if dev: dev.close()
    return found

def auto(enable_output=True, hard=False, calibrate=True, verbose=False):
    """Module-level helper forwarding to P1150.auto()."""
    return P1150.auto(enable_output=enable_output, hard=hard, calibrate=calibrate, verbose=verbose)

# Also attach as classmethods for backward compatibility (overwriting prior lambdas)
P1150.scan = classmethod(lambda cls: scan())  # type: ignore
# P1150.auto already defined as classmethod above.

__all__ = ["P1150", "P1150API", "scan", "auto"]
