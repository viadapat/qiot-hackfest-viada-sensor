
"""Read the MICS6814 via an ads1015 ADC"""

from flask import Flask, jsonify
import time
import atexit
import ads1015
from flask_json import FlaskJSON, as_json, json_response, JsonError
from pms5003 import PMS5003, PMS5003Data, ReadTimeoutError
import RPi.GPIO as GPIO
import serial
import struct
import logging
from logging.handlers import RotatingFileHandler



app = Flask(__name__)
FlaskJSON(app)

MICS6814_HEATER_PIN = 24
MICS6814_GAIN = 6.144

ads1015.I2C_ADDRESS_DEFAULT = ads1015.I2C_ADDRESS_ALTERNATE
_is_setup = False
_adc_enabled = False
_adc_gain = 6.148


pms5003 = PMS5003()

class Mics6814Reading(object):
    __slots__ = 'oxidising', 'reducing', 'nh3', 'adc'

    def __init__(self, ox, red, nh3, adc=None):
        self.oxidising = ox
        self.reducing = red
        self.nh3 = nh3
        self.adc = adc

    def __repr__(self):
        fmt = """Oxidising: {ox:05.02f} Ohms
Reducing: {red:05.02f} Ohms
NH3: {nh3:05.02f} Ohms"""
        if self.adc is not None:
            fmt += """
ADC: {adc:05.02f} Volts
"""
        return fmt.format(
            ox=self.oxidising,
            red=self.reducing,
            nh3=self.nh3,
            adc=self.adc)

    __str__ = __repr__

class GasClass(dict):
    def __init__(self, data):
       dict.__init__(self, adc =data.adc, nh3 = data.nh3, oxidising = data.oxidising, reducing = data.reducing)

def setup():
    global adc, _is_setup
    if _is_setup:
        return
    _is_setup = True

    adc = ads1015.ADS1015(i2c_addr=0x49)
    adc.set_mode('single')
    adc.set_programmable_gain(MICS6814_GAIN)
    adc.set_sample_rate(1600)

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MICS6814_HEATER_PIN, GPIO.OUT)
    GPIO.output(MICS6814_HEATER_PIN, 1)
    atexit.register(cleanup)


def enable_adc(value=True):
    """Enable reading from the additional ADC pin."""
    global _adc_enabled
    _adc_enabled = value


def set_adc_gain(value):
    """Set gain value for the additional ADC pin."""
    global _adc_gain
    _adc_gain = value


def cleanup():
    GPIO.output(MICS6814_HEATER_PIN, 0)


def read_all():
    """Return gas resistence for oxidising, reducing and NH3"""
    setup()
    ox = adc.get_voltage('in0/gnd')
    red = adc.get_voltage('in1/gnd')
    nh3 = adc.get_voltage('in2/gnd')

    try:
        ox = (ox * 56000) / (3.3 - ox)
    except ZeroDivisionError:
        ox = 0

    try:
        red = (red * 56000) / (3.3 - red)
    except ZeroDivisionError:
        red = 0

    try:
        nh3 = (nh3 * 56000) / (3.3 - nh3)
    except ZeroDivisionError:
        nh3 = 0

    analog = None

    if _adc_enabled:
        if _adc_gain == MICS6814_GAIN:
            analog = adc.get_voltage('ref/gnd')
        else:
            adc.set_programmable_gain(_adc_gain)
            time.sleep(0.05)
            analog = adc.get_voltage('ref/gnd')
            adc.set_programmable_gain(MICS6814_GAIN)

    return Mics6814Reading(ox, red, nh3, analog)

def read_oxidising():
    """Return gas resistance for oxidising gases.

    Eg chlorine, nitrous oxide
    """
    setup()
    return str(read_all().oxidising)


def read_reducing():
    """Return gas resistance for reducing gases.

    Eg hydrogen, carbon monoxide
    """
    setup()
    return read_all().reducing


def read_nh3():
    """Return gas resistance for nh3/ammonia"""
    setup()
    return read_all().nh3


def read_adc():
    """Return spare ADC channel value"""
    setup()
    return read_all().adc

def get_serial_number():
   with open('/sys/firmware/devicetree/base/serial-number', 'r') as f:
      serial_number = f.readline()
      return serial_number.strip()

@app.route('/gas')
@as_json
def gas():
   try:
        setup()
        readings = read_all()
        gas = GasClass(readings)
        gas['stationId'] = get_serial_number()
        return gas
   except Exception as e:
        print(e)

@app.route('/serial')
@as_json
def serial():
   try:
        return  get_serial_number()
   except Exception as e:
        print(e)

@app.route('/particulates')
@as_json
def patriculates():
  try:
     pms5003 = PMS5003()
     readings = pms5003.read().data
     returnDict = {
                'pm1_0':readings[0],
                'pm2_5':readings[1],
                'pm10':readings[2],
                'pm1_0_atm':readings[3],
                'pm2_5_atm':readings[4],
                'pm10_atm':readings[5],
                'gt0_3um':readings[6],
                'gt0_5um':readings[7],
                'gt1_0um':readings[8],
                'gt2_5um':readings[9],
                'gt5_0um':readings[10],
                'gt10um':readings[11],
		'stationId':get_serial_number() 
     }
     patriculates = jsonify(returnDict)
     return patriculates
  except Exception as e:
     print(e)

