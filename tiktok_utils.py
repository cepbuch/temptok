from datetime import timedelta

DAY = 60 * 60 * 24


def count_laugh_indicator(text: str) -> int:
    small_ah_count = text.count('ах')
    caps_ah_count = text.count('АХ')
    return small_ah_count + caps_ah_count * 2


def milliseconds_to_string_duration(milliseconds: float) -> str:
    duration = timedelta(milliseconds=milliseconds)
    days = duration.days
    seconds = duration.seconds
    hours = seconds // 3600
    seconds = seconds % 3600
    minutes = seconds // 60

    str_duration = ''

    if days:
        str_duration += f'{days} д. '

    if hours:
        str_duration += f'{hours} ч. '

    if minutes:
        str_duration += f'{minutes} м.'

    return str_duration.strip()
