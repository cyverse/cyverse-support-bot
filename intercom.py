from intercom.client import Client
import os

INTERCOM_KEY=os.environ.get("INTERCOM_KEY")
intercom = Client(personal_access_token=INTERCOM_KEY)

def check_intercom():
    conversations = intercom.conversations.find_all(open=True)
    num_open = 0
    num_unread = 0

    for conv in conversations:
        num_open += 1
        if conv.read == False:
            num_unread += 1
    return "There are %d open conversations in Intercom.\n Of those conversations, %d are unread" % (num_open, num_unread)
