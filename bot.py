import httplib2, time, oauth, datetime, sys, socket, logging, re
from slackclient import SlackClient
from apiclient import discovery
from oauth2client import client, tools
from oauth2client.file import Storage
from slackclient import SlackClient
from os import remove, environ
from os.path import realpath, dirname
from chatterbot import ChatBot
try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None


def handle_command(command, channel, user):
    """
        Manages the commands 'who', 'when', 'why', 'where', and 'how'.
        Also responds to a list of hello_words
        No return, sends message to Slack.
    """
    command = command.lower().strip()
    if   command.startswith("who is on support")          : response = fancy_who(command.split()[4])
    elif command.startswith("who") and len(command) == 3  : response = get_todays_support_name()
    elif command.startswith("when") and len(command.split()) <= 2 : response = find_when(command.split(), user)
    elif command.startswith("all")                        : response = next_seven_days()
    elif command.startswith("swap") and len(command.split()) > 1 : response = swap(user, get_user_id(slack_client, command.split()[1]))
    elif command.startswith(("confirm", "accept"))        : response = confirm_swap(user)
    elif command.startswith(("decline", "deny"))          : response = deny_swap()
    elif command.startswith(("help", "man"))              : response = help_msg
    elif command == "how"                                 : response = how_to_support
    elif command == "where"                               : response = where_am_i
    else                                                  : response = chatbot.get_response(command).text
    logging.info("Sending response to Slack: %s" % response)
    slack_client.api_call("chat.postMessage", channel=channel, text=response, as_user=True)

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
                text = output['text'].split(("<@" + BOT_ID + ">"))
                if text[0].strip().lower() == "man":
                    return text[0].strip().lower(), output['channel'], output['user']
                return text[1].strip().lower(), output['channel'], output['user']
    return None, None, None

def get_event_list():
    # Check next week
    now = datetime.datetime.utcnow()
    now = now.isoformat() + 'Z' # 'Z' indicates UTC time
    eventsResult = service.events().list(
        calendarId=CAL_ID, timeMin=now, singleEvents=True,
        orderBy='startTime').execute()
    return eventsResult.get('items', [])

def get_todays_support_name():
    """
        Search today's events, looking for "Atmosphere Support" and return the name of the user on support.

        Returns:
            Name string
    """
    logging.info("Getting name from calendar for today")

    events = get_event_list()

    # Search through events looking for 'Atmosphere Support'
    if events:
        for event in events:
            desc = event['summary']
            # If the event matches, return the first word of summary which is name
            if "Atmosphere Support" in desc:
                return "Today's support person is %s." % ("<@" + desc.split()[0] + ">")
    return "No one is on support today."

def get_next_day(name):
    """
        Search upcoming events, looking for the specified name.

        Returns:
            Day string ("Monday", etc.)
    """
    logging.info("Getting day from calendar for user %s" % name)

    events = get_event_list()

    # Search through events
    if events:
        for event in events:
            desc = event['summary']
            if name.lower() in desc.lower() and "Atmosphere Support" in desc:
                date = datetime.datetime.strptime(event['start'].get('dateTime', event['start'].get('date')), "%Y-%m-%d")
                # Return day of week as full string
                return date.strftime("%A") + " " + date.strftime("%Y-%m-%d")
    return "not on the calendar"

def get_event(name):
    """
        Search upcoming events, looking for the specified name.

        Returns:
            Google Calendar Event ID
    """
    logging.info("Getting event ID from calendar for user %s" % name)

    events = get_event_list()

    # Search through events
    if events:
        for event in events:
            desc = event['summary']
            if name.lower() in desc.lower() and "Atmosphere Support" in desc:
                return event
    return None

def next_seven_days():
    """
        Get a list of users covering support in the next 7 days

        Returns:
            String of support users
    """
    logging.info("Getting support persons for the next week")

    events = get_event_list()

    result = ""
    num_days = 0

    if events:
        for event in events:
            desc = event['summary']
            if "Atmosphere Support" in desc and num_days < 7:
                num_days += 1
                date = datetime.datetime.strptime(event['start'].get('dateTime', event['start'].get('date')), "%Y-%m-%d")
                date = "%-9s %s" % (date.strftime("%A"), date.strftime("%Y-%m-%d"))
                name = desc.split()[0]
                result += "The support person for `%s` is %s\n" % (date, name)
    return result

