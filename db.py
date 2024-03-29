import os
from datetime import datetime, timedelta
from typing import Optional

from pymongo import MongoClient

from tiktok_utils import count_laugh_indicator

STRICT_MODE_START_FROM = datetime(2021, 2, 27, 0, 0, 0)

client = MongoClient(os.environ['MONGO_DB_DSN'])
db = client.tiktok


def form_db_stored_message(user_id: int, message_id: int, message_sent_at: datetime,
                           message_text: str, video_id: Optional[str] = None) -> dict:
    return {
        'sent_by_id': user_id,
        'message_id': message_id,
        'video_id': video_id,
        'sent_at': message_sent_at,
        'text': message_text
    }


def save_sent_tiktok(user_id: int, message_id: int, message_sent_at: datetime,
                     message_text: str, video_id: Optional[str]) -> dict:
    res = db.tiktoks.update_one(
        {'message_id': message_id},
        {
            '$set': form_db_stored_message(
                user_id, message_id, message_sent_at,
                message_text, video_id
            ) | {'replies': []},
        },
        upsert=True
    )

    return db.tiktoks.find_one({'_id': res.upserted_id})


def save_tiktok_reply_if_applicable(replied_user: dict, replied_to_message_id: int,
                                    message_id: int, message_sent_at: datetime,
                                    message_text: Optional[str]) -> None:
    not_yet_replied_tiktok = db.tiktoks.find_one({
        'message_id': replied_to_message_id,
        'sent_by_id': {'$ne': replied_user['user_id']},
        'replies.sent_by_id': {'$ne': replied_user['user_id']}
    })

    if not not_yet_replied_tiktok:
        return

    reply_data = form_db_stored_message(
        replied_user['user_id'], message_id, message_sent_at, message_text
    )

    reply_data['laugh_indicator'] = count_laugh_indicator(message_text)

    db.tiktoks.update_one(
        {'message_id': not_yet_replied_tiktok['message_id']},
        {
            '$push': {
                'replies': reply_data
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


def get_not_answered_tiktoks(user_id: int, offset_from_now: Optional[timedelta] = None) -> Optional[dict]:
    query = {
        'sent_by_id': {"$ne": user_id},
        'sent_at': {'$gte': STRICT_MODE_START_FROM},
        'replies.sent_by_id': {'$ne': user_id}
    }
    if offset_from_now:
        query['sent_at']['$lte'] = datetime.utcnow() - offset_from_now

    return list(db.tiktoks.find(query).sort('sent_at', 1))


def get_sent_tiktoks_stats(start_date: Optional[datetime] = None) -> dict:
    query = [
        {
            '$set': {
                'replied': {
                    '$toInt': {
                        '$gte': [
                            {
                                '$size': '$replies'
                            }, 1
                        ]
                    }
                }
            }
        }, {
            '$group': {
                '_id': '$sent_by_id',
                'sent_count': {
                    '$sum': 1
                },
                'got_replies_count': {
                    '$sum': '$replied'
                }
            }
        }
    ]

    return {d['_id']: d for d in db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date))}


def get_outcome_replies_tiktoks_stats(start_date: Optional[datetime] = None) -> dict:
    query = [
        {
            '$unwind': {
                'path': '$replies'
            }
        }, {
            '$set': {
                'reply_time': {
                    '$subtract': [
                        '$replies.sent_at', '$sent_at'
                    ]
                },
                'own_reply': {
                    '$eq': ['$replies.sent_by_id', '$sent_by_id']
                }
            }
        }, {
            '$match': {
                'own_reply': False
            }
        }, {
            '$group': {
                '_id': '$replies.sent_by_id',
                'replied_count': {'$sum': 1},
                'avg_outcome_reply_time': {
                    '$avg': '$reply_time'
                },
                'avg_outcome_laugh_indicator': {
                    '$avg': '$replies.laugh_indicator'
                }
            }
        }
    ]
    return {d['_id']: d for d in db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date))}


