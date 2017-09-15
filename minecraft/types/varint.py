from minecraft.types import exceptions


def from_stream(stream):
    num = 0
    chars = 0
    for c in stream:
        val = ord(c)
        num += (val & 127) << 7*chars
        chars += 1
        if not val & 128:
            return num, chars
    raise exceptions.ProtocolException("Incorrect protocol")


def to_stream(number):
    if number == 0:
        return chr(0)
    word = ""
    while number > 0:
        cur = number & 127
        number >>= 7
        if number:
            cur |= 128
        word += chr(cur)
    return word
