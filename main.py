import datetime
import logging.handlers
import time
import argparse
import os
import requests
import json

from selection import Selection


os.makedirs('logs', exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

handler = logging.handlers.RotatingFileHandler('logs/ecobee.log', maxBytes=1024 * 1024 * 10, backupCount=5)
handler.setFormatter(formatter)
logger.addHandler(handler)

token = {}
last_hold = {}


def dumps(o, indent=None):
    return json.dumps(o, indent=indent, cls=DateTimeEncoder)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')

        return json.JSONEncoder.default(self, o)


def get_api_key():
    with open('api_key.txt', 'r') as fp:
        api_key = fp.read().strip()
    return api_key


def run(args):

    log_stdout = args.log_stdout

    if log_stdout:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.info('Entered run method')

    heat = args.heat
    sleep_duration = args.sleep_duration
    modes_to_check = [m.strip() for m in args.valid_modes.split(',')]
    sensors_to_check = [s.strip() for s in args.sensors.split(',')]
    dry_run = args.dry_run

    for arg, val in args.__dict__.items():
        logger.info(f'{arg}: {val}')

    api_key = get_api_key()
    logger.info(f'Read API key: {api_key}')

    read_last_hold()
    logger.info('Got last hold:')
    logger.info(dumps(last_hold, indent=2))

    read_token()
    logger.info('Got token:')
    logger.info(dumps(token, indent=2))

    while True:
        logger.info('Beginning iteration')

        try:
            thermostat = get_thermostat(api_key)
            if thermostat:
                logger.info('Thermostat:')
                logger.info(dumps(thermostat, indent=2))
                check_setting(thermostat, heat, modes_to_check, sensors_to_check, dry_run)

        except Exception as e:
            logger.error('An error occurred getting or updating the thermostat. Continuing after next sleep', exc_info=True)

        if dry_run:
            return

        logger.info(f'Sleeping for {sleep_duration} minutes')
        time.sleep(sleep_duration * 60)
        logger.info('Woke up from sleep')


def read_token():
    global token
    with open('token.json', 'r') as fp:
        token = json.load(fp)


def read_last_hold():
    global last_hold
    if os.path.exists('last_hold.json'):
        with open('last_hold.json', 'r') as fp:
            last_hold = json.load(fp)

        if 'time' in last_hold:
            last_hold['time'] = datetime.datetime.strptime(last_hold['time'], '%Y-%m-%d %H:%M:%S')
    else:
        return {}


def write_last_hold():
    with open('last_hold.json', 'w') as fp:
        fp.write(dumps(last_hold, indent=2))


def check_setting(thermostat, heat_setting, modes_to_check, sensors_to_check, dry_run):
    """The flow is:

    1. Check that the current mode is in the list
    2. Check if there is a current hold on the thermostat.

    If there is a hold:
    3. Check if it's a hold we set earlier. If not, then return (don't overwrite another hold).
    4. Check if there is occupancy. If yes, then return (the hold we set remains valid).
    5. Remove the hold that we set.

    If there is not a hold:
    3. Check occupancy. If not occupied, then return (there is nothing to do).
    4. Set the hold.

    """
    current_climate = get_current_mode(thermostat)

    logger.info(f"Is manual hold: {current_climate['isManualHold']}")

    if current_climate['name'] not in modes_to_check:
        print(f'Current mode is {current_climate["name"]}, so there is nothing to do.')
        return

    occupied = check_occupancy(thermostat, sensors_to_check)
    logger.info(f'Sensor occupied: {occupied}')

    current_hold = get_current_hold(thermostat, current_climate)

    if current_hold:
        logger.info('Current hold:')
        logger.info(dumps(current_hold, indent=2))

        set_by_me = hold_set_by_me(current_hold)
        logger.info(f'Hold set by me: {set_by_me}')

        if not set_by_me:
            logger.info('Hold not set by me; returning without removing it')
            return

        if occupied:
            logger.info('Sensor is occupied; returning without removing the hold')
            return

        if not dry_run:
            logger.info('Removing hold')
            remove_hold()
        else:
            logger.info('--dry-run was set, so not actually removing the hold')
    else:
        logger.info('No current hold found')

        if not occupied:
            logger.info('Sensor is not occupied; returning without setting a hold')
            return

        if not dry_run:
            logger.info('Setting hold')
            set_hold(heat_setting, thermostat['runtime']['desiredCool'])
        else:
            logger.info('--dry-run was set, so not actually setting the hold')


def check_occupancy(thermostat, sensors_to_check):
    sensors = [s for s in thermostat['remoteSensors'] if s['name'] in sensors_to_check]
    for sensor in sensors:
        occupancy = next(o for o in sensor['capability'] if o['type'] == 'occupancy')
        if not occupancy:
            continue
        if occupancy['value'].lower() == 'true':
            logger.debug(f'Sensor {sensor["name"]} is occupied')
            return True

    logger.debug('No sensors we care about are occupied')
    return False


def get_current_hold(thermostat, current_climate):
    if not current_climate["isManualHold"]:
        return None

    last_event = thermostat['events'][0] if thermostat['events'] else None
    if not last_event:
        logger.debug('No event found')
    if last_event and last_event.get('type') != 'hold':
        logger.debug('Event found, but it is not a hold')

    return last_event if last_event and last_event.get('type') == 'hold' else None


def hold_set_by_me(hold_event):
    if not last_hold:
        return False

    event_heat = hold_event['heatHoldTemp']
    event_cool = hold_event['coolHoldTemp']
    event_time = datetime.datetime.strptime(hold_event['startDate'] + ' ' + hold_event['startTime'], '%Y-%m-%d %H:%M:%S')

    if last_hold.get('heat') != event_heat or last_hold.get('cool') != event_cool:
        logger.debug('The temperatures on the current hold do not match what we sent')
        return False
    last_hold_time = last_hold['time']
    if last_hold_time > event_time and (last_hold_time - event_time).seconds > 60 \
            or last_hold_time < event_time and (event_time - last_hold_time).seconds > 60:
        logger.debug('The current hold time does not match what we sent')
        return False

    logger.debug(f'Hold appears to have been set by me')
    return True


def get_current_mode(thermostat):
    current_mode = thermostat['program']['currentClimateRef']
    logger.debug(f'Current mode: {current_mode}')

    climates = thermostat['program']['climates']

    mode_climate = next(c for c in climates if c['climateRef'] == current_mode)
    climate_heat = mode_climate['heatTemp']
    climate_cool = mode_climate['coolTemp']

    runtime = thermostat['runtime']
    desired_heat = runtime['desiredHeat']
    desired_cool = runtime['desiredCool']
    mode_climate['isManualHold'] = desired_heat != climate_heat or desired_cool != climate_cool

    return mode_climate


def set_hold(heat, cool):
    s = Selection()
    req_body = {
        'selection': s.get_selection(),
        'functions': [
            {
                'type': 'setHold',
                'params': {
                    'heatHoldTemp': heat,
                    'coolHoldTemp': cool,
                    'holdType': 'nextTransition'
                }
            }
        ]
    }

    headers = {
        'Authorization': f'Bearer ${token["access_token"]}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    # no fucking idea why this API is what it is
    logger.info('Submitting request to set hold')
    resp = requests.request('POST', f'https://www.ecobee.com/home//api/1/thermostat?json=true&token={token["access_token"]}', headers=headers, json=req_body)
    logger.debug(resp.content)
    logger.info(f'Return code: {resp.status_code}')
    if resp.status_code != 200:
        logger.error('The request failed')
        return
    resp_obj = json.loads(resp.content)
    logger.debug(dumps(resp_obj, indent=2))

    global last_hold
    last_hold = {
        'heat': heat,
        'cool': cool,
        'time': datetime.datetime.now()
    }
    write_last_hold()


def remove_hold():
    s = Selection()
    req_body = {
        'selection': s.get_selection(),
        'functions': [
            {
                'type': 'resumeProgram',
                'params': {
                    'resumeAll': True,
                }
            }
        ]
    }

    headers = {
        'Authorization': f'Bearer ${token["access_token"]}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    logger.info('Submitting request to remove hold')
    # no fucking idea why this API is what it is
    resp = requests.request('POST', f'https://www.ecobee.com/home//api/1/thermostat?json=true&token={token["access_token"]}', headers=headers, json=req_body)
    logger.debug(resp.content)
    logger.info(f'Return code: {resp.status_code}')
    if resp.status_code != 200:
        logger.error('The request failed')
        return
    resp_obj = json.loads(resp.content)
    logger.debug(dumps(resp_obj, indent=2))

    global last_hold
    last_hold = {}
    write_last_hold()


def get_thermostat(api_key):
    s = Selection(includeRuntime=True,
                  includeExtendedRuntime=False,
                  includeProgram=True,
                  includeSensors=True,
                  includeSettings=False,
                  includeEvents=True)

    req_body = {
        'selection': s.get_selection()
    }

    params = {
        'json': dumps(req_body),
        'token': token['access_token']
    }

    headers = {
        'Authorization': f'Bearer ${token["access_token"]}',
        'Accept': 'application/json'
    }

    logger.info('Submitting get thermostat request')
    resp = requests.request('GET', 'https://api.ecobee.com/1/thermostat', params=params, headers=headers)
    logger.debug(resp.content)
    logger.info(f'Return code: {resp.status_code}')

    resp_obj = json.loads(resp.content)
    logger.debug(dumps(resp_obj, indent=2))

    if 'status' in resp_obj and 'code' in resp_obj['status'] and resp_obj['status']['code'] == 14:
        logger.info('Token was expired; refreshing and retrying')
        refresh_token(api_key)
        return get_thermostat(api_key)
    elif resp.status_code != 200:
        logger.error(f'Failed to get thermostat (and the error was not the refresh token)')
        return None

    return resp_obj['thermostatList'][0]


def refresh_token(api_key):
    global token
    params = {
        'refresh_token': token['refresh_token'],
        'client_id': api_key,
        'grant_type': 'refresh_token'
    }

    logger.info('Submitting request to refresh token')
    resp = requests.request('POST', 'https://api.ecobee.com/token', params=params)
    logger.debug(resp.content)
    logger.info(f'Return code: {resp.status_code}')
    token = json.loads(resp.content)
    logger.debug(dumps(token, indent=2))

    with open('token.json', 'w') as fp:
        fp.write(dumps(token, indent=2))


def get_token(args):
    api_key = args.api_key
    auth_code = args.auth_code

    if not api_key:
        with open('api_key.txt', 'r') as fp:
            api_key = fp.read().strip()

    global token
    params = {
        'code': auth_code,
        'client_id': api_key,
        'grant_type': 'ecobeePin'
    }

    resp = requests.request('POST', 'https://api.ecobee.com/token', params=params)
    token = json.loads(resp.content)

    print(resp.status_code)
    print(token)

    with open('api_key.txt', 'w') as fp:
        fp.write(api_key)

    with open('code.txt', 'w') as fp:
        fp.write(auth_code)

    with open('token.json', 'w') as fp:
        fp.write(dumps(token, indent=2))


def status(args):
    api_key = get_api_key()
    read_token()
    thermostat = get_thermostat(api_key)
    print(json.dumps(thermostat, indent=2))


def get_pin(args):
    api_key = args.api_key
    params = {
        'response_type': 'ecobeePin',
        'scope': 'smartWrite',
        'client_id': api_key
    }
    resp = requests.request('GET', 'https://api.ecobee.com/authorize', params=params)
    resp_body = json.loads(resp.content)
    print(resp_body)

    with open('api_key.txt', 'w') as fp:
        fp.write(api_key)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Make ecobee smarter [again].')
    subparsers = parser.add_subparsers(title='mode', dest='mode')
    subparsers.required = True

    pin_parser = subparsers.add_parser('pin', help='Obtain a PIN and auth code for app installation. This also saves the passed API key into api_key.txt.')
    pin_parser.add_argument('--api-key', help='The application API key', required=True)
    pin_parser.set_defaults(func=get_pin)

    token_parser = subparsers.add_parser('token', help='Obtain auth and refresh tokens, saving the result to token.json. This also saves the passed code to code.txt.')
    token_parser.add_argument('--api-key', help='The application API key. If omitted, read it from the api_key.txt file.')
    token_parser.add_argument('--auth-code', help='The authorization code returned with the PIN', required=True)
    token_parser.set_defaults(func=get_token)

    run_parser = subparsers.add_parser('run', help='Run the actual program.')
    run_parser.add_argument('--log-stdout', action='store_true',
                            help='Whether to log to stdout in addition to the log file. Only applies to "run" mode, because the other modes are interactive.')
    run_parser.add_argument('--heat', default=680, type=int,
                            help='The heat setting to use, in ecobee units (e.g., 70 degrees = 700). Default: 680')
    run_parser.add_argument('--sleep-duration', default=30, type=int,
                            help='The length of the sleep between runs, in minutes. Default: 30')
    run_parser.add_argument('--valid-modes', required=True,
                            help='A comma-separated list of thermostat comfort settings to process; if the current comfort setting is not one of these, then the program will not do anything.')
    run_parser.add_argument('--sensors', required=True,
                            help='A comma-separated list of sensors to check for occupancy - this should be the room(s) that dictate whether the adjusted setting will be used.')
    run_parser.add_argument('--dry-run', action='store_true',
                            help='Do not actually change the mode, just log what would have happened.')
    run_parser.set_defaults(func=run)

    status_parser = subparsers.add_parser('status', help='Get the thermostat status and return. Prints to stdout.')
    status_parser.set_defaults(func=status)

    args = parser.parse_args()
    args.func(args)
