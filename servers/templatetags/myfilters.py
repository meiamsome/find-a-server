from django import template

register = template.Library()


@register.filter(name='addcss')
def addcss(value, arg):
    return value.as_widget(attrs={'class': arg})


@register.filter(name="timedelta")
def delta(value):
    values = [
        (3600, "hour", "hours"),
        (60, "minute", "minutes"),
        (1, "second", "seconds"),
    ]
    for value in values:
        if value[0] > value:
            continue
        num = int(value/value[0])
        return str(num) + " " + (value[2] if num > 1 else value[1])
    return ""
