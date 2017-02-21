#!/usr/bin/env python

"""
Communicate with an Amazon Fire TV device via ADB over a network.

ADB Debugging must be enabled.
"""

import errno
import logging
import re
from socket import error as socket_error
from adb import adb_commands
from adb.adb_protocol import InvalidChecksumError

# Matches window windows output for app & activity name gathering
WINDOW_REGEX = re.compile("Window\{(?P<id>.+?) (?P<user>.+) (?P<package>.+?)(?:\/(?P<activity>.+?))?\}$", re.MULTILINE)

# ADB key event codes.
HOME = 3
VOLUME_UP = 24
VOLUME_DOWN = 25
POWER = 26
PLAY_PAUSE = 85
NEXT = 87
PREVIOUS = 88
PLAY = 126
PAUSE = 127
UP = 19
DOWN = 20
LEFT = 21
RIGHT = 22
ENTER = 66
BACK = 4
MENU = 1

# Fire TV states.
STATE_ON = 'on'
STATE_IDLE = 'idle'
STATE_OFF = 'off'
STATE_PLAYING = 'play'
STATE_PAUSED = 'pause'
STATE_STANDBY = 'standby'
STATE_DISCONNECTED = 'disconnected'

PACKAGE_LAUNCHER = "com.amazon.tv.launcher"
INTENT_LAUNCH = "android.intent.category.LAUNCHER"
INTENT_HOME = "android.intent.category.HOME"


