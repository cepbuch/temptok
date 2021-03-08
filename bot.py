
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import pymorphy2
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (CallbackContext, CallbackQueryHandler,
                          CommandHandler, Defaults, Filters, MessageHandler,
                          Updater)
from telegram.update import Message, Update

from db import (STRICT_MODE_START_FROM, db, get_income_replies_stats,
                get_not_answered_tiktoks, get_outcome_replies_tiktoks_stats,
                get_sent_tiktoks_stats, get_tiktoks_with_same_video_id,
                get_today_sent_tiktoks_count, get_top_most_popular_reactions,
                save_sent_tiktok, save_tiktok_reply_if_applicable)
from security import known_user
from tiktok import EXTRACT_SHARE_URL_FROM_TIKTOK, get_tiktok_id_by_share_url
from tiktok_utils import milliseconds_to_string_duration

morph = pymorphy2.MorphAnalyzer()

defaults = Defaults(parse_mode=telegram.ParseMode.HTML)
updater = Updater(token=os.environ['BOT_TOKEN'], defaults=defaults)

dispatcher = updater.dispatcher

COMMANDS = [
    ('start', 'посмотреть инструкцию'),
    ('stats', 'посмотреть статистику по тиктокам (есть аргументы <code>"Имя" "DD.MM.YYYY"</code>)'),
    ('watch', 'получить самый ранний неотвеченный тикток'),
    ('search', 'искать по ссылке'),
]

success = updater.bot.set_my_commands(COMMANDS)

if not success:
    raise ValueError('Error settings commands')


@known_user
def tiktok_handler(user: dict, update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    chat_id = update.effective_chat.id

    video_url = context.match.group(1)
    video_id = None

    try:
        video_id = get_tiktok_id_by_share_url(video_url)
    except Exception as e:
        context.bot.send_message(
            chat_id=26187519,
            text=f'Cannot get video_id of tiktok {video_url}\n\n{repr(e)}'
        )

    is_duplicate = send_is_duplicate_if_applicable(
        chat_id, video_id, user, update, context
    )

    if is_duplicate:
        return

    save_sent_tiktok(
        user['user_id'], message.message_id,
        message.date, message.text, video_id
    )

    send_has_not_answered_if_applicable(chat_id, message, user, update, context)
    send_milestones_if_applicable(chat_id, user, update, context)


def send_is_duplicate_if_applicable(chat_id: int, video_id: str, user: dict,
                                    update: Update, context: CallbackContext) -> bool:

    if not video_id:
        return

    already_sent_tiktoks = get_tiktoks_with_same_video_id(
        user['user_id'], video_id
    )

    if not already_sent_tiktoks:
        return False

    already_sent_tiktok = already_sent_tiktoks[0]
    sent_user = already_sent_tiktok['user']
    context.bot.send_message(
        chat_id=chat_id,
        text=(
            '🤔 Хмм... Кажется этот тикток уже присылали. '
            f"{sent_user['name']} делал{'a' if user['gen'] == 'f' else ''} "
            f"это {already_sent_tiktok['sent_at'].strftime('%d.%m.%Y')} (на дубликаты "
            'можно не отвечать)'
        )
    )

    if already_sent_tiktok['sent_at'] > STRICT_MODE_START_FROM:
        context.bot.forward_message(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_id=already_sent_tiktok['message_id']
        )
    else:
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                'Пруф я переслать не могу, потому что меня тогда еще не было в чате. '
                'Если нужно, поищите по дате.'
            )
        )

    return True


def send_has_not_answered_if_applicable(chat_id: int, message: Message, user: dict,
                                        update: Update, context: CallbackContext) -> None:
    not_answered_tiktoks = get_not_answered_tiktoks(user['user_id'], offset_from_now=timedelta(hours=1))

    if not_answered_tiktoks:
        context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=not_answered_tiktoks[0]['message_id'],
            text=(
                f"🤫 Kind reminder! {user['name']}, у тебя есть неотвеченные тиктоки, а "
                'ты присылаешь новые. Ведь те тиктоки ценнее, чем в ленте: за тебя их уже отобрали '
                'и возможно очень сильно ждут твоей реакции.'
            )
        )


