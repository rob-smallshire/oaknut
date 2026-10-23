view[0]  # read a byte
view[0:8] = b"DISK    "  # write — persists to the buffer (and the file)
view.tobytes()  # a plain bytes copy
