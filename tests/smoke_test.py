import pyuartsi

assert pyuartsi.UARTTSI.__module__ == "pyuartsi.uart_tsi"
assert "UARTTSI" in pyuartsi.__all__
assert "CDLL" not in dir(pyuartsi)