def send_milestones_if_applicable(chat_id: int, user: dict,
                                  update: Update, context: CallbackContext) -> None:
    tiktok_morph = morph.parse('тикток')[0]
    user_sent_tiktoks_count = get_sent_tiktoks_stats().get(user['user_id'], {}).get('sent_count', -1)
    today_sent_tiktoks_count = get_today_sent_tiktoks_count(user['user_id'])

    if user_sent_tiktoks_count % 100 == 0:
        tiktoks_word = tiktok_morph.make_agree_with_number(user_sent_tiktoks_count).word
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🥂 {user['name']}, а у тебя юбилей! За все время ты отправил{'a' if user['gen'] == 'f' else ''} "
                f"уже {user_sent_tiktoks_count} {tiktoks_word}, продолжай в том же духе!"
            )
        )

    if today_sent_tiktoks_count % 15 == 0:
        tiktoks_word = tiktok_morph.make_agree_with_number(today_sent_tiktoks_count).word
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"👍 Вау, вот это контент! За сегодня {user['name']} послал{'a' if user['gen'] == 'f' else ''} уже "
                f"{today_sent_tiktoks_count} {tiktoks_word}. Предлагаю не останавливаться!"
            )
        )


@known_user
def reply_handler(user: dict, update: Update, context: CallbackContext) -> None:
    message = update.effective_message

    save_tiktok_reply_if_applicable(
        user, message.reply_to_message.message_id,
        message.message_id, message.date, message.text
    )


@known_user
def start(user: dict, update: Update, context: CallbackContext) -> None:
    commands_info = '\n\n'.join(
        [f'/{command} — {description}' for command, description in COMMANDS]
    )

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            'Привет!\n\n'
            "Я буду помогать соблюдать некоторые правила temptok'ского клуба. "
            'Какие конкретно правила — станет ясно в момент их нарушения.\n\n'
            'Единственное, чтобы я лишний раз на тебя не наговаривал, отвечай, пожалуйста, на '
            'все тиктоки через реплаи, а не просто сообщением.\n\n'
            f'Что еще:\n\n{commands_info}'
        )
    )


@known_user
def stats(user: dict, update: Update, context: CallbackContext) -> None:
    all_users = list(db.users.find({}).sort('name', 1))

    for_user_id = None
    start_date = None

    if args := context.args:
        for arg in args[:2]:
            # Try parse user
            found_user = None

            try:
                found_user = next(u for u in all_users if u['name'].lower() == arg.lower())
                for_user_id = found_user['user_id']
                continue
            except StopIteration:
                pass

            # Or try parse date
            try:
                start_date = datetime.strptime(arg, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    if for_user_id:
        text = form_stats_for_person(for_user_id, all_users, start_date)
    else:
        text = form_stats_summary(all_users, start_date)

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text
    )


