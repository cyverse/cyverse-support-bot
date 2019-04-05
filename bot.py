import httplib2, time, oauth, sys, socket, logging, re
from datetime import datetime as dt
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


class AtmoSupportBot:
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
        `man`/`help` to see this message
        If you ask me something other than something here, I use github.com/gunthercox/ChatterBot to come up with a clever response"""

    hello_words = {'hello', 'hi', 'howdy', 'hey', 'good morning'}

    def __init__(self, cal_id, bot_name, google_app_secret_path, google_app_oauth_secret_path,
                 bot_user_oauth_token, support_channel):
        self.CAL_ID = cal_id
        self.BOT_NAME = bot_name
        self.GOOGLE_APP_SECRET_PATH = google_app_secret_path
        self.GOOGLE_APP_OAUTH_SECRET_PATH = google_app_oauth_secret_path
        self.BOT_USER_OAUTH_TOKEN = bot_user_oauth_token
        self.SUPPORT_CHANNEL = support_channel
        self.slack_client = SlackClient(self.BOT_USER_OAUTH_TOKEN)
        # Create and train chatterbot
        self.chatbot = ChatBot(
            'CyVerse Support Bot',
            trainer='chatterbot.trainers.ChatterBotCorpusTrainer',
            storage_adapter='chatterbot.storage.MongoDatabaseAdapter',
            database='chatterbot-database',
            filters=['chatterbot.filters.RepetitiveResponseFilter'],
            logic_adapters=[
                "chatterbot.logic.BestMatch",
                "chatterbot.logic.MathematicalEvaluation"
            ])
        self.chatbot.train("chatterbot.corpus.english")

        # OAUTH
        credentials = self.get_credentials()
        http = credentials.authorize(httplib2.Http())
        self.service = discovery.build('calendar', 'v3', http=http)

        # Get list of users so it API doesn't have to be asked for list each time
        api_call = self.slack_client.api_call("users.list")
        if api_call.get('ok'):
            self.user_list = api_call.get('members')
        self.BOT_ID = self.get_user_name_or_id(self.BOT_NAME)


    def handle_command(self, command, channel, user, thread_ts=None):
        """
            Manages the commands 'who', 'when', 'why', 'where', and 'how'.
            Also responds to a list of hello_words
            No return, sends message to Slack.
        """
        command = command.lower().strip()
        if command[-1] == '?':
            command = command[0:-1]

        if command.startswith("who is on support"):
            response = self.fancy_who(command.split()[4])
        elif command.startswith("who") and len(command) == 3:
            response = self.get_todays_support_name()
        elif command.startswith("when") and len(command.split()) <= 2:
            response = self.find_when(command.split(), user)
        elif command.startswith("all"):
            response = self.next_seven_days()
        elif command.startswith(("help", "man")):
            response = self.help_msg
        elif command == "how":
            response = self.how_to_support
        elif command == "where":
            response = self.where_am_i
        else:
            response = self.chatbot.get_response(command).text
        logging.info("Sending response to Slack: %s" % response)
        if thread_ts:
            self.slack_client.api_call(
                "chat.postMessage", channel=channel, text=response, as_user=True, thread_ts=thread_ts)
        else:
            self.slack_client.api_call(
                "chat.postMessage", channel=channel, text=response, as_user=True)


    def read_and_respond(self):
        """
            The Slack Real Time Messaging API is an events firehose. This parsing
            function checks if a message is directed at the bot and then extracts
            the specific command from the message
        """
        output_list = self.slack_client.rtm_read()
        command, channel, user, thread_ts = None, None, None, None

        if output_list:
            for output in output_list:
                if output and 'text' in output and (
                        "<@" + self.BOT_ID + ">") in output['text']:
                    # check if message is in a thread
                    if 'thread_ts' in output:
                        thread_ts = output['thread_ts']
                    # return text after the @ mention, whitespace removed
                    text = [t.strip().lower() for t in output['text'].split("<@" + self.BOT_ID + ">")]
                    # allow users to say 'man @atmosupportbot' like CLI man
                    channel, user = output['channel'], output['user']
                    command = text[0] if text[0] == "man" else text[1]
        if command and channel:
            self.handle_command(command, channel, user, thread_ts=thread_ts)


    def morning_message(self):
        """
            Send a message to the channel announcing today's support person if it is
            8 am
        """
        cur_time = time.localtime()
        if cur_time.tm_wday < 5 and cur_time.tm_hour == 8 and cur_time.tm_min == 0 and cur_time.tm_sec == 0:
            self.handle_command("who", self.SUPPORT_CHANNEL, None)
            self.slack_client.api_call(
                "chat.postMessage",
                channel=self.SUPPORT_CHANNEL,
                text="Don't forget Intercom! :slightly_smiling_face:",
                as_user=True)
            logging.info("Sent daily 8am message.")


    def get_event_list(self):
        # Check next week
        now = dt.utcnow()
        now = now.isoformat() + 'Z'  # 'Z' indicates UTC time
        eventsResult = self.service.events().list(
            calendarId=self.CAL_ID, timeMin=now, singleEvents=True,
            orderBy='startTime').execute()
        return eventsResult.get('items', [])


    def get_todays_support_name(self):
        """
            Search today's events, looking for "Atmosphere Support" and return the name of the user on support.

            Returns:
                Name string
        """
        logging.info("Getting name from calendar for today")

        # Search through events looking for 'Atmosphere Support'
        for event in self.get_event_list():
            desc = event['summary']
            # If the event matches, return the first word of summary which is name
            if "Atmosphere Support" in desc:
                date = dt.strptime(event['start'].get('date'), "%Y-%m-%d").date()
                now = dt.now().date()
                if date == now:
                    name = desc.split('-')[0].strip()
                    try:
                        user = filter(lambda u: (u['real_name'] == name or u['profile']['display_name'] == name) if 'real_name' in u.keys() else False, self.user_list)[0]['id']
                    except:
                        user = name
                    return "Today's support person is %s." % (
                        "<@" + user + ">")
        return "<!here> no one is on support today."


    def get_next_day(self, name):
        """
            Search upcoming events, looking for the specified name.

            Returns:
                Day string ("Monday", etc.)
        """
        logging.info("Getting day from calendar for user %s" % name)
        days = filter(lambda e: name.lower() in e['summary'].lower() and "Atmosphere Support" in e['summary'], self.get_event_list())
        return dt.strptime(days[0].get('date'), "%Y-%m-%d").strftime("%A %Y-%m-%d") if days else "not on the calendar"


    def next_seven_days(self):
        """
            Get a list of users covering support in the next 7 days

            Returns:
                String of support users
        """
        logging.info("Getting support persons for the next week")

        result = ""
        num_days = 0

        for event in self.get_event_list():
            desc = event['summary']
            if "Atmosphere Support" in desc and num_days < 7:
                num_days += 1
                date = dt.strptime(event['start'].get('date'), "%Y-%m-%d").strftime("%A %Y-%m-%d")
                name = desc.split('-')[0].strip()
                result += "The support person for `{}` is {}\n".format(date, name)
        return result


    def fancy_who(self, info):
        logging.info("Handling fancy who request: %s." % info)

        # Remove non-alphanumeric characters
        info = re.sub(r'\W+', '', info)

        num_days = 0
        week = []
        for event in self.get_event_list():
            desc = event['summary']
            if "Atmosphere Support" in desc and num_days < 7:
                num_days += 1
                date = dt.strptime(event['start'].get('date'), "%Y-%m-%d").strftime("%A %Y-%m-%d")
                week.append(
                    "The support person for `%s` is %s\n" % (date, desc.split()[0]))
        result = [week[0]] if 'today' in info else ([week[1]] if 'tomorrow' in info else filter(lambda day: info in day.lower(), week))
        return ''.join(result) if result else "Sorry, I do not have an answer to this question."


    def find_when(self, name, user):
        """
            Finds the user's next support day.

            Argument 'name' is a list. It should look like ['when'] or ['when', 'username'].
            If the first word is not 'when', then ignore.
            If no username is specified after 'when', find it based off asking user's ID.
        """
        if name[0] != "when":
            response = "Command is not 'when'"
        elif len(name) <= 1:
            response = "The next support day for %s is `%s`." % (
                ("<@" + user + ">"), self.get_next_day(
                    self.get_user_name_or_id(user)))
        else:  # User is asking about a different user's next day
            user_id = self.get_user_name_or_id(name[1])
            if user_id:
                response = "The next support day for %s is `%s`." % (
                    ("<@" + user_id + ">"), self.get_next_day(name[1]))
            else:
                response = "User %s does not seem to exist in this team." % (
                    name[1])
        return response


    def get_user_name_or_id(self, name_or_id):
        """
            Gets valid username from ID or ID from username.

            Returns:
                Username.
        """
        logging.info("Getting username for Slack name/id %s" % name_or_id)
        for user in self.user_list:
            if 'name' in user and user.get('name') == name_or_id:
                return user.get('id')
            if 'id' in user and user.get('id') == name_or_id:
                return user.get('name')
        return None


    def get_credentials(self):
        """
            Gets valid user credentials from storage.

            If nothing has been stored, or if the stored credentials are invalid,
            the OAuth2 flow is completed to obtain the new credentials.

            Returns:
                Credentials, the obtained credential.
        """
        logging.info("Getting Google Oauth credentials")
        credential_path = self.GOOGLE_APP_OAUTH_SECRET_PATH
        store = Storage(credential_path)
        credentials = store.get()
        if not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(
                self.GOOGLE_APP_SECRET_PATH, 'https://www.googleapis.com/auth/calendar')
            flow.user_agent = 'Cyverse Slack Supurt But'
            if flags:
                credentials = tools.run_flow(flow, store, flags)
            else:  # Needed only for compatibility with Python 2.6
                credentials = tools.run(flow, store)
            print('Storing credentials to ' + self.GOOGLE_APP_OAUTH_SECRET_PATH)
        return credentials


    def start(self):
        if self.slack_client.rtm_connect():
            while True:
                self.read_and_respond()
                self.morning_message()
                time.sleep(1)
        else:
            print("Connection failed. Invalid Slack token or bot ID?")


def main():
    logging.basicConfig(
        filename="%s/cyverse-support-bot.log" % dirname(realpath(__file__)),
        filemode='a',
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO)

    bot = AtmoSupportBot(
        environ.get("CAL_ID"),
        environ.get("BOT_NAME"),
        environ.get("GOOGLE_APP_SECRET_PATH"),
        environ.get("GOOGLE_APP_OAUTH_SECRET_PATH", ".oauth_secret_json"),
        environ.get('BOT_USER_OAUTH_TOKEN'),
        environ.get('SUPPORT_CHANNEL', 'general')
    )
    bot.start()

if __name__ == "__main__":
    main()
