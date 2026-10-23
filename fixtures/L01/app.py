from datetime import date

def next_anniversary(today):
    # BUG: raises ValueError when today is Feb 29
    return today.replace(year=today.year + 1)

if __name__ == "__main__":
    t = date.today()
    print("today", t, "-> next", next_anniversary(t))
