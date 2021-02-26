import os
from datetime import datetime, timedelta
from typing import Optional

from pymongo import MongoClient

STRICT_MODE_START_FROM = datetime(2021, 2, 15, 0, 0, 0)

client = MongoClient(os.environ['MONGO_DB_DSN'])
db = client.tiktok


def form_db_stored_message(user_id: int, message_id: int, message_sent_at: datetime, message_text: str) -> dict:
    return {
        'sent_by_id': user_id,
        'message_id': message_id,
        'sent_at': message_sent_at,
        'text': message_text
    }


def save_sent_tiktok(user_id: int, message_id: int, message_sent_at: datetime, message_text: str) -> dict:
    db.tiktoks.update_one(
        {'message_id': message_id},
        {
            '$set': form_db_stored_message(user_id, message_id, message_sent_at, message_text) | {'replies': []},
        },
        upsert=True
    )


def save_tiktok_reply_if_applicable(user_id: int, replied_to_message_id: int,
                                    message_id: int, message_sent_at: datetime,
                                    message_text: str) -> None:
    replied_user = db.users.find_one({'user_id': user_id})

    if not replied_user:
        return

    not_yet_replied_tiktok = db.tiktoks.find_one({
        'message_id': replied_to_message_id,
        'sent_by_user_id': {'$ne': user_id},
        'replies.user_id': {'$ne': user_id}
    })

    if not not_yet_replied_tiktok:
        return

    db.tiktoks.update_one(
        {'message_id': not_yet_replied_tiktok['message_id']},
        {
            '$push': {
                'replies': form_db_stored_message(
                    replied_user['user_id'], message_id, message_sent_at, message_text
                )
            }
        }
    )

    db.users.update_one(
        {'user_id': replied_user['user_id']},
        {
            '$set': {
               'last_replied_at': datetime.utcnow(),
               'last_replied_tiktok_id': not_yet_replied_tiktok['_id']
            },
            '$inc': {
                'tiktoks_replied_count': 1
            }
        }
    )


def get_last_not_answered_tiktok(user_id: int, offset_from_now: Optional[timedelta] = None) -> Optional[dict]:
    query = {
        'sent_by_id': {"$ne": user_id},
        'sent_at': {'$gte': STRICT_MODE_START_FROM},
        'replies.sent_by_id': {'$ne': user_id}
    }
    if offset_from_now:
        query['sent_at']['$lte'] = datetime.utcnow() - offset_from_now

    not_answered_tiktok_list = list(db.tiktoks.find(query).sort('sent_at', 1).limit(1))

    try:
        return not_answered_tiktok_list[0]
    except IndexError:
        return None


def get_sent_tiktoks_stats(start_date: Optional[datetime] = None) -> dict:
    sent_tiktoks_query = [
        {
            '$group': {'_id': '$sent_by_id', 'count': {'$sum': 1}}
        },
        {
            '$lookup': {
                'from': 'users',
                'localField': '_id',
                'foreignField': 'user_id',
                'as': 'users'
            }
        },
        {
            '$replaceRoot': {'newRoot': {'$mergeObjects': [{'$arrayElemAt': ['$users', 0]}, '$$ROOT']}}
        },
        {
            '$sort': {'count': -1}
        },
        {
            '$project': {'name': 1, 'count': 1}
        }
    ]

    if start_date:
        sent_tiktoks_query.insert(0, {'$match': {'sent_at': {'$gt': start_date}}})

    return list(db.tiktoks.aggregate(sent_tiktoks_query))


def get_replied_tiktoks_stats(start_date: Optional[datetime] = None) -> dict:
    ...


def get_tiktok_avg_time_to_answer(start_date: Optional[datetime] = None) -> dict:
    ...


def get_top_most_popular_reactions(start_date: Optional[datetime] = None) -> dict:
    ...
