import os

from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel

from db import db, save_sent_tiktok, save_tiktok_reply_if_applicable


def export_tiktoks(client: TelegramClient, channel: Channel) -> None:
    count_tiktoks = 0

    print('Started exporting tiktok-related messages')

    for message in client.iter_messages(channel, None, reverse=True):
        if not message.text:
            continue

        user_id = message.sender.id

        if 'vm.tiktok.com' in message.text:
            count_tiktoks += 1

            save_sent_tiktok(user_id, message.id, message.date, message.text)

            if count_tiktoks % 100 == 0:
                print(f'Exported another {count_tiktoks} from group')

        if message.reply_to_msg_id:
            replied_user = db.users.find_one({'user_id': user_id})

            save_tiktok_reply_if_applicable(
                replied_user, message.reply_to_msg_id,
                message.id, message.date, message.text
            )


with TelegramClient('tg_session', os.environ['TG_API_ID'], os.environ['TG_API_HASH']) as client:
    dialogs = client.get_dialogs()
    temptok_dialog = next(d for d in dialogs if d.name == '#temptok')

    participants = client.get_participants(temptok_dialog.entity)

    for participant in participants:
        db_user = db.users.find_one({'user_id': participant.id})

        if not db_user:
            db.users.insert_one(
                {
                    'user_id': participant.id,
                    'name': participant.first_name,
                    'gen': 'm',
                    'last_replied_tiktok_id': None,
                    'last_replied_at': None,
                    'tiktoks_replied_count': 0
                }
            )

    db.tiktoks.delete_many({})

    full_channel = client(GetFullChannelRequest(temptok_dialog.entity)).full_chat

    if full_channel.migrated_from_chat_id:
        print('Found old style group. First exporting from it')
        export_tiktoks(client, client.get_entity(full_channel.migrated_from_chat_id))

    export_tiktoks(client, temptok_dialog.entity)

    print('Done')