def fancy_who(info):
    logging.info("Handling fancy who request: %s." % info)

    events = get_event_list()

    # Remove non-alphanumeric characters
    info = re.sub(r'\W+', '', info)

    num_days = 0
    week = []
    if events:
        for event in events:
            desc = event['summary']
            if "Atmosphere Support" in desc and num_days < 7:
                num_days += 1
                date = datetime.datetime.strptime(event['start'].get('dateTime', event['start'].get('date')), "%Y-%m-%d")
                date = "%s %s" % (date.strftime("%A"), date.strftime("%Y-%m-%d"))
                name = desc.split()[0]
                week.append("The support person for `%s` is %s\n" % (date, name))
        if "today" in info: return week[0]
        if "tomorrow" in info: return week[1]
        else:
            for day in week:
                if info in day.lower(): return day
    return "Sorry, I do not have an answer to this question."


def swap(user, user_id):
    """
        Initial step of swapping days. Creates file with both user ID's to swap

        Returns:
            String to notify user that swap is initiated
    """
    with open("%s/support-bot-swap" % dirname(realpath(__file__)), "w") as file:
        file.write(user + "\n")
        file.write(user_id + "\n")
    return "Awaiting confirmation from %s to swap with %s." % ("<@" + user_id + ">", "<@" + user + ">")

def confirm_swap(user):
    """
        Allow a swap if there is one pending and commanding user is part of the swap

        Returns:
            String to notify user of swap state
    """
    try:
        file = open("%s/support-bot-swap" % dirname(realpath(__file__)), "r")
        user_one_id = file.readline().strip()
        user_two_id = file.readline().strip()
        file.close()

        logging.info("Finished reading users from swap file: %s and %s" % (user_two_id, user_one_id))
        response = "You cannot confirm the pending swap between %s and %s" % ("<@" + user_one_id + ">", "<@" + get_user_name(slack_client, user_two_id) + ">")

        # If user sending the confirmation is the second user in swap request, swap confirmed
        if user == user_two_id:
            logging.info("Second user, %s, confirmed the swap with %s" % (user_two_id, user_one_id))
            response = "Swap with %s is confirmed." % ("<@" + user_one_id + ">")
            perform_swap(user_one_id, user_two_id)
    except IOError:
        logging.info("No pending swap requests (file not found)")
        response = "No pending swap requests."

    return response

def deny_swap():
    """
        Deny the swap and delete the file

        Returns:
            String to notify user of swap state
    """
    response = "Swap declined by user."
    try:
        remove("%s/support-bot-swap" % dirname(realpath(__file__)))
    except OSError:
        logging.info("File does not exist.")
        response = "No open swap request to decline."
    logging.info("Deleted swap file after denying swap")
    return response

def perform_swap(user_one, user_two):
    """
        After swap is confirmed, perform the swap by editing the Google Calendar

        Returns:
            None
    """
    # Get upcoming support days for each user
    user_one_event = get_event(get_user_name(slack_client, user_one))
    user_two_event = get_event(get_user_name(slack_client, user_two))

    # Swap the descriptions of the two events
    temp_summary = user_one_event['summary']
    user_one_event['summary'] = user_two_event['summary']
    user_two_event['summary'] = temp_summary

    # Update both events
    service.events().update(calendarId=CAL_ID, eventId=user_one_event['id'], body=user_one_event).execute()
    service.events().update(calendarId=CAL_ID, eventId=user_two_event['id'], body=user_two_event).execute()

    # Remove swap file
    remove("%s/support-bot-swap" % dirname(realpath(__file__)))
    logging.info("Deleted swap file after performing swap")

def find_when(name, user):
    """
        Finds the user's next support day.

        Argument 'name' is a list. It should look like ['when'] or ['when', 'username'].
        If the first word is not 'when', then ignore.
        If no username is specified after 'when', find it based off asking user's ID.
    """
    if name[0] != "when": response = "Command is not 'when'"
    elif len(name) <= 1:  response = "The next support day for %s is `%s`." % (("<@" + user + ">"), get_next_day(get_user_name(slack_client, user)))
    else: # User is asking about a different user's next day
        user_id = get_user_id(slack_client, name[1])
        if user_id: response = "The next support day for %s is `%s`." % (("<@" + user_id + ">"), get_next_day(name[1]))
        else:       response = "User %s does not seem to exist in this team." % (name[1])
    return response

def get_user_id(slack_client, name):
    """
        Gets valid user id from username.

        Returns:
            User ID of bot.
    """
    logging.info("Getting id for Slack user %s" % name)
    for user in user_list:
        if 'name' in user and user.get('name') == name:
            return user.get('id')
    return None