def form_stats_summary(users: list, start_date: Optional[datetime]) -> str:
    tiktok_morph = morph.parse('тикток')[0]

    sent_stats = get_sent_tiktoks_stats(start_date)
    outcome_replies_stats = get_outcome_replies_tiktoks_stats(start_date)
    income_replies_stats = get_income_replies_stats(start_date)

    text = ''

    for user in users:
        user_sent_stats = sent_stats.get(user['user_id'])
        user_outcome_replies_stats = outcome_replies_stats.get(user['user_id'])
        user_income_replies_stats = income_replies_stats.get(user['user_id'])

        text += f"<b>{user['name']}</b>\n"

        if user_sent_stats and user_sent_stats['sent_count']:
            tiktoks_word = tiktok_morph.make_agree_with_number(user_sent_stats['sent_count']).word
            got_answers_percent = round(user_sent_stats['got_replies_count'] / user_sent_stats['sent_count'] * 100)

            text += (
                f"Отправил{'a' if user['gen'] == 'f' else ''} "
                f"<code>{user_sent_stats['sent_count']}</code> {tiktoks_word} "
                f"и получил{'a' if user['gen'] == 'f' else ''} ответ на "
                f"<code>{user_sent_stats['got_replies_count']}</code> из них ({got_answers_percent}%). "
            )

            if user_income_replies_stats:
                text += (
                    f"AVG получает ответ за "
                    f"{milliseconds_to_string_duration(user_income_replies_stats['avg_income_reply_time'])}, "
                    f"AVG длина получаемого ахаха — "
                    f"{round(user_income_replies_stats['avg_income_laugh_indicator'], 1)}"
                )

        else:
            text += f"Не отправлял{'a' if user['gen'] == 'f' else ''} тиктоков за период :("

        text += '\n\n'

        others_sent_count = sum([v['sent_count'] for k, v in sent_stats.items() if k != user['user_id']])

        if others_sent_count:
            replied_count = 0

            if user_outcome_replies_stats:
                replied_count = user_outcome_replies_stats['replied_count']

            text += (
                f"Ответил{'a' if user['gen'] == 'f' else ''} "
                f"на <code>{replied_count}</code> "
                f"из <code>{others_sent_count}</code> тиктоков, которые "
                f"получил{'a' if user['gen'] == 'f' else ''}. "
            )

            if user_outcome_replies_stats:
                text += (
                    f"AVG отвечает за "
                    f"{milliseconds_to_string_duration(user_outcome_replies_stats['avg_outcome_reply_time'])}, "
                    f"AVG длина ахаха в ответе — "
                    f"{round(user_outcome_replies_stats['avg_outcome_laugh_indicator'], 1)}"
                )
        else:
            text += f"А отвечать {'ей' if user['gen'] == 'f' else 'ему'} некому — нет тиктоков"

        text += '\n\n'

    return text


def form_stats_for_person(user_id: int, users: list, start_date: Optional[datetime]) -> str:
    text = (
        'Тут будет статистика чтобы понять кто кому как отвечает, но потом...\n\n'
    )

    # get_personal_income_stats(user_id, start_date)
    # get_personal_outcome_stats(user_id, start_date)

    reactions = get_top_most_popular_reactions(user_id, start_date)

    text += 'Самые частые реакции:\n'
    if reactions:
        for i, reaction in enumerate(reactions, start=1):
            text += f"{i}. {reaction['_id']} ({reaction['frequency']})\n"
    else:
        text += 'Нет реакция за период'

    return text


@known_user
def watch(user: dict, update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    all_users = list(db.users.find({}).sort('name', 1))

    watch_user = user

    if args := context.args:
        try:
            found_user = next(u for u in all_users if u['name'].lower() == args[0].lower())
            watch_user = found_user
        except StopIteration:
            pass

    not_answered_tiktoks = get_not_answered_tiktoks(watch_user['user_id'])

    if not_answered_tiktoks:
        tiktoks_count = len(not_answered_tiktoks)
        tiktok_morph = morph.parse('тикток')[0].make_agree_with_number(tiktoks_count).word

        context.bot.send_message(
            chat_id=chat_id,
            text=f'У тебя {tiktoks_count} {tiktok_morph} к просмотру, начиная с этого 👆',
            reply_to_message_id=not_answered_tiktoks[0]['message_id']
        )
    else:
        context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"Ты молодец, ты все просмотрел{'a' if user['gen'] == 'f' else ''}! "
                'Можно с чистой совестью идти смотреть новые тиктоки и скидывать друзьям 😊'
            )
        )