def get_income_replies_stats(start_date: Optional[datetime] = None) -> dict:
    query = [
        {
            '$unwind': {
                'path': '$replies'
            }
        }, {
            '$set': {
                'reply_time': {
                    '$subtract': [
                        '$replies.sent_at', '$sent_at'
                    ]
                },
                'own_reply': {
                    '$eq': ['$replies.sent_by_id', '$sent_by_id']
                }
            }
        }, {
            '$match': {
                'own_reply': False
            }
        }, {
            '$group': {
                '_id': '$sent_by_id',
                'avg_income_reply_time': {
                    '$avg': '$reply_time'
                },
                'avg_income_laugh_indicator': {
                    '$avg': '$replies.laugh_indicator'
                }
            }
        }
    ]
    return {d['_id']: d for d in db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date))}


def get_personal_income_stats(user_id: int, start_date: Optional[datetime] = None) -> list:
    query = [
        {
            '$match': {
                'sent_by_id': user_id
            }
        }, {
            '$unwind': {
                'path': '$replies'
            }
        }, {
            '$match': {
                '$replies.sent_by_id': {'$ne': user_id}
            }
        }, {
            '$set': {
                'reply_time': {
                    '$subtract': [
                        '$replies.sent_at', '$sent_at'
                    ]
                }
            }
        }, {
            '$group': {
                '_id': '$replies.sent_by_id',
                'replied_count': {'$sum': 1},
                'avg_income_reply_time': {
                    '$avg': '$reply_time'
                },
                'avg_income_laugh_indicator': {
                    '$avg': '$replies.laugh_indicator'
                }
            }
        }
    ]
    return list(db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date)))


def get_personal_outcome_stats(user_id: int, start_date: Optional[datetime] = None) -> list:
    query = [
        {
            '$match': {
                'sent_by_id': {
                    '$ne': user_id
                },
                'replies.sent_by_id': user_id
            }
        }, {
            '$unwind': {
                'path': '$replies'
            }
        }, {
            '$group': {
                '_id': '$sent_by_id',
                'replied_count': {
                    '$sum': 1
                },
                'avg_income_reply_time': {
                    '$avg': '$reply_time'
                },
                'avg_income_laugh_indicator': {
                    '$avg': '$replies.laugh_indicator'
                }
            }
        }
    ]
    return list(db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date)))


def get_top_most_popular_reactions(user_id: int, start_date: Optional[datetime] = None) -> list:
    query = [
        {
            '$match': {
                'sent_by_id': {
                    '$ne': user_id
                },
                'replies.sent_by_id': user_id
            }
        }, {
            '$unwind': {
                'path': '$replies'
            }
        }, {
            '$group': {
                '_id': '$replies.text',
                'frequency': {
                    '$sum': 1
                }
            }
        }, {
            '$sort': {
                'frequency': -1
            }
        }, {
            '$limit': 10
        }
    ]
    return list(db.tiktoks.aggregate(_add_date_filter_if_provided(query, start_date)))


def get_today_sent_tiktoks_count(user_id: int) -> int:
    now = datetime.utcnow()
    day_beginning = now.replace(hour=0, minute=0, second=1)

    query = {
        'sent_by_id': user_id,
        'sent_at': {'$gte': day_beginning},
    }

    return db.tiktoks.count_documents(query)


def get_tiktoks_with_same_video_id(user_id: int, video_id: str) -> int:
    query = [
        {
            '$match': {
                'video_id': video_id
            }
        },
        {
            '$lookup': {
                'from': 'users',
                'localField': 'sent_by_id',
                'foreignField': 'user_id',
                'as': 'users'
            }
        },
        {
            '$sort': {'sent_at': -1}
        },
        {
            '$project': {
                'user': {'$arrayElemAt': ["$users", 0]},
                'message_id': 1,
                'sent_at': 1
            }
        }
    ]

    return list(db.tiktoks.aggregate(query))


def _add_date_filter_if_provided(query: list[dict], start_date: Optional[datetime]) -> dict:
    if start_date:
        query.insert(0, {'$match': {'sent_at': {'$gt': start_date}}})
    return query
