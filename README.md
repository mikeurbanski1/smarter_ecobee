# smarter_ecobee
When the smart device isn't smart enough.

The problem this project aims to solve is the situation where you have a comfort setting that involves two or more sensors with very different temperatures, and both locations are places where you regularly spend time. For example, in my house, my basement is routinely 10 degrees colder than the upstairs in the winter. However, I spend a lot of time down there, so I have it included in my "Home" comfort setting. Yet, I also regularly go upstairs, and the thermostat is in a large area, so both sensors generally show as "occupied" if I am downstairs.

By design, Ecobee averages the temperatures of all occupied sensors, which means in order to bring the temperature of the home back up to the desired level, it pumps the heat. The result, because of the large temperature gap, is that upstairs will be 5 degrees warmer than the set temperature, which makes it quite uncomfortable.

However, I do not want to lower the temperature of the comfort setting, because if I am only spending time upstairs, then I want it to remain at my desired temperature.

The solution, then, is to lower the desired temperature by a couple degrees only when downstairs is occupied. This results in a little bit of extra heat downstairs, but not so much that upstairs becomes a sweat lodge.

This tool uses a simple approach: every 30 minutes (configurable), it runs the following routine:

1. Get the current thermostat state.
2. Check that the current thermostat mode / comfort setting is in the configurable list (e.g., "Home" but not "Sleep").
3. Check if there is a current hold set on the thermostat.

If there is a hold:
1. Check if it's a hold we set earlier. If not, then return (don't overwrite another hold that was set manually).
2. Check if there is occupancy in any of the listed sensors. If yes, then return (the hold we set remains valid).
3. Remove the hold that we set (because we want to reset to the desired temperature for upstairs).

If there is not a hold:
1. Check occupancy. If not occupied, then return (there is nothing to do).
2. Set a temperature hold until the next Thermostat scheduled transition.

It's perfect for a raspberry pi or similar device. I have mine running on my Pi-Hole.

The app also contains the basic calls to authorize the app and obtain access tokens, available via the commands.

`python main.py -h`
`python main.py COMMAND -h`

Example flow:

`python main.py pin --api-key APP_API_KEY` - obtain a PIN to install the app for your device, and print out an auth code that can be exchanged for access tokens.

`python main.py token --auth-code AUTH_CODE` - use the auth code from the previous step to obtain access tokens.

`python main.py run --valid-modes MODE_1,MODE_2 --sensors SENSOR_1,SENSOR_2` - run the program.
