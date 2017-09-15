def to_stream(num):
    return "%c%c" % (chr((num >> 8) & 255), chr(num & 255))


def from_stream(stream):
    return (ord(stream[0]) << 8) + ord(stream[1]), 2