class FireTV:
    """ Represents an Amazon Fire TV device. """

    def __init__(self, host):
        """ Initialize FireTV object.

        :param host: Host in format <address>:port.
        """
        self.host = host
        self._adb = None
        self.connect()

    def connect(self):
        """ Connect to an Amazon Fire TV device.

        Will attempt to establish ADB connection to the given host.
        Failure sets state to DISCONNECTED and disables sending actions.
        """
        logging.debug('Connecting to device "%s"', self.host)
        try:
            self._adb = adb_commands.AdbCommands.ConnectDevice(
                serial=self.host)
            logging.debug('ADB Connection sucessful')
        except socket_error as serr:
            if serr.errno != errno.ECONNREFUSED:
                logging.debug('Socket error')
                raise serr
        except ValueError as adb_value_error:
            if "'Unable to unpack ADB command.', '<6I'," in str(adb_value_error):
                logging.error('Reboot "%s" Fire TV, it has multiple ADB connections.', self.host)
            else:
                raise adb_value_error


    @property
    def state(self):
        """ Compute and return the device state.

        :returns: Device state.
        """
        # Check if device is disconnected.
        if not self._adb:
            return STATE_DISCONNECTED
        # Check if device is off.
        if not self._screen_on:
            return STATE_OFF
        # Check if screen saver is on.
        if not self._awake:
            return STATE_IDLE
        # Check if the launcher is active.
        if self._launcher:
            return STATE_STANDBY
        # Check for a wake lock (device is playing).
        if self._wake_lock:
            return STATE_PLAYING
        # Otherwise, device is paused.
        return STATE_PAUSED

    def running_apps(self):
        """ Return an array of running user applications """
        return self._ps('u0_a')

    def app_state(self, app):
        """ Informs if application is running """
        if self.state == STATE_OFF or self.state == STATE_DISCONNECTED:
            return STATE_OFF
        if self.current_app["package"] == app:
            return STATE_ON
        return STATE_OFF

    def turn_on(self):
        """ Send power action if device is off. """
        if self.state == STATE_OFF:
            self._power()

    def turn_off(self):
        """ Send power action if device is not off. """
        if self.state != STATE_OFF:
            self._power()

    def home(self):
        """ Send home action. """
        self._key(HOME)

    def up(self):
        """ Send up action. """
        self._key(UP)

    def down(self):
        """ Send down action. """
        self._key(DOWN)

    def left(self):
        """ Send left action. """
        self._key(LEFT)

    def right(self):
        """ Send right action. """
        self._key(RIGHT)

    def enter(self):
        """ Send enter action. """
        self._key(ENTER)

    def back(self):
        """ Send back action. """
        self._key(BACK)

    def menu(self):
        """ Send menu action. """
        self._key(MENU)

    def volume_up(self):
        """ Send volume up action. """
        self._key(VOLUME_UP)

    def volume_down(self):
        """ Send volume down action. """
        self._key(VOLUME_DOWN)

    def media_play_pause(self):
        """ Send media play/pause action. """
        self._key(PLAY_PAUSE)

    def media_play(self):
        """ Send media play action. """
        self._key(PLAY)

    def media_pause(self):
        """ Send media pause action. """
        self._key(PAUSE)

    def media_next(self):
        """ Send media next action (results in fast-forward). """
        self._key(NEXT)

    def media_previous(self):
        """ Send media previous action (results in rewind). """
        self._key(PREVIOUS)

    def _send_intent(self, pkg, intent, count=1):
        if not self._adb:
            return None

        cmd = 'monkey -p {} -c {} {}; echo $?'.format(pkg, intent, count)
        logging.debug("Sending an intent %s to %s (count: %s)", intent, pkg, count)

        # adb shell outputs in weird format, so we cut it into lines,
        # separate the retcode and return info to the user
        res = self._adb.Shell(cmd).strip().split("\r\n")
        retcode = res[-1]
        output = "\n".join(res[:-1])

        return {"retcode": retcode, "output": output}

    def launch_app(self, app):
        """ Launch the specified app on the Fire TV """
        if not self._adb:
            return None

        return self._send_intent(app, INTENT_LAUNCH)

    def stop_app(self, app):
        """ Stop the specified app on the Fire TV """
        if not self._adb:
            return None
        logging.debug('Stopping "%s" by going home.', app)
        return self._send_intent(PACKAGE_LAUNCHER, INTENT_HOME)

    @property
    def current_app(self):
        """ Get the current running app on the Fire TV """
        current_focus = self._dump("window windows", "mCurrentFocus").replace("\r", "")

        #logging.error("Current: %s", current_focus)
        #mCurrentFocus = Window{299091cd u0 com.netflix.ninja / com.netflix.ninja.MainActivity}

        matches = WINDOW_REGEX.search(current_focus)
        if matches:
            (pkg, activity) = matches.group('package', 'activity')
            return {"package": pkg, "activity": activity}
        else:
            logging.warning("Couldn't get current app, reply was %s", current_focus)
            return None

    @property
    def _screen_on(self):
        """ Check if the screen is on. """
        return self._dump_has('power', 'Display Power', 'state=ON')

    @property
    def _awake(self):
        """ Check if the device is awake (screen saver is not running). """
        return self._dump_has('power', 'mWakefulness', 'Awake')

    @property
    def _wake_lock(self):
        """ Check for wake locks (device is playing). """
        return not self._dump_has('power', 'Locks', 'size=0')

    @property
    def _launcher(self):
        """ Check if the active application is the Amazon TV launcher. """
        return self.current_app["package"] == PACKAGE_LAUNCHER

    def _power(self):
        """ Send power action. """
        self._key(POWER)

    def _input(self, cmd):
        """ Send input to the device.

        :param cmd: Input command.
        """
        if not self._adb:
            return
        self._adb.Shell('input {0}'.format(cmd))

    def _key(self, key):
        """ Send a key event to device.

        :param key: Key constant.
        """
        self._input('keyevent {0}'.format(key))

    def _dump(self, service, grep=None):
        """ Perform a service dump.

        :param service: Service to dump.
        :param grep: Grep for this string.
        :returns: Dump, optionally grepped.
        """
        if not self._adb:
            return
        if grep:
            return self._adb.Shell('dumpsys {0} | grep "{1}"'.format(service, grep))
        return self._adb.Shell('dumpsys {0}'.format(service))

    def _dump_has(self, service, grep, search):
        """ Check if a dump has particular content.

        :param service: Service to dump.
        :param grep: Grep for this string.
        :param search: Check for this substring.
        :returns: Found or not.
        """
        return self._dump(service, grep=grep).strip().find(search) > -1

    def _ps(self, search=''):
        """ Perform a ps command with optional filtering.

        :param search: Check for this substring.
        :returns: List of matching fields
        """
        if not self._adb:
            return
        result = []
        processes = self._adb.StreamingShell('ps')
        try:
            for bad_line in processes:
                # The splitting of the StreamingShell doesn't always work
                # this is to ensure that we get only one line
                for line in bad_line.splitlines():
                    if search in line:
                        result.append(line.strip().rsplit(' ', 1)[-1])
            return result
        except InvalidChecksumError as bad_checksum:
            print(bad_checksum)
            self.connect()
            raise IOError
