#!/usr/bin/env python3
"""
Controls a PWM capable fan connected to a PWM pin on the Raspberry Pi

Copyright © 2021 Qetesh
This work is free. You can redistribute it and/or modify it under the
terms of the Do What The Fuck You Want To Public License, Version 2,
as published by Sam Hocevar. See the LICENSE file for more details.

To enable hardware pwm, add to /boot/config.txt: dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
This will enable pwm channel 0 on GPIO 12 (PIN 32) and channel 1 on GPIO 13 (PIN 33)
Don't forget to reboot for this to have an effect
"""

from rpi_hardware_pwm import HardwarePWM, HardwarePWMException
from threading import Timer
import signal
import pathlib
import os

# Default values
CHANNEL = 0         # PWM Channel - 0 or 1
MINTEMP = 40        # Minimum temperature in °C - fan is always off below this value
MAXTEMP = 60        # Maximum temperature in °C - fan is always at 100% above this value
HYSTERESIS = 3      # Temperature hysteresis in °C for switching the fan on and off around mintemp
MINDC = 20          # Minimum Duty Cycle for the fan
MAXDC = 100         # Maximum Duty Cycle for the fan
SLEEPTIME = 5       # time in seconds between updates
WRITEFILES = True   # write current temperature and dutycycle into files in run directory for external use


class PWMFan:
    def __init__(self,
                 PWMChannel: int = CHANNEL,
                 mintemp: int = MINTEMP,
                 maxtemp: int = MAXTEMP,
                 hysteresis: int = HYSTERESIS,
                 mindc: int = MINDC,
                 maxdc: int = MAXDC,
                 sleeptime: int = SLEEPTIME,
                 writeFiles: bool = WRITEFILES,
                 temperaturePath: str = "/sys/class/thermal/thermal_zone0/temp"
                 ) -> None:
        """
        :param PWMChannel: 0 or 1
        :param mintemp: Temperature less than this and the fan is off
        :param maxtemp: Temperature more than this and the fan runs full speed
        :param hysteresis: Hysteresis for switching the fan on and off around mintemp
        :param mindc: Minimum duty cycle for the fan
        :param maxdc: Maximum duty cycle for the fan
        :param sleeptime: Sleep time in seconds between updates when looping
        :param writeFiles: write current temperature and dutycycle into files in run directory for external use
        :param temperaturePath: path to read system temperature - don't change this unless you know what you're doing
        """

        # Initialize local objects
        self.sleeptime = sleeptime
        self.mintemp = mintemp
        self.maxtemp = maxtemp
        self.hysteresis = hysteresis
        self.hystOn = False
        self.mindc = mindc
        self.maxdc = maxdc
        self.temperaturePath = temperaturePath
        self.running = False
        self.writeFiles = writeFiles
        self.lasttemp = 0
        self.cwd = str(pathlib.Path.cwd())
        self.tempfile = self.cwd + "/temperature"
        self.dcfile = self.cwd + "/dutycycle"
        self._timer = None

        # Try to initialize hardware PWM
        try:
            self.pwm = HardwarePWM(PWMChannel, hz=25000)
        except HardwarePWMException:
            # Warn if hardware PWM does not work
            self.pwm = None
            print("Hardware-PWM is not active! "
                  "Add dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4 to /boot/congig.txt and reboot to enable!")

        # Initialize the fan at 100% speed
        if self.pwm is not None:
            self.pwm.start(100)

        # get and set paths
        print("Current working directory:", self.cwd)
        if self.writeFiles:
            print("Temperature File:", self.tempfile)
            print("Duty Cycle File:", self.dcfile)

        # Initialize signal handlers
        signal.signal(signal.SIGINT, self._sig)
        signal.signal(signal.SIGHUP, self._sig)
        signal.signal(signal.SIGTERM, self._sig)

    def start(self, sleeptime: int = None) -> None:
        """
        Start the timer interval
        :param sleeptime: Change sleep time
        """
        if self.running is False:
            print("Starting the fan controller...")
            self.running = True
            if sleeptime is not None:
                self.sleeptime = sleeptime
            self._runTimer()

    def _runTimer(self):
        """
        Set and start a timer thread
        :return:
        """
        if self.running:
            self._timer = Timer(self.sleeptime, self.updateFan)
            self._timer.start()

    def _sig(self, signum, frame) -> None:
        """
        Signal handler
        """
        print(F"{signal.Signals(signum).name} ({signum}) cought in frame {frame}")
        self.stop()

    def stop(self) -> None:
        """
        Stop PWM and clean up
        """
        print("Stopping the fan controller...")
        self._timer.cancel()
        self.running = False
        self.pwm.stop()
        if os.path.exists(self.tempfile):
            os.remove(self.tempfile)
        if os.path.exists(self.dcfile):
            os.remove(self.dcfile)

    def updateFan(self) -> None:
        """
        Call this to update the fan speed

        Also gets called by the timer thread
        """
        # Get current temperature
        try:
            with open(self.temperaturePath, "r") as t:
                temperature = int(t.readline().strip()) / 1000
        except FileNotFoundError:
            print(self.temperaturePath, "not found, using max value")
            temperature = self.maxtemp

        # check if temperature changed. If so, go on
        if temperature != self.lasttemp:
            # store temperature for next loop
            self.lasttemp = temperature
            if temperature < self.mintemp or (temperature < self.mintemp + self.hysteresis and self.hystOn is False):
                # fan is off when temp below mintemp or hysteresis level
                self.hystOn = False
                dc = 0
            elif temperature >= self.maxtemp:
                # fan is fully on when temp above maxtemp
                self.hystOn = True
                dc = 100
            else:
                # calculate duty cycle when temp is between min and max
                self.hystOn = True
                dc = int((temperature - self.mintemp) * (self.maxdc - self.mindc) /
                         (self.maxtemp - self.mintemp) + self.mindc)
            # set duty cycle
            if self.pwm is not None:
                self.pwm.change_duty_cycle(dc)
            # print out temperature and dc
            print(f"Temperature: {temperature:4.1f}°C - DutyCycle: {dc}%")
            if self.writeFiles:
                # write temperature and dutycycle values to files in run directory
                try:
                    with open(self.tempfile, "w") as tempfile:
                        tempfile.write(str(temperature))
                except FileNotFoundError:
                    print("Can't write temperature file")
                try:
                    with open(self.dcfile, "w") as dcfile:
                        dcfile.write(str(dc))
                except FileNotFoundError:
                    print("Can't write dc file")

        # start the next timer
        self._runTimer()


if __name__ == "__main__":
    fan = PWMFan()
    fan.start()