def get_user_name(slack_client, id):
    """
        Gets valid username from user id.

        Returns:
            Username.
    """
    logging.info("Getting username for Slack id %s" % id)
    for user in user_list:
        if 'id' in user and user.get('id') == id:
            return user.get('name')
    return None

def get_credentials():
    """
        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Credentials, the obtained credential.
    """
    logging.info("Getting Google Oauth credentials")
    credential_path = GOOGLE_APP_OAUTH_SECRET_PATH
    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(GOOGLE_APP_SECRET_PATH,
		'https://www.googleapis.com/auth/calendar')
        flow.user_agent = 'Cyverse Slack Supurt But'
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + GOOGLE_APP_OAUTH_SECRET_PATH)
    return credentials

# constants
CAL_ID = environ.get("CAL_ID")
BOT_NAME = environ.get("BOT_NAME")
BOT_ID = None
GOOGLE_APP_SECRET_PATH = environ.get("GOOGLE_APP_SECRET_PATH")
GOOGLE_APP_OAUTH_SECRET_PATH = environ.get("GOOGLE_APP_OAUTH_SECRET_PATH", ".oauth_secret_json")
BOT_USER_OAUTH_TOKEN=environ.get('BOT_USER_OAUTH_TOKEN')
SUPPORT_CHANNEL=environ.get('SUPPORT_CHANNEL', 'general')
hello_words = {'hello', 'hi', 'howdy', 'hey', 'good morning'}
slack_client = SlackClient(BOT_USER_OAUTH_TOKEN)
user_list = None

how_to_support = "http://cerberus.iplantcollaborative.org/rt/ or https://app.intercom.io/a/apps/tpwq3d9w/respond"

where_am_i = "This bot is hosted on %s in the directory `%s`.\n" \
           "You can find my code here: github.com/calvinmclean/cyverse-support-bot" \
           % (socket.getfqdn(), dirname(realpath(__file__)))

help_msg = """Ask me:
    `who` is today's support person.
    `when` is someone's next day (optional username argument)
    `where` I am hosted
    `how` you can support users
    `all` support assignments for the next 7 days
    [BETA disabled] ~`swap <username>` initiate a swap with another user that must be approved before 8am tomorrow~
    [BETA disabled] ~`deny`/`decline` if someone tried to swap with you, decline that swap~
    [BETA disabled] ~`confirm`/`accept` if someone tried to swap with you, accept that swap~
    `man`/`help` to see this message
    If you ask me something other than something here, I use github.com/gunthercox/ChatterBot to come up with a clever response"""

if __name__ == "__main__":

    logging.basicConfig(filename="%s/cyverse-support-bot.log" % dirname(realpath(__file__)),
                        filemode='a',
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        level=logging.INFO)

    # OAUTH
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    # Get list of users so it API doesn't have to be asked for list each time
    api_call = slack_client.api_call("users.list")
    if api_call.get('ok'):
        user_list = api_call.get('members')

    # Create and train chatterbot
    chatbot = ChatBot(
        'CyVerse Support Bot',
        trainer='chatterbot.trainers.ChatterBotCorpusTrainer',
        storage_adapter='chatterbot.storage.MongoDatabaseAdapter',
        database='chatterbot-database',
        filters=[
            'chatterbot.filters.RepetitiveResponseFilter'
        ],
        logic_adapters=[
            "chatterbot.logic.BestMatch",
            "chatterbot.logic.MathematicalEvaluation"
        ]
    )
    chatbot.train("chatterbot.corpus.english")

    # SLACK
    BOT_ID = get_user_id(slack_client, BOT_NAME)
    if slack_client.rtm_connect():
        while True:
            # wait to be mentioned
            command, channel, user = parse_slack_output(slack_client.rtm_read())
            if command and channel:
                handle_command(command, channel, user)

            cur_time = time.localtime()
            # or print today's support name if it is a weekday at 8am
            if cur_time.tm_wday < 5 and cur_time.tm_hour == 8 and cur_time.tm_min == 0 and cur_time.tm_sec == 0:
                try:
                    remove("%s/support-bot-swap" % dirname(realpath(__file__)))
                    logging.info("Deleted pending swap")
                except OSError:
                    logging.info("No pending swap to delete")

                handle_command("who", SUPPORT_CHANNEL, None)
                slack_client.api_call("chat.postMessage", channel=SUPPORT_CHANNEL, text="Don't forget Intercom! :slightly_smiling_face:", as_user=True)
                logging.info("Sent daily 8am message.")
            time.sleep(1)
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
