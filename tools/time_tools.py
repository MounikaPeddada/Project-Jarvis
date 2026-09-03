import datetime

def get_time():
    """Returns the current time."""
    now = datetime.datetime.now()
    return now.strftime("%I:%M %p")

def get_date():
    """Returns the current date."""
    now = datetime.datetime.now()
    return now.strftime("%B %d, %Y")

def echo(message: str):
    """Repeats back a message."""
    return f"Echo: {message}"

def add_numbers(a: float, b: float):
    """Adds two numbers together."""
    return a + b
    