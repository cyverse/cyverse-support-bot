import httplib2, os, time, oauth, datetime, sys, socket
from slackclient import SlackClient
from apiclient import discovery
from oauth2client import client, tools
from oauth2client.file import Storage
from slackclient import SlackClient
try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

def parse_slack_output(slack_rtm_output):
    """
        The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.
    """
    output_list = slack_rtm_output

    if output_list and len(output_list) > 0:
        for output in output_list:
            if output and 'text' in output and ("<@" + BOT_ID + ">") in output['text']:
                # return text after the @ mention, whitespace removed
                return output['text'].split(("<@" + BOT_ID + ">"))[1].strip().lower(), \
                       output['channel']
    return None, None

# Get the name for the person doing support on today day
def get_name_from_cal():
    """
        Search today's events, looking for "Atmosphere Support".

        Returns:
            Name string
    """
    # Check next 24 hours
    now = datetime.datetime.utcnow()
    later = now + datetime.timedelta(hours=23)
    now = now.isoformat() + 'Z' # 'Z' indicates UTC time
    later = later.isoformat() + 'Z'
    eventsResult = service.events().list(
        calendarId=CAL_ID, timeMin=now, timeMax=later, singleEvents=True,
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    # Search through events looking for 'Atmosphere Support'
    if events:
        for event in events:
            desc = event['summary']
            # If the event matches, return the first word of summary which is name
            if "Atmosphere Support" in desc:
                return desc.split()[0]
    return "no one is on support today"

def get_day_from_cal(name):
    """
        Search upcoming events, looking for the specified name.

        Returns:
            Day string ("Monday", etc.)
    """
    # Check next week
    now = datetime.datetime.utcnow()
    now = now.isoformat() + 'Z' # 'Z' indicates UTC time
    eventsResult = service.events().list(
        calendarId=CAL_ID, timeMin=now, singleEvents=True,
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    # Search through events
    if events:
        for event in events:
            desc = event['summary']
            if name.lower() in desc.lower() and "Atmosphere Support" in desc:
                date = datetime.datetime.strptime(event['start'].get('dateTime', event['start'].get('date')), "%Y-%m-%d")
                # Return day of week as full string
                return date.strftime("%A") + " " + date.strftime("%d/%m/%Y")
    return "not on the calendar"

def handle_command(command, channel):
    """
        Manages the commands 'who', 'when', 'why' and 'how'
        No return, sends message to Slack.
    """
    # who - get today's support person
    if command.lower() == "who":
        name = get_name_from_cal()
        response = "Today's support person is @%s." % (name)
    # when - find next day for specified user
    elif command.startswith("when"):
        if len(command.split()) <= 1:
            response = "In order to use the `when` command, specify a user"
        else:
            name = command.split()[1]
            day = get_day_from_cal(name)
            response = "The next support day for @%s is %s." % (name, day)
    # why - bc our users are great
    elif command.lower() == "why":
        response = "because we love our users!"
    # where - find where this is hosted
    elif command.lower() == "where":
        response = "This bot is hosted on %s in the directory %s.\nYou can find my code here: %s." % (socket.getfqdn(), os.getcwd(), "https://github.com/calvinmclean/cyverse-support-bot")
    # how - links to support sites
    elif command.lower() == "how":
        response = "%s or %s" % ("http://cerberus.iplantcollaborative.org/rt/", "https://app.intercom.io/a/apps/tpwq3d9w/respond")
    # Otherwise, usage help
    else:
        response = "Ask me:\n  `who` is today's support person.\n  `when` is someone's next day\n  `where` I am hosted\n  `how` you can support users\n  `why`"
    slack_client.api_call("chat.postMessage", channel=channel, text=response, as_user=True)

def get_credentials():
    """
        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Credentials, the obtained credential.
    """
    credential_path = GOOGLE_APP_OAUTH_SECRET_PATH
    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(GOOGLE_APP_SECRET_PATH,
		'https://www.googleapis.com/auth/calendar.readonly')
        flow.user_agent = 'Cyverse Slack Supurt But'
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + GOOGLE_APP_OAUTH_SECRET_PATH)
    return credentials

def get_bot_id(slack_client, bot_name):
    """
        Gets valid user id from user name.

        Returns:
            User ID of bot.
    """
    api_call = slack_client.api_call("users.list")
    if api_call.get('ok'):
        # retrieve all users so we can find our bot
        users = api_call.get('members')
        for user in users:
            if 'name' in user and user.get('name') == bot_name:
                return user.get('id')
    return None

# constants
CAL_ID = os.environ.get("CAL_ID")
BOT_NAME = os.environ.get("BOT_NAME")
BOT_ID = None
GOOGLE_APP_SECRET_PATH = os.environ.get("GOOGLE_APP_SECRET_PATH")
GOOGLE_APP_OAUTH_SECRET_PATH = os.environ.get("GOOGLE_APP_OAUTH_SECRET_PATH", ".oauth_secret_json")
BOT_USER_OAUTH_TOKEN=os.environ.get('BOT_USER_OAUTH_TOKEN')
SUPPORT_CHANNEL=os.environ.get('SUPPORT_CHANNEL', 'general')

if __name__ == "__main__":

    # OAUTH
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    # SLACK
    slack_client = SlackClient(BOT_USER_OAUTH_TOKEN)
    BOT_ID = get_bot_id(slack_client, BOT_NAME)
    if slack_client.rtm_connect():
        while True:
            # wait to be mentioned
            command, channel = parse_slack_output(slack_client.rtm_read())
            if command and channel:
                handle_command(command, channel)

            cur_time = time.localtime()
            # or print today's support name if it is a weekday at 8am
            if cur_time.tm_wday < 5 and cur_time.tm_hour == 8 and cur_time.tm_min == 0 and cur_time.tm_sec == 0:
                handle_command("who", SUPPORT_CHANNEL)
            time.sleep(1)
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
