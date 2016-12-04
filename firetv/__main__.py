#!/usr/bin/env python

"""
Amazon Fire TV server

RESTful interface for communication over a network via ADB
with Amazon Fire TV devices with ADB Debugging enabled.

From https://developer.amazon.com/public/solutions/devices/fire-tv/docs/connecting-adb-over-network:

Turn on ADB Debugging:
    1. From the main (Launcher) screen, select Settings.
    2. Select System > Developer Options.
    3. Select ADB Debugging.

Find device IP:
    1. From the main (Launcher) screen, select Settings.
    2. Select System > About > Network.
"""

import argparse
import re
import logging
import yaml
from flask import Flask, jsonify, request, abort
from firetv import FireTV

MAIN_APPLICATION = Flask(__name__)
KNOWN_DEVICES = {}

VALID_DEVICE_ID = re.compile(r"^[-\w]+$")
VALID_APP_ID = re.compile(r"^[a-zA-Z][a-z\.A-Z]+$")


def is_valid_host(host):
    """ Check if host is valid.

    Performs two simple checks:
        - Has host and port separated by ':'.
        - Port is a positive digit.

    :param host: Host in <address>:<port> format.
    :returns: Valid or not.
    """
    parts = host.split(':')
    return not (len(parts) != 2 or not parts[1].isdigit())


def is_valid_device_id(device_id):
    """ Check if device identifier is valid.

    A valid device identifier contains only ascii word characters or dashes.

    :param device_id: Device identifier
    :returns: Valid or not.
    """
    return VALID_DEVICE_ID.match(device_id)

def is_valid_app_id(app_id):
    """ check if app identifier is valid.

    To restrict access a valid app is one with only a-z, A-Z, and '.'.
    It is possible to make this less restrictive using the regex above.

    :param app_id: Application identifier
    :returns: Valid or not
    """
    return VALID_APP_ID.match(app_id)

def add(device_id, host):
    """ Add a device.

    Creates FireTV instance associated with device identifier.

    :param device_id: Device identifier.
    :param host: Host in <address>:<port> format.
    :returns: Added successfully or not.
    """
    valid = is_valid_device_id(device_id) and is_valid_host(host)
    if valid:
        KNOWN_DEVICES[device_id] = FireTV(str(host))
    return valid


@MAIN_APPLICATION.route('/devices/add', methods=['POST'])
def add_device():
    """ Add a device via HTTP POST.

    POST JSON in the following format ::

        {
            "device_id": "<your_device_id>",
            "host": "<address>:<port>"
        }

    """
    req = request.get_json()
    success = False
    if 'device_id' in req and 'host' in req:
        success = add(req['device_id'], req['host'])
    return jsonify(success=success)


@MAIN_APPLICATION.route('/devices/list', methods=['GET'])
def list_devices():
    """ List devices via HTTP GET. """
    output = {}
    for device_id, device in KNOWN_DEVICES.items():
        output[device_id] = {
            'host': device.host,
            'state': device.state
        }
    return jsonify(KNOWN_DEVICES=output)


@MAIN_APPLICATION.route('/devices/state/<device_id>', methods=['GET'])
def device_state(device_id):
    """ Get device state via HTTP GET. """
    if device_id not in KNOWN_DEVICES:
        return jsonify(success=False)
    return jsonify(state=KNOWN_DEVICES[device_id].state)

@MAIN_APPLICATION.route('/devices/<device_id>/apps/running', methods=['GET'])
def running_apps(device_id):
    """ Get running apps via HTTP GET. """
    if not is_valid_device_id(device_id):
        abort(403)
    if device_id not in KNOWN_DEVICES:
        abort(404)
    return jsonify(running_apps=KNOWN_DEVICES[device_id].running_apps())

@MAIN_APPLICATION.route('/devices/<device_id>/apps/state/<app_id>', methods=['GET'])
def get_app_state(device_id, app_id):
    """ Get the state of the requested app """
    if not is_valid_app_id(app_id):
        abort(403)
    if not is_valid_device_id(device_id):
        abort(403)
    if device_id not in KNOWN_DEVICES:
        abort(404)
    return jsonify(status=KNOWN_DEVICES[device_id].app_state(app_id))

@MAIN_APPLICATION.route('/devices/action/<device_id>/<action_id>', methods=['GET'])
def device_action(device_id, action_id):
    """ Initiate device action via HTTP GET. """
    success = False
    if device_id in KNOWN_DEVICES:
        input_cmd = getattr(KNOWN_DEVICES[device_id], action_id, None)
        if callable(input_cmd):
            input_cmd()
            success = True
    return jsonify(success=success)

@MAIN_APPLICATION.route('/devices/<device_id>/apps/<app_id>/start', methods=['GET'])
def app_start(device_id, app_id):
    """ Starts an app with corresponding package name"""
    if not is_valid_app_id(app_id):
        abort(403)
    if not is_valid_device_id(device_id):
        abort(403)
    if device_id not in KNOWN_DEVICES:
        abort(404)
    KNOWN_DEVICES[device_id].launch_app(app_id + "/.Splash")
    return jsonify(success=True)

@MAIN_APPLICATION.route('/devices/<device_id>/apps/<app_id>/stop', methods=['GET'])
def app_stop(device_id, app_id):
    """ stops an app with corresponding package name"""
    if not is_valid_app_id(app_id):
        abort(403)
    if not is_valid_device_id(device_id):
        abort(403)
    if device_id not in KNOWN_DEVICES:
        abort(404)
    KNOWN_DEVICES[device_id].stop_app(app_id)
    return jsonify(success=True)

@MAIN_APPLICATION.route('/devices/connect/<device_id>', methods=['GET'])
def device_connect(device_id):
    """ Force a connection attempt via HTTP GET. """
    success = False
    if device_id in KNOWN_DEVICES:
        KNOWN_DEVICES[device_id].connect()
        success = True
    return jsonify(success=success)

def _parse_config(config_file_path):
    """ Parse Config File from yaml file. """
    config_file = open(config_file_path, 'r')
    config = yaml.load(config_file)
    config_file.close()
    return config

def _add_devices_from_config(args):
    """ Add devices from config. """
    config = _parse_config(args.config)
    logging.info('Loading configuration from: %s', args.config)
    for device in config['devices']:
        if args.default:
            if device == "default":
                raise ValueError('devicename "default" in config is not '
                                 'allowed if default param is set')
            if config['devices'][device]['host'] == args.default:
                raise ValueError('host set in default param must not be defined in config')
        logging.info('Adding device: %s', device)
        add(device, config['devices'][device]['host'])

def main():
    """ Set up the server. """
    parser = argparse.ArgumentParser(description='AFTV Server')
    parser.add_argument('-p', '--port', type=int, help='Listen port', default=5556)
    parser.add_argument('-d', '--default', help='Default Amazon Fire TV host', nargs='?')
    parser.add_argument('-c', '--config', type=str, help='Path to config file')
    parser.add_argument('-v', '--verbose', help='Enable verbose logging',
                        action="store_true")
    args = parser.parse_args()

    if args.default and not add('default', args.default):
        exit('invalid hostname')

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        logging.info('Verbose logging enabled')

    if args.config:
        _add_devices_from_config(args)

    MAIN_APPLICATION.run(host='0.0.0.0', port=args.port)


if __name__ == '__main__':
    main()