@known_user
def search(user: dict, update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if not context.args:
        return

    video_url = context.args[0]

    if not (m := re.match(EXTRACT_SHARE_URL_FROM_TIKTOK, video_url)):
        context.bot.send_message(
            chat_id=chat_id,
            text='Не похоже на ссылку на тикток. <code>/manage https://vm.tiktok.com/some_id/</code>'
        )

    video_url = m.group(1)

    try:
        video_id = get_tiktok_id_by_share_url(video_url)
    except Exception as e:
        context.bot.send_message(
            chat_id=chat_id,
            text='Ошибка в пробивке тиктока через сайт тиктока...'
        )
        context.bot.send_message(
            chat_id=chat_id,
            text=f'Cannot get video_id of tiktok {video_url}\n\n{repr(e)}'
        )

    tiktoks = get_tiktoks_with_same_video_id(
        user['user_id'], video_id
    )

    text = 'Использования тиктока:\n'
    reply_markup = None

    if tiktoks:
        for i, tiktok in enumerate(tiktoks, start=1):
            text += f"{i}. {tiktok['user']['name']} — {tiktok['sent_at'].strftime('%d.%m.%Y')}\n"

        reply_markup = InlineKeyboardMarkup.from_column([
            InlineKeyboardButton(
                text='🗑 Удалить последнее',
                callback_data=f"search_delete_top__{tiktok['message_id']}"
            ),
            InlineKeyboardButton(text='Закрыть', callback_data='search_close'),
        ])
    else:
        text = 'Этот тикток еще не присылался'

    context.bot.send_message(chat_id, text, reply_markup=reply_markup)


def callback(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    payload = update.callback_query.data
    chat_id = update.effective_chat.id

    if payload.startswith('search_delete_'):
        payload = payload.removeprefix('search_delete_')
        payload, message_id = payload.split('__')
        found_tiktok = db.tiktoks.find_one({'message_id': int(message_id)})

        if not found_tiktok:
            context.bot.send_message(chat_id, 'Тикток для удаления не найден')
            return

        if payload == 'top':
            additional_text = (
                f"Последнее использование тиктока (от {found_tiktok['sent_at'].strftime('%d.%m.%Y')}) "
                'будет удалено. Ок?'
            )
            reply_markup = InlineKeyboardMarkup.from_column([
                InlineKeyboardButton(
                    text='❌ Да, удалить',
                    callback_data=f'search_delete_confirm__{message_id}'
                ),
                InlineKeyboardButton(text='Отмена', callback_data='search_close'),
            ])
        else:
            reply_markup = None
            db.tiktoks.delete_one({'message_id': int(message_id)})
            additional_text = (
                f"Использование тиктока от {found_tiktok['sent_at'].strftime('%d.%m.%Y')} "
                'было удалено ✅'
            )

        update.callback_query.edit_message_text(
            text=f'{update.effective_message.text}\n\n{additional_text}',
            reply_markup=reply_markup
        )
    else:
        update.callback_query.edit_message_reply_markup(reply_markup=None)


def error_handler(update: Update, context: CallbackContext) -> None:
    try:
        raise context.error
    except Exception as e:
        exc_str = traceback.format_exc(e)
        try:
            context.bot.send_message(
                chat_id=26187519,
                text=exc_str[:4000]
            )

            if not update.callback_query:
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text='💫 Что-то упало... Сережа, почини'
                )

        except Exception:
            pass


tiktoks_handler = MessageHandler(
    Filters.text & Filters.regex(EXTRACT_SHARE_URL_FROM_TIKTOK) & ~Filters.update.edited_message,
    tiktok_handler
)

replies_handler = MessageHandler(
    Filters.reply & ~Filters.update.edited_message,
    reply_handler
)

dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('stats', stats))
dispatcher.add_handler(CommandHandler('watch', watch))
dispatcher.add_handler(CommandHandler('search', search))
dispatcher.add_handler(CallbackQueryHandler(callback))
dispatcher.add_handler(tiktoks_handler)
dispatcher.add_handler(replies_handler)
dispatcher.add_error_handler(error_handler)
updater.start_polling()
