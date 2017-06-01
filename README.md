# cyverse-support-bot

This is a Slack bot that will notify users if it is their day for support. In order to do this, it accesses Google Calendars and parses events. Every weekday morning at 8am, the bot will post in a channel the name of today's support person.

Also, the bot can be talked to using the commands `who`, `when`, `why`, and `how`.

`who` - prints the name of the user in charge of support today.

`when` - requires a parameter that is the name. The bot checks upcoming events and prints out when the specified user's next support day is.

`how` - prints links to our support sites.

`why` - tells you why.

### Usage

1. Clone repository

  `git clone https://github.com/calvinmclean/cyverse-support-bot.git`

2. Install dependencies

  `pip install -r requirements.txt`

3. Make sure environment variables are defined
  ```
  export BOT_NAME='<name of slack bot>'
  export CAL_ID='<id of google calendar>'
  export GOOGLE_APP_SECRET_PATH='<path to secrets json file>'
  export BOT_USER_OAUTH_TOKEN='<slack bot oauth token>'
  export SUPPORT_CHANNEL='<slack channel for support updates>'
  ```

4. Run the bot!

  `python bot.py --noauth_local_webserver` or `python bot.py --noauth_local_webserver &` to run in the background
