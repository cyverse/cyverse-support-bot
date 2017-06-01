import httplib2
import os
import time
import oauth
import datetime
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

# starterbot's ID as an environment variable
BOT_ID = os.environ.get("BOT_ID")

# constants
AT_BOT = "<@" + BOT_ID + ">"
SUPPORT_CHANNEL = "general"
CAL_ID = ""

slack_client = SlackClient(os.environ.get('SLACK_BOT_TOKEN'))

def parse_slack_output(slack_rtm_output):
    """
        The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.
    """
    output_list = slack_rtm_output
    if output_list and len(output_list) > 0:
        for output in output_list:
            if output and 'text' in output and AT_BOT in output['text']:
                # return text after the @ mention, whitespace removed
                return output['text'].split(AT_BOT)[1].strip(), \
                       output['channel']
    return None, None

# Get the name for the person doing support on today day
def get_name_from_cal():
    # Get 10 events
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    eventsResult = service.events().list(
        calendarId=CAL_ID, timeMin=now, maxResults=10, singleEvents=True,
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
    # Get 7 events
    now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    eventsResult = service.events().list(
        calendarId=CAL_ID, timeMin=now, maxResults=7, singleEvents=True,
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    # Search through events
    if events:
        for event in events:
            desc = event['summary']
            if name.lower() in desc.lower() and "Atmosphere Support" in desc:
                # Return day of week as full string
                return datetime.datetime.strptime(event['start'].get('dateTime', event['start'].get('date')), "%Y-%m-%d").strftime("%A")
    return "not on the calendar"

def handle_command(command, channel):
    if command.startswith("who"):
        name = get_name_from_cal()
        response = "Today's support person is %s." % (name)
    elif command.startswith("when"):
        if len(command.split()) <= 1:
            response = "In order to use the `when` command, specify a user"
        else:
            name = command.split()[1]
            day = get_day_from_cal(name)
            response = "The next support day for %s is %s." % (name, day)
    elif command.startswith("why"):
        response = "because we love our users!"
    elif command.startswith("how"):
        response = "%s or %s" % ("http://cerberus.iplantcollaborative.org/rt/", "https://app.intercom.io/a/apps/tpwq3d9w/respond")
    else:
        response = "Ask me: `who`, `when`, `why`, or `how`."
    slack_client.api_call("chat.postMessage", channel=channel, text=response + " :party-parrot:", as_user=True)

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-python-quickstart.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

sevice=None

if __name__ == "__main__":
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    if slack_client.rtm_connect():
        while True:
            command, channel = parse_slack_output(slack_client.rtm_read())
            if command and channel:
                handle_command(command, channel)

            cur_time = time.localtime()
            # Only print today's support name if it is a weekday at 8am
            if cur_time.tm_wday < 5 and cur_time.tm_hour == 8 and cur_time.tm_min == 0 and cur_time.tm_sec == 0:
                handle_command("who", SUPPORT_CHANNEL)
            time.sleep(1)
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
